"""Super-AI Machine Learning Ensemble Engine for NIFTY Research.

Trains XGBoost, LightGBM, Random Forest, and Gradient Boosting Ensembles
on a FIXED 80/20 train/test split (NOT walk-forward). CONTEXT ONLY: no
standalone edge (~51% vs ~52% baseline, see AGENTS.md). Feature cache
freshness is surfaced in the output (feature_freshness).
"""
import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))


def train_super_ai_ensemble():
    """Train XGBoost + LightGBM + Random Forest Meta-Ensemble."""
    print("\n🧠 [SUPER-AI ML ENGINE] Initializing Multi-Model Ensemble...")
    
    # Load historical feature dataset
    feat_path = "data/ml_features.csv"
    if not os.path.exists(feat_path):
        print(f"Error: {feat_path} not found.")
        return None

    import truth
    feat_fresh = truth.file_freshness(feat_path, truth.DAILY_CACHE_FRESHNESS_H)

    df = pd.read_csv(feat_path)
    if "target" not in df.columns:
        # Create target: 1 if next day close > current close, else 0
        df["target"] = (df["close"].shift(-1) > df["close"]).astype(int)

    # Fill missing indicator values (e.g. initial lookbacks)
    df = df.bfill().ffill().fillna(0)
    features = [c for c in df.columns if c not in ["date", "target", "target_up", "close", "high", "low", "open"]]

    X = df[features]
    y = df["target_up"] if "target_up" in df.columns else df["target"]


    if len(X) < 100:
        print("Dataset too small for deep ML training.")
        return None

    # Train-Test Split (80% Train, 20% Test)
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    models = {}
    scores = {}

    # Model 1: XGBoost Classifier
    try:
        import xgboost as xgb
        xgb_model = xgb.XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42)
        xgb_model.fit(X_train, y_train)
        xgb_acc = xgb_model.score(X_test, y_test)
        models["xgboost"] = xgb_model
        scores["xgboost"] = round(xgb_acc * 100, 2)
    except Exception as e:
        scores["xgboost"] = f"Error: {e}"

    # Model 2: LightGBM Classifier
    try:
        import lightgbm as lgb
        lgb_model = lgb.LGBMClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, verbose=-1)
        lgb_model.fit(X_train, y_train)
        lgb_acc = lgb_model.score(X_test, y_test)
        models["lightgbm"] = lgb_model
        scores["lightgbm"] = round(lgb_acc * 100, 2)
    except Exception as e:
        scores["lightgbm"] = f"Error: {e}"

    # Model 3: Random Forest Classifier
    try:
        from sklearn.ensemble import RandomForestClassifier
        rf_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        rf_model.fit(X_train, y_train)
        rf_acc = rf_model.score(X_test, y_test)
        models["random_forest"] = rf_model
        scores["random_forest"] = round(rf_acc * 100, 2)
    except Exception as e:
        scores["random_forest"] = f"Error: {e}"

    # Ensemble Prediction on Latest Bar
    latest_bar = X.iloc[[-1]]
    ensemble_votes = []
    for name, m in models.items():
        pred = m.predict(latest_bar)[0]
        prob = m.predict_proba(latest_bar)[0][1]
        ensemble_votes.append({"model": name, "prediction": int(pred), "bullish_probability": round(float(prob), 4)})

    avg_bull_prob = np.mean([v["bullish_probability"] for v in ensemble_votes])
    final_verdict = "BULLISH_CALL" if avg_bull_prob > 0.55 else ("BEARISH_PUT" if avg_bull_prob < 0.45 else "NEUTRAL_SIDEWAYS")

    res = {
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_historical_bars": len(df),
        "model_accuracies_pct": scores,
        "ensemble_votes": ensemble_votes,
        "ensemble_bullish_probability": round(float(avg_bull_prob), 4),
        "super_ai_verdict": final_verdict,
        "feature_freshness": feat_fresh.get("status"),
        "feature_age_h": feat_fresh.get("age_h"),
        "feature_freshness_budget_h": feat_fresh.get("budget_h"),
    }

    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    train_super_ai_ensemble()
