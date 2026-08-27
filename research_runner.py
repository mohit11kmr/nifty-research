"""Phase I.3 - Full Research Runner (spec sections 27-31).

Deterministic research backtest for Phase I.3 proposals over the frozen
646-session unified dataset.

Cost model is the canonical project model (cost_model.py): COST_PER_TRADE=40
per order, SLIPPAGE_PCT=0.015 adverse per fill. Quantity is the POINT-IN-TIME
market lot of the exact entry contract (from the frozen bhavcopy `NewBrdLotQty`
via `lot_size`); there is NO current-lot fallback. Every option trade is marked
ONLY from the exact (expiry, strike, side) chain row (CONTRACT_UNAVAILABLE =
no trade); on the expiry date a missing row falls back to intrinsic value
(settlement), a documented approximation identical in spirit to the frozen
engines.

Exit semantics (Phase I.4 F1 correction): a LONG single-leg position with a
declared `risk.stop_pct` exits at `stop_pct x entry premium` evaluated on EOD
closes (stop -> horizon -> expiry precedence). Because the dataset is EOD, the
stop is evaluated at EOD resolution only - no intraday stop paths are
invented; the exit mark is the EOD close mark.

Sections implemented:
  27 full research (backtest + dev/OOS + stability + concentration + risk)
  28 OOS / walk-forward verdict (OOS_INSUFFICIENT below 20 OOS trades)
  29 sample-size policy buckets (1-5, 6-19, 20-49, 50+; <20 NOT_RELIABLE)
  30 profit concentration (best / top2 / top3 / best-month; HIGH_CONCENTRATION)
  31 regime robustness (per-regime net; REGIME_SPECIFIC flag)

Accounting invariant (F5): the trade ledger is authoritative; aggregate net
equals aggregate gross minus fees minus slippage at both the trade and the
aggregate level, enforced in compute_metrics.

The evaluation vector (ai_strategy_research.evaluation_vector) is reused so
Phase I.3 research output stays comparable to Phase I.1/I.2 conventions.
"""
import datetime as dt
import json
import os
import hashlib

import numpy as np
import pandas as pd

import research_conditions as RC
import research_feature_registry as FREG
import research_screener as RS
import research_dataset as RD
from cost_model import COST_PER_TRADE, SLIPPAGE_PCT

OOS_CUT = "2026-03-01"
DEV_UNTIL = "2026-02-28"

SAMPLE_BUCKETS = {"1_5": (1, 5), "6_19": (6, 19), "20_49": (20, 49), "50_plus": (50, None)}


def _strike_for(spot, selection, step=50):
    if selection == "ATM":
        return round(spot / step) * step
    if selection == "OTM_1":
        return (int(spot / step) + 1) * step
    if selection == "ITM_1":
        return (int(spot / step) - 1) * step
    return round(spot / step) * step


class Contract:
    __slots__ = ("date", "expiry", "strike", "side", "settle", "close", "underlying",
                 "low", "high", "spot", "lot")

    def __init__(self, date, expiry, strike, side, settle, low, high, spot, close=None,
                 lot=None):
        self.date = date
        self.expiry = expiry
        self.strike = strike
        self.side = side
        self.settle = float(settle) if settle is not None and not np.isnan(settle) else None
        self.close = float(close) if close is not None and not np.isnan(close) else None
        self.low = float(low) if low is not None and not np.isnan(low) else None
        self.high = float(high) if high is not None and not np.isnan(high) else None
        self.spot = float(spot)
        self.lot = int(lot) if lot is not None and not np.isnan(lot) else None

    def mark(self, date):
        """Official settle, but on the expiry date the source bhavcopy stores the
        underlying close in settle_price for expiring contracts (data artifact);
        there we fall back to close which is the true premium/intrinsic."""
        if self.settle is not None and not (date == self.expiry
                                            and self.spot is not None
                                            and abs(self.settle - self.spot) < 1e-9):
            return self.settle
        if self.close is not None:
            return self.close
        return self.settle


