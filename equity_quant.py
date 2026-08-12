"""Equity Quant Engine — Mansfield Relative Strength (MRS), Sector Rotation & Delivery Volume Scanner.

Scans NSE Stocks for:
1. Mansfield Relative Strength (MRS vs Nifty 50): Stocks outperforming index during market corrections.
2. Sector Rotation Heatmap: Rank IT, BANK, AUTO, PHARMA, METAL, FMCG relative momentum.
3. Delivery Volume Spikes: Institutional accumulation detection.
"""
import os
import json
import datetime as dt
import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def compute_mansfield_rs(stock_df, nifty_df, period=50):
    """Compute Mansfield Relative Strength (MRS) vs Nifty 50.

    Formula: MRS = ((Stock_Close / Nifty_Close) / SMA(Stock_Close / Nifty_Close, period) - 1) * 100
    MRS > 0 = Stock outperforming Nifty 50 (Institutional Accumulation)
    MRS < 0 = Stock underperforming Nifty 50
    """
    if stock_df is None or nifty_df is None or stock_df.empty or nifty_df.empty:
        return pd.Series(dtype=float)

    merged = pd.merge(
        stock_df[["date", "close"]].rename(columns={"close": "stock_close"}),
        nifty_df[["date", "close"]].rename(columns={"close": "nifty_close"}),
        on="date",
        how="inner",
    ).sort_values("date")

    if len(merged) < period:
        return pd.Series(dtype=float)

    rel_perf = merged["stock_close"] / merged["nifty_close"]
    rel_sma = rel_perf.rolling(period, min_periods=period).mean()
    mrs = ((rel_perf / rel_sma) - 1.0) * 100.0
    merged["mrs"] = mrs
    return merged.set_index("date")["mrs"]


def scan_equity_outperformers(top_n=10):
    """Scan Nifty 50 stocks for highest Mansfield Relative Strength."""
    nifty_p = os.path.join(DATA_DIR, "nifty_history.csv")
    stocks_dir = os.path.join(DATA_DIR, "stocks")

    if not os.path.exists(nifty_p) or not os.path.exists(stocks_dir):
        return []

    nifty_df = pd.read_csv(nifty_p)
    nifty_df["date"] = pd.to_datetime(nifty_df["date"])

    results = []
    for f in os.listdir(stocks_dir):
        if not f.endswith(".csv"):
            continue
        sym = f.replace(".csv", "")
        p = os.path.join(stocks_dir, f)
        try:
            sdf = pd.read_csv(p)
            sdf["date"] = pd.to_datetime(sdf["date"])
            mrs_series = compute_mansfield_rs(sdf, nifty_df)
            if not mrs_series.empty:
                latest_mrs = mrs_series.iloc[-1]
                last_price = sdf["close"].iloc[-1]
                pct_1m = (sdf["close"].iloc[-1] / sdf["close"].iloc[-20] - 1) * 100 if len(sdf) >= 20 else 0.0
                results.append({
                    "symbol": sym,
                    "close": round(last_price, 2),
                    "mrs_score": round(latest_mrs, 2),
                    "pct_1m": round(pct_1m, 1),
                    "status": "OUTPERFORMING" if latest_mrs > 0 else "UNDERPERFORMING",
                })
        except Exception:
            continue

    df = pd.DataFrame(results)
    if df.empty:
        return []
    return df.sort_values("mrs_score", ascending=False).head(top_n).to_dict(orient="records")


