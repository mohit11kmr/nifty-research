"""Trainer - walk-forward self-training loop.

For every historical bar: generate the agent's verdict using ONLY data
available up to that point, then check what ACTUALLY happened in the next
N bars. Accumulates accuracy stats per regime / per bias. This is the
"training data" the agent learns from - it shows which rules actually work.
"""
import os
import numpy as np
import pandas as pd

import market_brain as brain


def _outcome_direction(df, idx, horizon):
    """Did the market move in the predicted direction over next `horizon` bars?
    Returns: actual_move_pct, moved_up(bool)."""
    end = min(idx + horizon, len(df) - 1)
    if end <= idx:
        return 0.0, None
    start_close = df["close"].iloc[idx]
    end_close = df["close"].iloc[end]
    return (end_close / start_close - 1) * 100, end_close > start_close


def train(df, horizon=3, min_idx=250, iv=None):
    """Walk-forward: predict at each bar, score against reality.

    Returns: predictions DataFrame + summary stats.
    """
    records = []
    for i in range(min_idx, len(df)):
        past = df.iloc[: i + 1]
        try:
            res = brain.analyze_market(past, iv=iv)
        except Exception:  # noqa: BLE001
            continue
        move_pct, moved_up = _outcome_direction(df, i, horizon)

        bias = res["verdict"]["bias"]
        if bias == "NEUTRAL" or moved_up is None:
            hit = None
        else:
            hit = int((bias == "CALL" and moved_up) or (bias == "PUT" and not moved_up))

        records.append({
            "date": res["date"],
            "close": res["close"],
            "regime": res["regime"],
            "bias": bias,
            "strength": res["verdict"]["strength"],
            "confidence": res["verdict"]["confidence"],
            "horizon_move_pct": round(move_pct, 2),
            "hit": hit,
        })

    pred = pd.DataFrame(records)
    return pred


def summarize(pred):
    """Accuracy breakdowns - what the agent learned."""
    if pred.empty:
        return {}
    scored = pred[pred["hit"].notna()].copy()
    if scored.empty:
        return {}

    def acc(sub):
        if len(sub) == 0:
            return None
        return {
            "n": len(sub),
            "hit_rate": round(sub["hit"].mean() * 100, 1),
            "avg_move": round(sub["horizon_move_pct"].mean(), 2),
        }

    return {
        "overall": acc(scored),
        "by_regime": {r: acc(scored[scored["regime"] == r]) for r in sorted(scored["regime"].unique())},
        "by_bias": {b: acc(scored[scored["bias"] == b]) for b in ["CALL", "PUT"]},
        "by_strength": {s: acc(scored[scored["strength"] == s]) for s in ["HIGH", "MEDIUM", "LOW"]},
        "high_conf": acc(scored[scored["confidence"] >= 60]),
    }


def train_and_report(df, horizon=3, out_md="results/training_report.md", out_csv="results/predictions_log.csv"):
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    pred = train(df, horizon=horizon)
    pred.to_csv(out_csv, index=False)
    s = summarize(pred)

    lines = []
    lines.append("# Agent Training Report (Walk-Forward)")
    lines.append(f"\n- Horizon: {horizon} bars forward | Predictions logged: {len(pred)}")
    lines.append(f"- Directional calls: {len(pred[pred['bias'].isin(['CALL','PUT'])])}")

    if s.get("overall"):
        o = s["overall"]
        lines.append(f"- **Overall hit-rate: {o['hit_rate']}%** ({o['n']} calls, avg move {o['avg_move']:+}%)")

    lines.append("\n## Hit-rate by Regime")
    lines.append("\n| Regime | Calls | Hit-rate% | Avg move% |")
    lines.append("|---|---|---|---|")
    for r, a in (s.get("by_regime") or {}).items():
        if a:
            lines.append(f"| {r} | {a['n']} | {a['hit_rate']} | {a['avg_move']:+} |")

    lines.append("\n## Hit-rate by Bias")
    lines.append("\n| Bias | Calls | Hit-rate% | Avg move% |")
    lines.append("|---|---|---|---|")
    for b, a in (s.get("by_bias") or {}).items():
        if a:
            lines.append(f"| {b} | {a['n']} | {a['hit_rate']} | {a['avg_move']:+} |")

    lines.append("\n## Hit-rate by Signal Strength")
    lines.append("\n| Strength | Calls | Hit-rate% |")
    lines.append("|---|---|---|")
    for st, a in (s.get("by_strength") or {}).items():
        if a:
            lines.append(f"| {st} | {a['n']} | {a['hit_rate']} |")

    lines.append("\n## Lessons (auto-derived)")
    br = s.get("by_regime") or {}
    best = max([(k, v) for k, v in br.items() if v], key=lambda kv: kv[1]["hit_rate"], default=None)
    if best:
        lines.append(f"- Agent is most accurate in **{best[0]}** markets ({best[1]['hit_rate']}% hit-rate, n={best[1]['n']})")
    hi = s.get("high_conf")
    if hi:
        lines.append(f"- High-confidence calls (>=60% conf): {hi['hit_rate']}% hit-rate (n={hi['n']}) - {('trust them' if hi['hit_rate']>=55 else 'still need caution')}")

    with open(out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return "\n".join(lines)