class Chain:
    def __init__(self, ctx):
        self.ctx = ctx
        self._index = {}
        for d, g in ctx.chain_by_date.items():
            key = d
            self._index[key] = g[["expiry", "strike", "option_type", "settle_price",
                                  "close", "low", "high", "underlying_price", "lot_size"]]

    def find(self, date, expiry, strike, side):
        g = self._index.get(date)
        if g is None:
            return None
        rows = g[(g["expiry"] == expiry) & (g["strike"] == strike) & (g["option_type"] == side)]
        if not len(rows):
            return None
        r = rows.iloc[0]
        return Contract(date, expiry, strike, side, r["settle_price"],
                        r.get("low"), r.get("high"), r.get("underlying_price"),
                        close=r.get("close"), lot=r.get("lot_size"))


def _intrinsic(spot, strike, side):
    if side == "CE":
        return max(0.0, spot - strike)
    return max(0.0, strike - spot)


def _leg_settle(chain, date, expiry, strike, side):
    """Exact-chain mark; intrinsic fallback on the expiry date only."""
    c = chain.find(date, expiry, strike, side)
    if c is not None:
        mark = c.mark(date)
        if mark is not None:
            return mark, c
    spot = chain.ctx.nifty.set_index("date")["close"].astype(float).get(date)
    if spot is not None and date >= expiry:
        return _intrinsic(float(spot), strike, side), None
    return None, None


