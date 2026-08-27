"""Phase 6 pipeline runner (READ-ONLY).

Executes the evaluation flow exactly as layered in the Phase 6 spec:

    47 REAL_FRESH signals
        -> Performance Report
        -> Signal / Prediction / Decision / Execution / Outcome (separate)
        -> Confidence Calibration
        -> Regime Analysis
        -> Failure Analysis
        -> MFE / MAE
        -> Insufficient-Sample filtering
        -> Frozen Baseline

This script NEVER writes to ground_truth.db (mode=ro facade). It only reads,
computes derived metrics, applies the documented sample-sufficiency gate and
prints the frozen baseline. Optionally snapshots the output to an audit file.

Usage:
    .venv/bin/python phase6_pipeline.py
    .venv/bin/python phase6_pipeline.py --json      # full report JSON
    .venv/bin/python phase6_pipeline.py --snapshot  # write audit/PHASE6-PIPELINE-<date>.md
"""
import os
import sys
import json
import argparse
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evaluation_engine as ee
import truth

MIN_PANEL = 0.50  # horizontal separator fill


def _sep(title, width=72):
    print("\n" + "=" * width)
    print(title)
    print("=" * width)


def _gate(data_sufficiency, n, min_sample):
    """Insufficient-sample gate: show the number and the required minimum."""
    return (f"{data_sufficiency} (n={n}, min={min_sample})"
            if n is not None else data_sufficiency)


def _layer0_cohorts(rep):
    _sep("LAYER 0 - COHORT SELECTION (only REAL_FRESH is eligible)")
    for label, n in sorted(rep["cohort_sizes"].items()):
        print(f"  {label:<16} {n}")
    ec = rep["evaluation_cohort"]
    print(f"  preferred            {ec['preferred']} | eligible={ec['eligible_count']} | "
          f"legacy={ec['excluded_legacy']} simulated={ec['excluded_simulated']} "
          f"stale={ec['excluded_stale']} unknown={ec['excluded_unknown']}")


def _layer1_performance_report(rep):
    _sep("LAYER 1 - PERFORMANCE REPORT (ledger counts)")
    c = rep["counts"]
    chain = ("market_observations", "feature_snapshots", "signals", "predictions",
             "decisions", "executions", "positions", "outcomes", "evaluations")
    for t in chain:
        print(f"  {t:<20} {c[t]}")
    print(f"  open_positions        {rep['open_positions']}  closed: {rep['closed_positions']}")
    print(f"  pending_predictions   {rep['pending_predictions']}  unresolved_outcomes: {rep['unresolved_outcomes']}")
    print(f"  leakage_clean         {rep['leakage_verification']['clean']} "
          f"({rep['leakage_verification']['leakage_issues']} issues)")


def _layer2_level_separation(rep):
    _sep("LAYER 2 - LEVEL SEPARATION (signal / prediction / decision / execution / outcome)")

    s = rep["signal_evaluation"]
    print(f"  [SIGNAL] n={s['sample_size']} | directional={s['directional_claims']} "
          f"non_directional={s['non_directional']} | hit_rate={s['hit_rate']} "
          f"| signals_with_outcome={s['signals_with_outcome']}")

    p = rep["prediction_evaluation"]
    print(f"  [PREDICTION] n={p['sample_size']} | correct={p['correct']} incorrect={p['incorrect']} "
          f"neutral={p['neutral']} unknown={p['unknown']} | accuracy={p['accuracy']} "
          f"| pending={p['pending']}")

    d = rep["decision_evaluation"]
    print(f"  [DECISION] n={d['sample_size']} | by_type={d['by_type']} | "
          f"skip_rate={d['skip_rate']} acceptance={d['acceptance_rate']}")

    x = rep["execution_evaluation"]
    print(f"  [EXECUTION] n={x['sample_size']} | slippage={x['average_slippage']} "
          f"fees={x['average_fees']} | estimated_fills={x['estimated_fill_count']}")

    o = rep["outcome_evaluation"]
    print(f"  [OUTCOME] n={o['sample_size']} | win_rate={o['win_rate']} "
          f"avg_net_pnl={o['average_net_pnl']} | by_class={o['by_class']}")


def _layer3_confidence(rep):
    _sep("LAYER 3 - CONFIDENCE CALIBRATION")
    cc = rep["confidence_calibration"]
    print(f"  status: {cc['calibration_status']}  (bands populated: {len(cc['bands'])})")
    for band, b in sorted(cc["bands"].items()):
        print(f"  {band:<10} n={b['sample_size']:<4} success={b['observed_success_rate']} "
              f"failure={b['failure_rate']} avg_pnl={b['average_outcome']}")


def _layer4_regime(rep):
    _sep("LAYER 4 - REGIME ANALYSIS")
    for state, m in sorted(rep["regime_analysis"].items()):
        print(f"  {state:<16} n={m['sample_size']} | signal_success={m['signal_success']} "
              f"decision_acceptance={m['decision_acceptance']} "
              f"net_outcome_total={m['net_outcome_total']}")


