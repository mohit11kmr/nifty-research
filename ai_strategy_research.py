"""Phase I - AI Strategy Research Pipeline.

Takes a compiled proposal through the deterministic backtest gate, runs it
through the EXISTING frozen backtest framework (BacktestAdapter), computes an
evaluation VECTOR (never a single opaque AI score), compares it under the same
dataset/cost model against current_control_v1 (and, where applicable, the other
registered strategies), and records the result with full provenance.

Safety:
  - only proposals that pass every gate reach the backtest
  - backtest uses the EXISTING deterministic engine (no parallel engine)
  - the cost model is canonical and unchangeable
  - nothing here writes production data / ground truth / paper account
"""
import datetime as dt
import hashlib
import json
import os

import strategy_proposal_schema as PS
import strategy_proposal_registry as SPR
from backtest_adapter import BacktestAdapter, ENGINES
import strategy_schema as S
import strategy_execution

REPO = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(REPO, "results")


# ---------------------------------------------------------------------------
# Deterministic result hashing
# ---------------------------------------------------------------------------
def result_hash(research_output):
    """Deterministic hash: strips the timestamp + result_hash itself so a
    rerun over identical data yields an identical result_hash."""
    exclude = {"generated_at", "result_hash", "baseline"}
    canonical = {k: v for k, v in research_output.items() if k not in exclude}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True,
                                     default=str).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Evaluation vector (section 16 - no single score)
# ---------------------------------------------------------------------------
def evaluation_vector(metrics, rows, by_regime, oos, capital=100000.0):
    n = metrics.get("trade_count") or 0
    wr = metrics.get("win_rate") or 0.0
    pf = metrics.get("profit_factor")
    expectancy = metrics.get("expectancy")
    mdd = metrics.get("max_drawdown") or 0.0
    return {
        "edge_quality": {
            "profit_factor": pf,
            "expectancy": expectancy,
            "net_pnl": metrics.get("net_pnl"),
        },
        "sample_size": n,
        "stability": {
            "win_rate": wr,
            "status": metrics.get("status"),
            "sufficient": n >= 20,
        },
        "drawdown": {"max_drawdown": mdd,
                     "max_drawdown_pct": metrics.get("max_drawdown_pct")},
        "risk_validity": "DECLARED_OK",   # gate passed pre-backtest (H3)
        "data_quality": "UNIFIED_FULL",
        "regime_robustness": {
            k: {"trades": v["trades"], "winrate": v["winrate"], "net": v["net"]}
            for k, v in (by_regime or {}).items()},
        "oos_quality": {
            "development": oos.get("development_until_2026_02_28", {}),
            "out_of_sample": oos.get("out_of_sample_from_2026_03_01", {}),
            "verdict": "OOS_INSUFFICIENT" if
            (oos.get("out_of_sample_from_2026_03_01", {}) or {}).get("trades", 0) < 20
            else "OOS_MEASURED",
        },
        "trade_frequency": metrics.get("trade_frequency"),
        "profit_concentration": _concentration(rows),
        "execution_realism": {
            "cost_model": "canonical (40/order, 1.5% slippage)",
            "fees": metrics.get("fees"),
            "slippage": metrics.get("slippage"),
        },
        "complexity": _complexity(rows),
    }


def _concentration(rows):
    nets = [r["net_pnl"] for r in rows]
    total = sum(nets)
    if not nets or total == 0:
        return {"best_trade_pct": None, "top5_pct": None}
    top5 = sorted(nets, reverse=True)[:5]
    return {
        "best_trade_pct": round(max(nets) / total * 100, 1),
        "top5_pct": round(sum(top5) / total * 100, 1),
        "n_trades": len(nets),
    }


def _complexity(rows):
    opt_types = {r.get("option_type") for r in rows}
    return {"n_trades": len(rows),
            "instrument_kinds": sorted(str(x) for x in opt_types if x)}


# ---------------------------------------------------------------------------
# Baseline comparison (section 24) - same dataset + cost model
# ---------------------------------------------------------------------------
def baseline_comparison(proposal_run, control_run, data_root=None):
    """Compare a proposal's research run against current_control_v1 under the
    same engine/dataset/cost. Never ranks on net P&L alone."""
    p = proposal_run["metrics"]
    c = control_run["metrics"]
    return {
        "control": "current_control_v1",
        "dataset": {
            "calendar_hash": proposal_run.get("dataset_calendar_hash"),
            "manifest_hash": proposal_run.get("dataset_manifest_hash"),
        },
        "dimensions": {
            "net_pnl": {"proposal": p.get("net_pnl"), "control": c.get("net_pnl")},
            "win_rate": {"proposal": p.get("win_rate"), "control": c.get("win_rate")},
            "profit_factor": {"proposal": p.get("profit_factor"),
                              "control": c.get("profit_factor")},
            "expectancy": {"proposal": p.get("expectancy"),
                           "control": c.get("expectancy")},
            "max_drawdown": {"proposal": p.get("max_drawdown"),
                             "control": c.get("max_drawdown")},
            "sample_size": {"proposal": p.get("trade_count"),
                            "control": c.get("trade_count")},
            "fees": {"proposal": p.get("fees"), "control": c.get("fees")},
            "slippage": {"proposal": p.get("slippage"), "control": c.get("slippage")},
        },
        "verdict": _comparison_verdict(p, c),
    }