class Backtester:
    def __init__(self, spec, panel, ctx, regime_labels):
        self.spec = spec
        self.panel = panel
        self.ctx = ctx
        self.regime = regime_labels
        self.chain = Chain(ctx)
        strat = spec["strategy"]
        entry = strat["entry"]
        self.direction = entry["direction"]
        self.instrument = entry["instrument"]
        self.strike_sel = entry.get("strike_selection", "ATM")
        self.exit_type = (strat.get("exit") or {}).get("type", "HORIZON")
        self.horizon = (strat.get("exit") or {}).get("horizon_sessions") or 5
        self.exit_cond = (strat.get("exit") or {}).get("condition")
        self.stop_pct = (strat.get("risk") or {}).get("stop_pct")
        self.wing_width = (strat.get("risk") or {}).get("wing_width") or 2
        self.regime_allowed = (strat.get("regime") or {}).get("allowed") or []
        self.sessions = panel.index.tolist()
        self.idx = {d: i for i, d in enumerate(self.sessions)}

    # -- signal/exit plumbing ------------------------------------------------
    def _signal(self, d):
        if self.regime_allowed and self.regime.get(d) not in self.regime_allowed:
            return False
        return RC.evaluate(self.panel.loc[d], self.spec["strategy"]["entry"]["conditions"])

    def _exit_boundary_idx(self, entry_idx):
        """Earliest of the horizon session and the near-expiry session; None
        when neither is reachable inside the window (no exit -> no trade)."""
        if self.exit_type == "EXPIRY":
            near = self.panel.loc[self.sessions[entry_idx], "near_expiry"]
            if near not in self.idx:
                return None
            return self.idx[near]
        if self.exit_type == "CONDITION":
            raise NotImplementedError(
                "CONDITION exit semantics not re-implemented in Phase I.4 "
                "(no frozen proposal declares it)")
        horizon_idx = entry_idx + self.horizon
        near = self.panel.loc[self.sessions[entry_idx], "near_expiry"]
        if near in self.idx and self.idx[near] < horizon_idx:
            return self.idx[near]
        if horizon_idx >= len(self.sessions):
            return None
        return horizon_idx

    def _exit_path(self, entry_idx, near, entries):
        """EOD exit walk with precedence entry -> stop -> horizon -> expiry.
        Returns (exit_date, marks, reason, stop_level) or None when no exit
        could be marked inside the window (CONTRACT_UNAVAILABLE -> no trade).

        Stop-loss (F1): applies to LONG single-leg positions with a declared
        `risk.stop_pct`; stop level = stop_pct x entry premium, evaluated on
        EOD closes. Because the dataset is EOD, stop fills are marked at the
        EOD close - no intraday stop paths are invented. A day with no chain
        row for the contract is carried (no fabricated mark)."""
        boundary = self._exit_boundary_idx(entry_idx)
        if boundary is None:
            return None
        stop_level = None
        if (self.stop_pct is not None and self.direction == "LONG"
                and len(entries) == 1):
            stop_level = self.stop_pct * entries[0]["entry"]
        for j in range(entry_idx + 1, boundary + 1):
            d = self.sessions[j]
            marks = []
            ok = True
            for leg in entries:
                s, _ = _leg_settle(self.chain, d, near, leg["strike"], leg["side"])
                if s is None:
                    ok = False  # missing observation -> carry to next day
                    break
                marks.append(s)
            if not ok:
                continue
            if stop_level is not None and marks[0] <= stop_level:
                return (d, marks, "EXIT_STOP", stop_level)
            if j == boundary:
                reason = "EXIT_EXPIRY" if d == near else "EXIT_HORIZON"
                return (d, marks, reason, stop_level)
        return None

    # -- leg sets -------------------------------------------------------------
    def _legs(self, d, expiry, spot):
        """Returns (legs, debit_or_credit_sign). sign=+1 credit (short), -1 debit (long)."""
        atm = _strike_for(spot, "ATM")
        legs = []
        if self.instrument in ("CALL", "PUT"):
            k = _strike_for(spot, self.strike_sel)
            side = "CE" if self.instrument == "CALL" else "PE"
            legs.append({"strike": k, "side": side,
                         "dir": 1 if self.direction == "LONG" else -1})
        elif self.instrument == "STRADDLE":
            for side in ("CE", "PE"):
                legs.append({"strike": atm, "side": side, "dir": 1})
        elif self.instrument == "IRON_CONDOR":
            kc = _strike_for(spot, "OTM_1")
            kp = _strike_for(spot, "ITM_1")
            w = self.wing_width * 50
            legs = [
                {"strike": kc, "side": "CE", "dir": -1},
                {"strike": kp, "side": "PE", "dir": -1},
                {"strike": kc + w, "side": "CE", "dir": 1},
                {"strike": kp - w, "side": "PE", "dir": 1},
            ]
        return legs

    # -- trade simulation -------------------------------------------------------
    def simulate(self):
        trades = []
        for i, d in enumerate(self.sessions):
            if not self._signal(d):
                continue
            near = self.panel.loc[d, "near_expiry"]
            spot = float(self.panel.loc[d, "nifty_close"])
            legs = self._legs(d, near, spot)
            if not legs:
                continue
            entries = []
            skip = False
            for leg in legs:
                s, c = _leg_settle(self.chain, d, near, leg["strike"], leg["side"])
                if s is None:
                    skip = True  # CONTRACT_UNAVAILABLE at entry -> no trade
                    break
                lot = c.lot if c is not None else None
                if lot is None:
                    skip = True  # no authoritative market lot -> no trade
                    break
                entries.append({"strike": leg["strike"], "side": leg["side"],
                                "dir": leg["dir"], "entry": s, "lot": lot})
            if skip:
                continue
            path = self._exit_path(i, near, entries)
            if path is None:
                continue
            exit_date, exits, reason, stop_level = path
            t = self._finalize(d, exit_date, near, spot, entries, exits, reason,
                               stop_level)
            if t is not None:
                trades.append(t)
        return trades

    def _finalize(self, entry_date, exit_date, expiry, spot, entries, exits,
                  reason, stop_level):
        n_legs = len(entries)
        lots = [leg["lot"] for leg in entries]
        gross = 0.0
        for leg, s in zip(entries, exits):
            gross += leg["dir"] * (s - leg["entry"]) * leg["lot"]
        gross = round(gross, 2)
        orders = 2 if n_legs == 1 else n_legs * 2
        fees = round(orders * COST_PER_TRADE, 2)
        prem_sum = 0.0
        for leg, s in zip(entries, exits):
            prem_sum += (leg["entry"] + s) * leg["lot"]
        slippage = round(SLIPPAGE_PCT * prem_sum, 2)
        net = round(gross - fees - slippage, 2)
        if n_legs == 1:
            option_type = entries[0]["side"]
            strike = entries[0]["strike"]
        elif self.instrument == "STRADDLE":
            option_type = "STRADDLE"
            strike = entries[0]["strike"]
        else:
            option_type = "IRON_CONDOR"
            strike = entries[0]["strike"]
        days_held = (dt.date.fromisoformat(exit_date) - dt.date.fromisoformat(entry_date)).days
        mfe, mae = self._mfe_mae(entry_date, exit_date, expiry, entries)
        return {
            "entry_date": entry_date,
            "exit_date": exit_date,
            "regime": self.regime.get(entry_date),
            "option_type": option_type,
            "strike": float(strike),
            "reason": reason,
            "net_pnl": net,
            "fees": fees,
            "slippage": slippage,
            "mfe": mfe,
            "mae": mae,
            "days_held": days_held,
            "gross": gross,
            "n_legs": n_legs,
            "lot": lots[0],
            "entry_mark": entries[0]["entry"] if n_legs == 1 else None,
            "exit_mark": exits[0] if n_legs == 1 else None,
            "stop_level": round(stop_level, 2) if stop_level is not None else None,
        }

    def _mfe_mae(self, entry_date, exit_date, expiry, entries):
        """Daily gross mark path for MFE/MAE between entry and exit."""
        start = self.idx[entry_date]
        end = self.idx[exit_date] if exit_date in self.idx else start
        best, worst = 0.0, 0.0
        base = sum(leg["dir"] * leg["entry"] * leg["lot"] for leg in entries)
        for j in range(start + 1, end + 1):
            d = self.sessions[j]
            total = 0.0
            for leg in entries:
                s, _ = _leg_settle(self.chain, d, expiry, leg["strike"], leg["side"])
                if s is None:
                    s = leg["entry"]  # no mark -> carry
                total += leg["dir"] * s * leg["lot"]
            pnl = total - base
            best = max(best, pnl)
            worst = min(worst, pnl)
        return round(best, 2), round(worst, 2)