def _layer5_failure(rep):
    _sep("LAYER 5 - FAILURE ANALYSIS")
    fa = rep["failure_analysis"]
    print(f"  classified_failures: {fa['classified_failures']} "
          f"| healthy_or_no_trade: {fa['healthy_or_no_trade']} "
          f"| most_common: {fa['most_common']}")
    for cat, n in sorted(fa["by_category"].items()):
        print(f"  {cat}: {n}")


def _layer6_mfe_mae(rep):
    _sep("LAYER 6 - MFE / MAE")
    o = rep["outcome_evaluation"]
    mfe, mae = o["mfe"], o["mae"]
    print(f"  MFE  avg={mfe['average']} median={mfe['median']} available={mfe['available']}")
    print(f"  MAE  avg={mae['average']} median={mae['median']} available={mae['available']}")
    print(f"  mfe_source_distribution: {o['mfe_source_distribution']}")


def _layer7_insufficient_gate(rep):
    _sep("LAYER 7 - INSUFFICIENT-SAMPLE GATE")
    checks = [
        ("signals",        rep["signal_evaluation"],        ee.MIN_SIGNAL_SAMPLE),
        ("predictions",    rep["prediction_evaluation"],    ee.MIN_PREDICTION_SAMPLE),
        ("decisions",      rep["decision_evaluation"],      ee.MIN_SIGNAL_SAMPLE),
        ("executions",     rep["execution_evaluation"],     ee.MIN_OUTCOME_SAMPLE),
        ("outcomes",       rep["outcome_evaluation"],       ee.MIN_OUTCOME_SAMPLE),
        ("risk_guard",     rep["risk_guard_analysis"],      ee.MIN_OUTCOME_SAMPLE),
        ("confidence",     rep["confidence_calibration"],   ee.MIN_CONFIDENCE_SAMPLE),
    ]
    for name, m, mn in checks:
        if name == "confidence":
            suff = "ADEQUATE" if m["calibration_status"] != "INSUFFICIENT_DATA" else "INSUFFICIENT_SAMPLE"
            n = sum(b["sample_size"] for b in m["bands"].values())
        else:
            suff = m.get("data_sufficiency")
            n = m.get("sample_size")
        gate = "PASS" if suff == "ADEQUATE" else "GATED"
        print(f"  {name:<12} {gate:<5} {_gate(suff, n, mn)}")
    print("\n  Rule: a metric with n < minimum may be shown but never used for an"
          "\n  empirical performance claim. No tuning is allowed on gated panels.")


def _layer8_frozen_baseline(rep, engine):
    _sep("LAYER 8 - FROZEN BASELINE")
    bs = engine.baseline_status()
    print(f"  report_version : {bs['report_version']}")
    print(f"  database_sha256: {bs['database_sha256']}")
    print(f"  cohort         : {bs['evaluation_cohort']['preferred']} "
          f"(eligible={bs['evaluation_cohort']['eligible_count']})")
    print(f"  generated_at   : {bs['generated_at']}")
    v = ee.verify_reproducibility(engine)
    print(f"  reproducible   : {v['reproducible']}")
    print(f"  hash_a         : {v['hash_a']}")
    print("\n  Baseline is a MEASUREMENT REFERENCE. It must NOT be tuned or promoted.")


def main():
    ap = argparse.ArgumentParser(description="Phase 6 read-only evaluation pipeline")
    ap.add_argument("--json", action="store_true", help="print full report JSON and exit")
    ap.add_argument("--snapshot", action="store_true",
                    help="also write audit/PHASE6-PIPELINE-<date>.md")
    args = ap.parse_args()

    engine = ee.EvaluationEngine(gt_db=ee.GT_DB)
    rep = engine.evaluation_report()

    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True, default=str))
        return 0

    _layer0_cohorts(rep)
    _layer1_performance_report(rep)
    _layer2_level_separation(rep)
    _layer3_confidence(rep)
    _layer4_regime(rep)
    _layer5_failure(rep)
    _layer6_mfe_mae(rep)
    _layer7_insufficient_gate(rep)
    _layer8_frozen_baseline(rep, engine)

    if args.snapshot:
        date = dt.datetime.now().strftime("%Y-%m-%d")
        path = os.path.join(HERE, "audit", f"PHASE6-PIPELINE-{date}.md")
        buf = []
        _capture = []
        _orig = sys.stdout
        class Cap:
            def write(self, s): _capture.append(s); return len(s)
            def flush(self): pass
        sys.stdout = Cap()
        try:
            _layer0_cohorts(rep); _layer1_performance_report(rep)
            _layer2_level_separation(rep); _layer3_confidence(rep)
            _layer4_regime(rep); _layer5_failure(rep); _layer6_mfe_mae(rep)
            _layer7_insufficient_gate(rep); _layer8_frozen_baseline(rep, engine)
        finally:
            sys.stdout = _orig
        with open(path, "w") as f:
            f.write("# Phase 6 Pipeline Snapshot\n\n```\n" + "".join(_capture) + "\n```\n")
        print(f"\n[saved] {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
