"""Phase I.3 - Regime Discovery + Stability + Transitions (spec sections 15-17).

Regimes are DISCOVERED from the point-in-time feature panel, never tuned for
P&L. A small deterministic k-means (numpy only, fixed seed) groups sessions
into REGIME_A / REGIME_B / REGIME_C; cluster ids are then ordered by a
volatility composite so the labels are interpretable (A = calmest, C = most
stressed). The same module reports:

  * stability (section 16): frequency, avg/median run duration, empirical
    transition probabilities, monthly/yearly distribution, VIX distribution,
    session-return distribution,
  * transitions (section 17): observed transitions and the behaviour AFTER a
    transition (forward returns are EVALUATION ONLY - never features).

The output is deterministic for a frozen panel and cached under the source +
feature version.
"""
import json
import numpy as np
import pandas as pd

import research_cache as RC
import research_feature_registry as FREG

REGIME_FEATURES = [
    "vix_close", "vix_rank_252", "nifty_20d_hv", "nifty_ret_5d",
    "nifty_ret_20d", "pcr_oi", "oi_total_growth_5d", "atm_premium_pct",
]
K = 3
SEED = 42
MAX_ITERS = 200
N_INIT = 10


def _kmeans(X, k, seed=SEED):
    """Deterministic k-means (k-means++ init, fixed seed). Returns labels."""
    rng = np.random.default_rng(seed)
    n, d = X.shape
    best = None
    for _ in range(N_INIT):
        centers = np.zeros((k, d))
        centers[0] = X[rng.integers(n)]
        dists = np.full(n, np.inf)
        for j in range(1, k):
            dists = np.minimum(dists, np.linalg.norm(X - centers[j - 1], axis=1))
            probs = dists ** 2
            total = probs.sum()
            if total <= 0:
                centers[j] = X[rng.integers(n)]
            else:
                centers[j] = X[np.searchsorted(np.cumsum(probs) / total, rng.random())]
        for _ in range(MAX_ITERS):
            labels = np.argmin(np.linalg.norm(X[:, None, :] - centers[None, :, :], axis=2), axis=1)
            new_centers = np.array([X[labels == j].mean(axis=0) if np.any(labels == j)
                                    else centers[j] for j in range(k)])
            if np.allclose(new_centers, centers):
                centers = new_centers
                break
            centers = new_centers
        inertia = float(np.sum(np.min(np.linalg.norm(X[:, None, :] - centers[None, :, :], axis=2), axis=1) ** 2))
        if best is None or inertia < best[0]:
            best = (inertia, labels, centers)
    return best[1], best[2]


def _std_features(panel):
    """Standardize the regime feature matrix (z-score over full panel)."""
    X = panel[REGIME_FEATURES].replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())
    mu, sd = X.mean(), X.std().replace(0, 1.0)
    return (X - mu) / sd


def _runs(labels):
    """Consecutive-run durations."""
    runs, start = [], 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs.append((labels[start], i - start, start, i - 1))
            start = i
    return runs


def discover_regimes(panel, meta):
    """Assign REGIME_A/B/C to every session + full stability report."""
    source_hash = meta["source_hash"]
    fv = meta["feature_version"]

    cached, state = RC.get("regime_report", source_hash, feature_version=fv)
    if cached is not None:
        return cached, state

    Z = _std_features(panel).to_numpy(dtype=float)
    raw_labels, centers = _kmeans(Z, K, seed=SEED)

    # order clusters by volatility composite (vix_close + nifty_20d_hv z-scores)
    composite = centers[:, [REGIME_FEATURES.index("vix_close"),
                            REGIME_FEATURES.index("nifty_20d_hv")]].mean(axis=1)
    order = np.argsort(composite)  # 0 = calmest
    mapping = {old: f"REGIME_{chr(ord('A') + new)}" for new, old in enumerate(order)}
    labels = pd.Series([mapping[old] for old in raw_labels], index=panel.index, name="regime")

    report = {"regime": labels.to_dict(), "labels": list(labels),
              "assignments": {d: mapping[int(l)] for d, l in zip(panel.index, raw_labels)}}
    report["interpretation"] = {
        reg: {
            "mean_vix": float(panel.loc[labels == reg, "vix_close"].mean()),
            "mean_hv20": float(panel.loc[labels == reg, "nifty_20d_hv"].mean()),
            "mean_ret_20d": float(panel.loc[labels == reg, "nifty_ret_20d"].mean()),
            "mean_pcr": float(panel.loc[labels == reg, "pcr_oi"].mean()),
            "mean_atm_premium_pct": float(panel.loc[labels == reg, "atm_premium_pct"].mean()),
            "n": int((labels == reg).sum()),
        }
        for reg in sorted(set(labels))
    }
    report["stability"] = stability_report(panel, labels)
    report["transitions"] = transitions_report(panel, labels)
    report["regime_features"] = REGIME_FEATURES
    report["feature_version"] = fv
    report["k"] = K
    report["seed"] = SEED

    RC.put("regime_report", source_hash, report, feature_version=fv)
    return report, state