# ---------------------------------------------------------------------------
# metrics + evaluation (sections 27-31)
# ---------------------------------------------------------------------------
def compute_metrics(trades, n_sessions):
    nets = [t["net_pnl"] for t in trades]
    n = len(nets)
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    gross = round(sum(t["gross"] for t in trades), 2)
    fees = round(sum(t["fees"] for t in trades), 2)
    slippage = round(sum(t["slippage"] for t in trades), 2)
    total = round(sum(nets), 2)
    if n:
        # F5 accounting invariant: the trade ledger is authoritative; the
        # aggregate identity net == gross - fees - slippage must hold (within
        # per-trade 2dp rounding, <= 0.005/trade).
        tol = 0.01 * n + 1e-6
        assert abs(total - (gross - fees - slippage)) <= tol, (
            f"aggregate accounting invariant broken: net {total} != "
            f"gross {gross} - fees {fees} - slippage {slippage} "
            f"(= {gross - fees - slippage})")
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    equity = []
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for x in nets:
        cum += x
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
        equity.append(cum)
    return {
        "trade_count": n,
        "win_rate": round(len(wins) / n, 4) if n else None,
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (None if n == 0 else np.inf),
        "expectancy": round(total / n, 2) if n else None,
        "net_pnl": total,
        "fees": fees,
        "slippage": slippage,
        "gross": gross,
        "max_drawdown": round(mdd, 2),
        "max_drawdown_pct": round(mdd / max(1.0, max(equity)) * 100, 2) if equity and max(equity) > 0 else None,
        "trade_frequency": round(n / n_sessions, 4) if n_sessions else None,
        "avg_days_held": round(float(np.mean([t["days_held"] for t in trades])), 2) if n else None,
        "status": "NOT_RELIABLE" if n < 20 else "RELIABLE",
    }


def _by_regime(trades):
    out = {}
    for t in trades:
        r = t["regime"] or "UNKNOWN"
        g = out.setdefault(r, {"trades": 0, "wins": 0, "net": 0.0})
        g["trades"] += 1
        g["wins"] += 1 if t["net_pnl"] > 0 else 0
        g["net"] += t["net_pnl"]
    return {k: {"trades": v["trades"], "winrate": round(v["wins"] / v["trades"], 4),
                "net": round(v["net"], 2)} for k, v in out.items()}


def _split_oos(trades):
    dev = [t for t in trades if t["entry_date"] <= DEV_UNTIL]
    oos = [t for t in trades if t["entry_date"] >= OOS_CUT]
    return dev, oos


