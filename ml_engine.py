"""ML engine - honest walk-forward models on cached data.

Two realistic uses (deep models on ~250 daily samples = fake edge, so we keep
it simple and validate out-of-sample):

1. META-BLENDER: the 16 strategy signals become features. A model learns which
   strategy is reliable in which context (price structure + FII/OI regime) and
   blends them - instead of betting everything on one strategy.

2. DIRECTION CLASSIFIER: technical + institutional features predict next-day
   NIFTY direction. Walk-forward: train on past, test only on future data.

Both use `walk_forward_eval()` so reported numbers are strictly out-of-sample.
Data comes from cache (data/nifty_history.csv, data/fii_dii_history.csv) -
nothing is re-downloaded. Run `python build_data.py` first if cache is stale.
"""
import os
import datetime as dt

import numpy as np
import pandas as pd

import truth

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.preprocessing import StandardScaler
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FEATURE_CACHE = os.path.join(DATA, "ml_features.csv")
FEATURE_BUDGET_H = truth.DAILY_CACHE_FRESHNESS_H


def feature_cache_status():
    """Truth-layer freshness of the feature cache (P-06)."""
    return truth.file_freshness(FEATURE_CACHE, FEATURE_BUDGET_H)


def _source_freshness():
    """Freshness of the underlying cache files the features are built from."""
    return {
        "nifty_history": truth.file_freshness(
            os.path.join(DATA, "nifty_history.csv"), truth.DAILY_CACHE_FRESHNESS_H).get("status"),
        "fii_dii_history": truth.file_freshness(
            os.path.join(DATA, "fii_dii_history.csv"), truth.FII_DII_FRESHNESS_H).get("status"),
    }


# --------------------------------------------------------------------------
# Feature building (cached)
# --------------------------------------------------------------------------
def _load_nifty():
    p = os.path.join(DATA, "nifty_history.csv")
    if not os.path.exists(p):
        from data_fetcher import fetch_index_history
        df = fetch_index_history("NIFTY 50", out_csv=p)
    else:
        df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def _load_fiidii():
    p = os.path.join(DATA, "fii_dii_history.csv")
    if not os.path.exists(p):
        from institutional import fetch_fii_dii_history
        df = fetch_fii_dii_history()
    else:
        df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date")


def _tech_features(df):
    c = df["close"]
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"]
    out["close"] = c
    for n in (1, 3, 5, 10, 20):
        out[f"ret_{n}"] = c.pct_change(n) * 100
    out["rsi14"] = df["rsi14"] if "rsi14" in df else None
    out["sma20"] = df.get("sma20")
    out["sma50"] = df.get("sma50")
    out["adx"] = df.get("adx")
    out["atr_pct"] = (df.get("atr") / c * 100) if "atr" in df else None
    if out["sma20"].notna().any() and out["sma50"].notna().any():
        out["above_sma50"] = (c > out["sma50"]).astype(int)
        out["dist_sma50_pct"] = (c / out["sma50"] - 1) * 100
    # vol regime
    out["vol_20"] = c.rolling(20).std() / c * 100
    # day of week
    out["dow"] = df["date"].dt.dayofweek
    return out


def _inst_features(df):
    out = pd.DataFrame(index=df.index)
    out["date"] = df["date"]
    for c in ("fii_net", "dii_net"):
        if c not in df.columns:
            continue
        out[c] = df[c]
        out[f"{c}_5d"] = df[c].rolling(5, min_periods=1).sum()
    if "fii_idx_fut_net" in df.columns:
        out["fii_fut_net"] = df["fii_idx_fut_net"].replace(0, np.nan)
    if "pcr" in df.columns:
        out["pcr"] = df["pcr"].replace(0, np.nan)
    if "sentiment_score" in df.columns:
        out["sentiment"] = df["sentiment_score"]
    return out


def _build_features_from_source():
    """Build feature cache from the real source caches and write it out."""
    nifty = _load_nifty()
    nifty = indicators_add(nifty)
    tech = _tech_features(nifty)

    inst = pd.DataFrame()
    try:
        fiidii = _load_fiidii()
        inst = _inst_features(fiidii)
    except Exception:
        inst = None

    if inst is not None and not inst.empty:
        tech = tech.merge(inst, on="date", how="left")

    tech["target_up"] = (tech["close"].shift(-1) > tech["close"]).astype(int)
    tech = tech.dropna(subset=["close"])

    os.makedirs(DATA, exist_ok=True)
    tech.to_csv(FEATURE_CACHE, index=False)
    return tech


