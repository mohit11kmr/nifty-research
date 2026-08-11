"""Options Volatility Skew & Smile Analytics Engine.

Calculates OTM Put IV vs OTM Call IV ratio (IV Skew), Volatility Smile,
and multi-index (NIFTY, BANKNIFTY, FINNIFTY) options skew metrics.
"""
import os
import json
import numpy as np
import pandas as pd


def compute_iv_skew(chain, spot=None, otm_pct=0.015):
    """Compute IV Skew Ratio = Mean(OTM Put IV) / Mean(OTM Call IV).

    chain: DataFrame containing strike, ce_iv, pe_iv, ce_oi, pe_oi
    spot: current spot price
    otm_pct: distance from spot for OTM strikes (~1.5%)
    """
    if chain is None or chain.empty:
        return {"skew_ratio": 1.0, "status": "NEUTRAL", "reason": "Empty chain"}

    df = chain.copy()
    if not spot:
        spot = df["strike"].median()

    otm_put_threshold = spot * (1.0 - otm_pct)
    otm_call_threshold = spot * (1.0 + otm_pct)

    otm_puts = df[df["strike"] <= otm_put_threshold]
    otm_calls = df[df["strike"] >= otm_call_threshold]

    put_iv = otm_puts["pe_iv"].replace(0, np.nan).mean() if "pe_iv" in df else np.nan
    call_iv = otm_calls["ce_iv"].replace(0, np.nan).mean() if "ce_iv" in df else np.nan

    if np.isnan(put_iv) or np.isnan(call_iv) or call_iv == 0:
        return {
            "spot": spot,
            "mean_put_iv": round(put_iv, 2) if not np.isnan(put_iv) else 0.0,
            "mean_call_iv": round(call_iv, 2) if not np.isnan(call_iv) else 0.0,
            "skew_ratio": 1.0,
            "bias": "NEUTRAL",
            "interpretation": "IV data unavailable for skew",
        }

    skew_ratio = put_iv / call_iv

    if skew_ratio > 1.25:
        bias = "BEARISH_HEDGE"
        interp = f"Put IV ({put_iv:.1f}%) > Call IV ({call_iv:.1f}%): High Institutional Downside Hedging (Reversal Risk)"
    elif skew_ratio < 0.85:
        bias = "BULLISH_SPECULATION"
        interp = f"Call IV ({call_iv:.1f}%) > Put IV ({put_iv:.1f}%): Aggressive Call Buying (Upside Momentum)"
    else:
        bias = "NEUTRAL"
        interp = f"Balanced IV Skew (Ratio: {skew_ratio:.2f})"

    return {
        "spot": spot,
        "mean_put_iv": round(put_iv, 2),
        "mean_call_iv": round(call_iv, 2),
        "skew_ratio": round(skew_ratio, 2),
        "bias": bias,
        "interpretation": interp,
    }


def multi_index_scan():
    """Scan NIFTY, BANKNIFTY, FINNIFTY skew indices."""
    indices = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
    results = {}
    try:
        import nse_live
        for idx in indices:
            try:
                chain, meta = nse_live.fetch_option_chain_live(idx)
                if not chain.empty:
                    spot = meta.get("underlying")
                    results[idx] = compute_iv_skew(chain, spot=spot)
                else:
                    results[idx] = {"status": "NO_DATA"}
            except Exception as e:
                results[idx] = {"status": "ERROR", "error": str(e)}
        nse_live.close()
    except Exception as e:
        results["error"] = str(e)
    return results


if __name__ == "__main__":
    dummy_chain = pd.DataFrame([
        {"strike": 24000, "pe_iv": 18.5, "ce_iv": 12.0},
        {"strike": 24200, "pe_iv": 16.0, "ce_iv": 12.5},
        {"strike": 24500, "pe_iv": 14.0, "ce_iv": 14.0},
        {"strike": 24800, "pe_iv": 12.0, "ce_iv": 15.5},
        {"strike": 25000, "pe_iv": 11.5, "ce_iv": 17.0},
    ])
    res = compute_iv_skew(dummy_chain, spot=24500)
    print("IV Skew Test Output:")
    print(json.dumps(res, indent=2))