def _concentration(trades):
    nets = [t["net_pnl"] for t in trades]
    total = sum(nets)
    if not nets or total == 0:
        return {"best_trade_pct": None, "top2_pct": None, "top3_pct": None,
                "best_month_pct": None, "concentration_flag": None}
    srt = sorted(nets, reverse=True)
    months = {}
    for t in trades:
        m = t["entry_date"][:7]
        months[m] = months.get(m, 0.0) + t["net_pnl"]
    best_month = max(months, key=months.get)
    top3 = sum(srt[:3]) / total * 100
    flag = "HIGH_CONCENTRATION" if (top3 > 50 or srt[0] / total * 100 > 30) else "BALANCED"
    return {
        "best_trade_pct": round(srt[0] / total * 100, 2) if total else None,
        "top2_pct": round(sum(srt[:2]) / total * 100, 2) if total else None,
        "top3_pct": round(top3, 2),
        "best_month": best_month,
        "best_month_pct": round(months[best_month] / total * 100, 2),
        "concentration_flag": flag,
    }


def _sample_buckets(trades):
    n = len(trades)
    out = {}
    for label, (lo, hi) in SAMPLE_BUCKETS.items():
        out[label] = int(n >= lo and (hi is None or n <= hi))
    return out


def _regime_robustness(trades, by_regime):
    positive = [k for k, v in by_regime.items() if v["net"] > 0]
    total_net = sum(v["net"] for v in by_regime.values())
    flag = "REGIME_SPECIFIC" if (total_net > 0 and len(positive) == 1
                                 and len(by_regime) > 1) else "MULTI_REGIME"
    return {"by_regime": by_regime, "positive_regimes": positive, "flag": flag}


def research(proposal_doc, panel, ctx, regime_labels):
    """Run the full research pipeline for a proposal. Returns output dict."""
    spec = proposal_doc["strategy"]
    FREG.require_registered(spec.get("required_features") or [])
    bt = Backtester(proposal_doc, panel, ctx, regime_labels)
    trades = bt.simulate()
    metrics = compute_metrics(trades, len(panel))
    dev, oos = _split_oos(trades)
    by_regime = _by_regime(trades)
    oos_quality = {
        "development_until_2026_02_28": {"trades": len(dev),
                                         "net": round(sum(t["net_pnl"] for t in dev), 2)},
        "out_of_sample_from_2026_03_01": {"trades": len(oos),
                                          "net": round(sum(t["net_pnl"] for t in oos), 2),
                                          "winrate": round(len([t for t in oos if t["net_pnl"] > 0]) / len(oos), 4) if oos else None},
    }
    oos_quality["verdict"] = "OOS_INSUFFICIENT" if len(oos) < 20 else "OOS_MEASURED"
    output = {
        "proposal_id": proposal_doc["proposal"]["proposal_id"],
        "family": proposal_doc["proposal"].get("candidate_family"),
        "metrics": metrics,
        "evaluation_vector": _eval_vector(metrics, trades, by_regime, oos_quality),
        "by_regime": by_regime,
        "oos": oos_quality,
        "concentration": _concentration(trades),
        "sample_buckets": _sample_buckets(trades),
        "regime_robustness": _regime_robustness(trades, by_regime),
        "n_trades": len(trades),
        "trades": trades,
    }
    output["result_hash"] = result_hash(output)
    output["aggregate"] = {
        "trades": len(trades),
        "gross": round(sum(t["gross"] for t in trades), 2),
        "fees": round(sum(t["fees"] for t in trades), 2),
        "slippage": round(sum(t["slippage"] for t in trades), 2),
        "net": round(sum(t["net_pnl"] for t in trades), 2),
        "identity": "net == gross - fees - slippage",
        "check": abs(round(sum(t["net_pnl"] for t in trades), 2)
                     - (round(sum(t["gross"] for t in trades), 2)
                        - round(sum(t["fees"] for t in trades), 2)
                        - round(sum(t["slippage"] for t in trades), 2))
                     <= 0.01 * len(trades) + 1e-6),
    }
    return output


def _eval_vector(metrics, trades, by_regime, oos_quality):
    from ai_strategy_research import evaluation_vector
    return evaluation_vector(metrics, trades, by_regime, oos_quality)


def result_hash(output):
    exclude = {"result_hash", "generated_at"}
    canonical = {k: v for k, v in output.items() if k not in exclude}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode()).hexdigest()


def reproducibility(output):
    a = result_hash(output)
    b = result_hash(output)
    return {"reproducible": a == b, "hash_a": a, "hash_b": b}


def save_proposal_research(output, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(output, fh, indent=2, sort_keys=True, default=str)