def build_features(force=False):
    """Merge technical + institutional features, add next-day direction target.

    Cached to data/ml_features.csv so it builds once. P-06 (Phase 4A):
    a STALE / MISSING / INVALID cache is rebuilt from the real source pipeline
    (nifty_history.csv + fii_dii_history.csv) instead of being read as fresh.
    A rebuild failure returns (None, meta) and the cache is left STALE/MISSING
    - no fabricated data, no timestamp touching. Returns (df, meta).
    """
    meta = {
        "path": FEATURE_CACHE,
        "budget_h": FEATURE_BUDGET_H,
        "rebuilt": False,
        "discarded_corrupt": False,
        "error": None,
        "source_freshness": _source_freshness(),
    }
    st = feature_cache_status()
    meta["previous_status"] = st["status"]
    meta["age_h"] = st["age_h"]

    if os.path.exists(FEATURE_CACHE) and not force and st["status"] == truth.REAL:
        df = pd.read_csv(FEATURE_CACHE)
        df["date"] = pd.to_datetime(df["date"])
        meta.update(status=truth.REAL, age_h=st["age_h"])
        return df, meta

    if os.path.exists(FEATURE_CACHE) and st["status"] == truth.INVALID:
        try:
            os.remove(FEATURE_CACHE)
            meta["discarded_corrupt"] = True
        except OSError:
            pass

    try:
        df = _build_features_from_source()
        meta["rebuilt"] = True
        st2 = feature_cache_status()
        meta["source_freshness"] = _source_freshness()
        final_status = st2["status"]
        if meta["source_freshness"].get("nifty_history") != truth.REAL:
            final_status = truth.STALE  # built from stale underlying data
        meta.update(status=final_status, age_h=st2["age_h"])
        return df, meta
    except Exception as e:
        meta["status"] = truth.MISSING if not os.path.exists(FEATURE_CACHE) else st["status"]
        meta["error"] = str(e)[:160]
        return None, meta


def indicators_add(df):
    """Add core indicators if not already present (columns checked lazily)."""
    import indicators as ind
    df = df.copy()
    if "rsi14" not in df.columns:
        df["rsi14"] = ind.rsi(df["close"])
    if "sma20" not in df.columns:
        df["sma20"] = ind.sma(df["close"], 20)
    if "sma50" not in df.columns:
        df["sma50"] = ind.sma(df["close"], 50)
    if "adx" not in df.columns:
        a, _, _ = ind.adx(df["high"], df["low"], df["close"])
        df["adx"] = a
    if "atr" not in df.columns:
        df["atr"] = ind.atr(df["high"], df["low"], df["close"])
    return df


# --------------------------------------------------------------------------
# Walk-forward evaluation (honest out-of-sample)
# --------------------------------------------------------------------------
def walk_forward_eval(features, feature_cols, model_factory, train_days=180,
                      step=20, min_pred=30, target_col="target_up"):
    """Train on past window, predict only future rows, slide forward.
    Returns combined predictions DataFrame + metrics. No shuffling - strictly
    chronological so it reflects real trading use."""
    df = features.dropna(subset=feature_cols + [target_col]).reset_index(drop=True)
    if len(df) < train_days + min_pred:
        return None, "insufficient data"
    X = df[feature_cols].to_numpy(dtype=float)
    y = df[target_col].to_numpy(dtype=int)
    preds = np.full(len(df), np.nan)

    start = train_days
    while start + min_pred <= len(df):
        tr_s, tr_e = 0, start
        te_s, te_e = start, min(start + step, len(df))
        try:
            scaler = StandardScaler()
            Xtr = scaler.fit_transform(X[tr_s:tr_e])
            Xte = scaler.transform(X[te_s:te_e])
            model = model_factory()
            model.fit(Xtr, y[tr_s:tr_e])
            preds[te_s:te_e] = model.predict(Xte)
        except Exception:
            pass
        start += step

    ok = ~np.isnan(preds)
    if ok.sum() < min_pred:
        return None, "too few oos predictions"
    pred = preds[ok].astype(int)
    actual = y[ok]
    acc = accuracy_score(actual, pred)
    base = max(np.mean(actual), 1 - np.mean(actual))
    f1 = f1_score(actual, pred, zero_division=0)
    # directional edge vs naive always-bullish baseline
    out = df.loc[ok.index if hasattr(ok, "index") else np.where(ok)[0]].copy()
    out["pred"] = pred
    out["actual"] = actual
    return {
        "accuracy": round(acc, 3),
        "baseline": round(base, 3),
        "f1": round(f1, 3),
        "n": int(ok.sum()),
        "edge": round(acc - base, 3),
        "pred_df": out,
    }, None


def _make(model_kind):
    if model_kind == "rf":
        return lambda: RandomForestClassifier(n_estimators=120, max_depth=4, min_samples_leaf=5, random_state=42)
    if model_kind == "gbm":
        return lambda: GradientBoostingClassifier(n_estimators=120, max_depth=2, learning_rate=0.05, random_state=42)
    return lambda: LogisticRegression(max_iter=500, C=0.5)