def stability_report(panel, labels):
    """Section 16 - frequency, duration, transition prob, monthly/yearly,
    VIX and return distributions per regime."""
    out = {}
    n = len(labels)
    rets = panel["nifty_ret_1d"].replace([np.inf, -np.inf], np.nan)
    years = [d[:4] for d in labels.index]
    months = [d[:7] for d in labels.index]
    for reg in sorted(set(labels)):
        idx = labels == reg
        m = idx.sum()
        runs = _runs(labels.to_numpy())
        reg_runs = [d for r, d, *_ in runs if r == reg]
        vix = panel.loc[idx, "vix_close"].dropna()
        r = rets.loc[idx].dropna()
        out[reg] = {
            "frequency": round(float(m) / n, 4),
            "sessions": int(m),
            "run_duration": {
                "avg": round(float(np.mean(reg_runs)), 2) if reg_runs else None,
                "median": float(np.median(reg_runs)) if reg_runs else None,
                "max": int(max(reg_runs)) if reg_runs else None,
            },
            "by_year": {y: int((idx & pd.Series([d[:4] == y for d in labels.index], index=labels.index)).sum())
                        for y in sorted(set(years))},
            "by_month": {mth: int((idx & pd.Series([d[:7] == mth for d in labels.index], index=labels.index)).sum())
                         for mth in sorted(set(months))},
            "vix_distribution": {
                "mean": round(float(vix.mean()), 2) if len(vix) else None,
                "std": round(float(vix.std()), 2) if len(vix) else None,
                "p10": round(float(np.percentile(vix, 10)), 2) if len(vix) else None,
                "p50": round(float(np.percentile(vix, 50)), 2) if len(vix) else None,
                "p90": round(float(np.percentile(vix, 90)), 2) if len(vix) else None,
            },
            "return_distribution": {
                "mean": round(float(r.mean()), 5) if len(r) else None,
                "std": round(float(r.std()), 5) if len(r) else None,
                "p10": round(float(np.percentile(r, 10)), 5) if len(r) else None,
                "p50": round(float(np.percentile(r, 50)), 5) if len(r) else None,
                "p90": round(float(np.percentile(r, 90)), 5) if len(r) else None,
                "up_days": int((r > 0).sum()) if len(r) else None,
                "down_days": int((r < 0).sum()) if len(r) else None,
            },
        }
    # transition probability matrix (empirical)
    matrix = {}
    uniq = sorted(set(labels))
    for a in uniq:
        matrix[a] = {}
        for b in uniq:
            num = int(((labels.to_numpy()[:-1] == a) & (labels.to_numpy()[1:] == b)).sum())
            den = int((labels.to_numpy()[:-1] == a).sum())
            matrix[a][b] = round(num / den, 4) if den else None
    out["transition_probability_matrix"] = matrix
    return out


def transitions_report(panel, labels):
    """Section 17 - transitions and behaviour after a transition.
    Forward returns here are EVALUATION ONLY (never used as features)."""
    nifty = panel["nifty_close"]
    fwd = pd.DataFrame({
        "fwd_1d": nifty.shift(-1) / nifty - 1,
        "fwd_5d": nifty.shift(-5) / nifty - 1,
    })
    events = []
    arr = labels.to_numpy()
    for i in range(1, len(arr)):
        if arr[i] != arr[i - 1]:
            events.append({
                "date": labels.index[i],
                "from": arr[i - 1],
                "to": arr[i],
            })
    ev_df = pd.DataFrame(events).set_index("date")
    joined = ev_df.join(fwd)
    per = {}
    for a in sorted(set(arr)):
        per[a] = {}
        for b in sorted(set(arr)):
            sub = joined[(joined["from"] == a) & (joined["to"] == b)]
            per[a][b] = {
                "count": int(len(sub)),
                "after_transition_avg_fwd_1d": round(float(sub["fwd_1d"].mean()), 5) if len(sub) else None,
                "after_transition_avg_fwd_5d": round(float(sub["fwd_5d"].mean()), 5) if len(sub) else None,
                "median_fwd_5d": round(float(sub["fwd_5d"].median()), 5) if len(sub) else None,
                "samples": [{"date": d, "fwd_1d": r, "fwd_5d": f}
                            for d, r, f in zip(sub.index, sub["fwd_1d"], sub["fwd_5d"])],
            }
    return {"n_transitions": len(events), "events": events, "after_transition": per}


if __name__ == "__main__":
    import research_feature_engine as FE
    panel, meta = FE.build_panel()
    report, state = discover_regimes(panel, meta)
    print(json.dumps(report["interpretation"], indent=2))
    print(json.dumps(report["stability"]["transition_probability_matrix"], indent=2))