def _comparison_verdict(p, c):
    """Structured, non-rank-based verdict."""
    if (p.get("trade_count") or 0) < 20:
        return "NOT_RELIABLE"
    if (c.get("trade_count") or 0) == 0:
        return "NO_CONTROL"
    d = {
        "net_better": (p.get("net_pnl") or 0) > (c.get("net_pnl") or 0),
        "pf_better": _gt_or_none(p.get("profit_factor"), c.get("profit_factor")),
        "dd_better": (p.get("max_drawdown") or 0) > (c.get("max_drawdown") or 0),
        "wr_better": (p.get("win_rate") or 0) > (c.get("win_rate") or 0),
    }
    score = sum(1 for v in d.values() if v)
    if score >= 3:
        return "OUTPERFORMS_CONTROL"
    if score == 2:
        return "COMPARABLE_TO_CONTROL"
    return "UNDERPERFORMS_CONTROL"


def _gt_or_none(a, b):
    if a is None or b is None:
        return None
    return a > b


# ---------------------------------------------------------------------------
# Research execution
# ---------------------------------------------------------------------------
def run_research(compilation, registry=None, data_root=None, control=True,
                 control_run=None):
    """Run the full research pipeline for a compiled proposal.

    Engine-backed strategies run through the frozen BacktestAdapter. Any other
    proposal runs through the Phase I.2 generic execution layer (registered
    deterministic families only). Returns a research_output dict
    (deterministic). Raises ValueError with a structured failure code if the
    proposal cannot reach the backtest.

    control_run: optional pre-computed control research output. When provided
    it is reused for the baseline comparison instead of recomputing the
    engine-backed control backtest (the control run is data-independent of the
    proposal and identical for every proposal).
    """
    strategy_id = compilation.strategy_id
    if strategy_id in ENGINES:
        adapter = BacktestAdapter(compilation.compiled, data_root=data_root)
        run = adapter.run()
    else:
        run = strategy_execution.run_generic(compilation, data_root=data_root)

    oos = _oos_split(run["trades"])
    vector = evaluation_vector(run["metrics"], run["trades"], run["by_regime"], oos)

    research = (compilation.proposal.get("research") or {})
    output = {
        "proposal": compilation.to_record(),
        "strategy_id": strategy_id,
        "spec_hash": compilation.spec_hash,
        "dataset": {
            "manifest_hash": research.get("dataset_manifest_hash"),
            "start_date": research.get("start_date"),
            "end_date": research.get("end_date"),
            "dev_oos_cut": research.get("dev_oos_cut"),
        },
        "metrics": run["metrics"],
        "by_regime": run["by_regime"],
        "monthly": run["monthly"],
        "trades": run["trades"],
        "evaluation_vector": vector,
        "fingerprints": run.get("fingerprints"),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    output["result_hash"] = result_hash(output)

    if control:
        try:
            if control_run is None:
                control_run = BacktestAdapter(
                    _compiled_control(), data_root=data_root).run()
            output["baseline"] = baseline_comparison(output, control_run,
                                                     data_root=data_root)
        except Exception as exc:  # control must never fail a research run
            output["baseline"] = {"control": "current_control_v1",
                                  "error": str(exc)}
    return output


def _compiled_control():
    from strategy_registry import default_registry
    return default_registry().compile("current_control_v1")


def _oos_split(rows, cut="2026-03-01"):
    dev = [r for r in rows if (r.get("exit_date") or "") < cut]
    oos = [r for r in rows if (r.get("exit_date") or "") >= cut]

    def agg(v):
        if not v:
            return {"trades": 0, "net": 0.0}
        w = sum(1 for r in v if r["net_pnl"] > 0)
        return {"trades": len(v),
                "winrate": round(w / len(v) * 100, 1),
                "net": round(sum(r["net_pnl"] for r in v), 2)}
    return {"development_until_2026_02_28": agg(dev),
            "out_of_sample_from_2026_03_01": agg(oos)}


def persist_research(output, registry=None, out_dir=None, status="REVIEW"):
    """Persist a research output to the proposal registry + results dir.

    Production isolation: writes only to strategy_proposals/ and results/.
    """
    registry = registry or SPR.default_registry()
    pid = (output["proposal"]["proposal_id"])
    record = registry.update(pid, result_hash=output["result_hash"],
                             dataset_hash=output["dataset"].get("manifest_hash"),
                             status=status, evidence="BACKTESTED")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{pid}.research.json")
        with open(path, "w") as fh:
            json.dump(output, fh, indent=2, sort_keys=True, default=str)
        return path
    return None