# --------------------------------------------------------------------------
# Meta-blender: 16 strategies -> features -> direction model
# --------------------------------------------------------------------------
def meta_blender(train_days=200, step=20, model_kind="logit"):
    """Use each strategy's live signal as an ML feature; learn which blend
    predicts next-day direction. Strictly walk-forward."""
    if not HAS_SKLEARN:
        return None, "sklearn missing"
    import indicators as ind
    import strategies as S

    nifty = _load_nifty()
    nifty = indicators_add(nifty).set_index("date")
    sig_cols = []
    for name in S.ALL_STRATEGIES:
        try:
            sig = S.ALL_STRATEGIES[name](nifty)
            sig = sig.rename(name)
            nifty = nifty.join(sig)
            sig_cols.append(name)
        except Exception:
            continue
    nifty = nifty.replace({1: 1, -1: 0})  # strategy signal -> binary "long" flag

    df = nifty.dropna(subset=sig_cols).copy()
    df["target_up"] = (df["close"].shift(-1) > df["close"]).astype(int)
    df = df.dropna(subset=["target_up"])

    res, err = walk_forward_eval(df.reset_index(), sig_cols,
                                 _make(model_kind), train_days, step,
                                 target_col="target_up")
    if err:
        return None, err

    # latest context: which strategies agree right now
    last = df.iloc[-1]
    agree_call = int((df[sig_cols].iloc[-1] == 1).sum())
    agree_put = int((df[sig_cols].iloc[-1] == 0).sum())
    res = {
        "walk_forward": res,
        "n_strategies": len(sig_cols),
        "today": str(df.index[-1].date()),
        "call_agree": agree_call,
        "put_agree": agree_put,
        "close": round(float(last["close"]), 2),
    }
    nf = truth.file_freshness(os.path.join(DATA, "nifty_history.csv"),
                              truth.DAILY_CACHE_FRESHNESS_H)
    res = truth.envelope(
        res,
        status=nf["status"],
        source="cache:nifty_history.csv",
        data_freshness=nf["status"],
        evaluation_method="walk_forward",
        feature_cache_age_h=nf["age_h"],
        feature_cache_budget_h=truth.DAILY_CACHE_FRESHNESS_H,
    )
    return res, None


def direction_forecast(model_kind="gbm", train_days=180, step=20):
    """Next-day NIFTY direction from technical + institutional features."""
    if not HAS_SKLEARN:
        return None, "sklearn missing"
    feats, meta = build_features()
    if feats is None:
        return None, f"feature cache unavailable ({meta.get('status')}): {meta.get('error')}"
    cols = [c for c in feats.columns
            if c not in ("date", "close", "target_up") and feats[c].notna().sum() > len(feats) * 0.6]
    res, err = walk_forward_eval(feats, cols, _make(model_kind), train_days, step)
    # FII/DII merge may leave too few rows -> fall back to technical only
    if err and "insufficient" in str(err):
        feats = feats.drop(columns=[c for c in feats.columns
                                    if c in ("fii_net", "dii_net", "fii_net_5d", "dii_net_5d",
                                             "fii_fut_net", "pcr", "sentiment")], errors="ignore")
        cols = [c for c in feats.columns
                if c not in ("date", "close", "target_up") and feats[c].notna().sum() > len(feats) * 0.6]
        res, err = walk_forward_eval(feats, cols, _make(model_kind), train_days, step)
    if err:
        return None, err
    res.pop("pred_df")
    fstat = feature_cache_status()
    try:
        data_ts = dt.datetime.fromtimestamp(os.path.getmtime(FEATURE_CACHE), tz=dt.timezone.utc
                                            ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OSError:
        data_ts = None
    return truth.envelope(
        res,
        status=meta.get("status", fstat["status"]),
        source="cache:ml_features.csv",
        data_timestamp=data_ts,
        data_freshness=fstat["status"],
        evaluation_method="walk_forward",
        feature_version=truth.hash_version(cols),
        feature_cache_age_h=fstat["age_h"],
        feature_cache_budget_h=FEATURE_BUDGET_H,
        rebuilt=meta.get("rebuilt"),
    ), None


def format_ml(res):
    if not res or "walk_forward" not in res:
        return [f"ML: no result ({res})"]
    wf = res["walk_forward"]
    lines = [
        f"META-BLENDER | {res['n_strategies']} strategies blended | out-of-sample "
        f"acc {wf['accuracy']:.0%} vs baseline {wf['baseline']:.0%} (edge {wf['edge']:+.0%}) n={wf['n']}",
        f"Today {res['today']} close {res['close']}: CALL agreement {res['call_agree']}/{res['n_strategies']}, "
        f"PUT agreement {res['put_agree']}/{res['n_strategies']}",
    ]
    if res.get("data_freshness"):
        lines.append(f"Data freshness: {res['data_freshness']} "
                     f"(age {res.get('feature_cache_age_h')}h / budget {res.get('feature_cache_budget_h')}h)")
    return lines


if __name__ == "__main__":
    print("=== ML meta-blender (walk-forward) ===")
    res, err = meta_blender()
    if err:
        print("  error:", err)
    else:
        for l in format_ml(res):
            print(l)