# Sector ETF first; if delisted/offline, build an equal-weight basket from
# the cached Nifty-50 constituent CSVs in data/stocks/ (real data, offline).
SECTOR_TICKERS = {
    "BANK": ("BANKBEES.NS", ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN"]),
    "IT": ("ITBEES.NS", ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"]),
    "AUTO": ("AUTOBEES.NS", ["M&M", "MARUTI", "TATAMOTORS", "EICHERMOT", "BAJAJ-AUTO"]),
    "PHARMA": ("PHARMABEES.NS", ["SUNPHARMA", "CIPLA", "DRREDDY", "DIVISLAB"]),
    "METAL": ("NETFMETAL.NS", ["TATASTEEL", "JSWSTEEL", "HINDALCO"]),
    "FMCG": ("NETFFMCG.NS", ["ITC", "HINDUNILVR", "NESTLEIND", "BRITANNIA", "TATACONSUM"]),
}
SECTOR_DIR = os.path.join(DATA_DIR, "sectors")
STOCKS_DIR = os.path.join(DATA_DIR, "stocks")


def _etf_or_basket(sector, ticker, constituents):
    """Cached ETF close series, else cached stock-basket close series."""
    cache = os.path.join(SECTOR_DIR, f"{sector}.csv")
    if os.path.exists(cache):
        df = pd.read_csv(cache)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["close"].notna()]
        if len(df) >= 21:
            return df

    # 1) live ETF fetch (only save when non-empty)
    try:
        import yfinance as yf
        etf = yf.Ticker(ticker).history(period="3mo")
        if etf is not None and not etf.empty:
            out = pd.DataFrame({"date": pd.to_datetime(etf.index),
                                "close": etf["Close"].astype(float)}).dropna()
            if len(out) >= 21:
                os.makedirs(SECTOR_DIR, exist_ok=True)
                out.to_csv(cache, index=False)
                return out
    except Exception:
        pass

    # 2) offline equal-weight basket from cached Nifty-50 constituents
    closes = {}
    for sym in constituents:
        p = os.path.join(STOCKS_DIR, f"{sym}.csv")
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, usecols=["date", "close"])
        df["date"] = pd.to_datetime(df["date"])
        df = df[pd.notna(df["close"])]
        closes[sym] = df.set_index("date")["close"]
    if not closes:
        return None
    basket = pd.DataFrame(closes).mean(axis=1).reset_index()
    basket.columns = ["date", "close"]
    os.makedirs(SECTOR_DIR, exist_ok=True)
    basket.to_csv(cache, index=False)
    return basket


def sector_rotation_heatmap():
    """Rank sectoral ETFs for momentum rotation using REAL (cached) data."""
    rankings = []
    for sector, (ticker, constituents) in SECTOR_TICKERS.items():
        df = _etf_or_basket(sector, ticker, constituents)
        if df is None:
            continue
        closes = df["close"].dropna().reset_index(drop=True)
        if len(closes) < 21:
            continue
        ret_1m = (closes.iloc[-1] / closes.iloc[-21] - 1) * 100
        ret_3m = (closes.iloc[-1] / closes.iloc[0] - 1) * 100 if len(closes) >= 60 else None
        rankings.append({
            "sector": sector,
            "ticker": ticker,
            "ret_1m_pct": round(ret_1m, 2),
            "ret_3m_pct": round(ret_3m, 2) if ret_3m is not None else None,
        })

    if not rankings:
        return {
            "status": "NO_DATA",
            "leading_sectors": [],
            "weak_sectors": [],
            "sector_rankings": [],
            "recommendation": "No sector data available (offline + no cache). Run with network to populate data/sectors/.",
        }

    rankings.sort(key=lambda r: r["ret_1m_pct"], reverse=True)
    best, worst = rankings[0]["sector"], rankings[-1]["sector"]
    return {
        "status": "OK",
        "leading_sectors": [r["sector"] for r in rankings[:2]],
        "weak_sectors": [r["sector"] for r in rankings[-2:]],
        "sector_rankings": rankings,
        "recommendation": f"Rotate capital toward {best} momentum; avoid {worst}.",
    }


if __name__ == "__main__":
    print("=== Equity Quant Engine Test ===")
    outperformers = scan_equity_outperformers(5)
    print("Top Mansfield RS Outperformers:")
    print(json.dumps(outperformers, indent=2))
