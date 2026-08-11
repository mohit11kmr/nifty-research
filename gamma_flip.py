"""Hedge Fund Market Maker Gamma Exposure (GEX) & Liquidity Heatmap Engine.

Calculates:
1. Net Gamma Exposure (GEX) per strike across option chain.
2. Gamma Flip Level: The exact strike where Market Makers switch from Short Gamma (Volatility Acceleration) to Long Gamma (Volatility Stabilization).
3. Institutional Liquidity Sweep Pools: High OI concentration levels where market makers trigger stops.
"""
import os
import json
import numpy as np
import pandas as pd


def calculate_gamma_exposure(chain, spot=None):
    """Compute Net Gamma Exposure (GEX) per strike and identify Gamma Flip Level.

    GEX Formula: Call GEX - Put GEX
    Call GEX = Call_OI * Call_Gamma * Spot * 100
    Put GEX = Put_OI * Put_Gamma * Spot * 100
    """
    if chain is None or chain.empty:
        return {"gamma_flip_level": None, "gex_status": "NO_DATA"}

    df = chain.copy()
    if not spot:
        spot = float(df["strike"].median())

    try:
        import greeks
        # Compute Gamma for each strike
        gex_list = []
        for _, row in df.iterrows():
            strike = row["strike"]
            ce_oi = row.get("ce_oi", 0) or 0
            pe_oi = row.get("pe_oi", 0) or 0

            ce_g = greeks.bs_price_and_greeks(spot, strike, 15, 0.15, side="CE")["gamma"]
            pe_g = greeks.bs_price_and_greeks(spot, strike, 15, 0.15, side="PE")["gamma"]

            ce_gex = ce_oi * ce_g * spot * 75
            pe_gex = pe_oi * pe_g * spot * 75
            net_gex = ce_gex - pe_gex

            gex_list.append({
                "strike": strike,
                "ce_gex": ce_gex,
                "pe_gex": pe_gex,
                "net_gex": net_gex
            })

        gex_df = pd.DataFrame(gex_list).sort_values("strike")
        
        # Identify Gamma Flip Strike (where Net GEX crosses zero)
        gex_df["prev_gex"] = gex_df["net_gex"].shift(1)
        crossings = gex_df[(gex_df["net_gex"] * gex_df["prev_gex"]) < 0]
        
        if not crossings.empty:
            gamma_flip_strike = crossings["strike"].iloc[0]
        else:
            gamma_flip_strike = gex_df.loc[gex_df["net_gex"].abs().idxmin(), "strike"]

        total_net_gex = gex_df["net_gex"].sum()
        market_maker_regime = "LONG_GAMMA (STABILIZING)" if total_net_gex > 0 else "SHORT_GAMMA (EXPLOSIVE VOLATILITY)"

        # Liquidity Sweep Pools (Top 3 CE & PE Gamma concentrations)
        top_ce_pools = gex_df.sort_values("ce_gex", ascending=False).head(3)["strike"].tolist()
        top_pe_pools = gex_df.sort_values("pe_gex", ascending=False).head(3)["strike"].tolist()

        return {
            "spot": spot,
            "gamma_flip_strike": int(gamma_flip_strike),
            "market_maker_regime": market_maker_regime,
            "total_net_gex_crores": round(total_net_gex / 1e7, 2),
            "liquidity_pools": {
                "upside_resistance_liquidity": top_ce_pools,
                "downside_support_liquidity": top_pe_pools
            },
            "trader_guidance": f"Above Gamma Flip ({gamma_flip_strike:.0f}): Market Makers stabilize market. Below {gamma_flip_strike:.0f}: Short Gamma accelerates moves!"
        }
    except Exception as e:
        return {"gamma_flip_level": None, "error": str(e)}


if __name__ == "__main__":
    dummy_chain = pd.DataFrame([
        {"strike": 24000, "ce_oi": 50000, "pe_oi": 120000},
        {"strike": 24200, "ce_oi": 70000, "pe_oi": 90000},
        {"strike": 24500, "ce_oi": 150000, "pe_oi": 140000},
        {"strike": 24800, "ce_oi": 180000, "pe_oi": 50000},
        {"strike": 25000, "ce_oi": 220000, "pe_oi": 20000},
    ])
    print("=== HEDGE FUND GAMMA FLIP & GEX ENGINE TEST ===")
    gex_result = calculate_gamma_exposure(dummy_chain, spot=24500)
    print(json.dumps(gex_result, indent=2))
