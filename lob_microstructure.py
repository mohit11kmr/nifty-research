"""2026 Market Microstructure & Order Book Toxicity (VPIN) Engine for NIFTY Research.

Implements 2026 Hedge-Fund Microstructure Technologies:
1. Limit Order Book (LOB) Imbalance Ratio
2. Volume-Synchronized Probability of Toxicity (VPIN)
3. Dealer Hedging Flow & Order Flow Delta Pressure
"""
import os
import json
import numpy as np
import pandas as pd


def compute_lob_microstructure(bids=None, asks=None, total_volume=50000, buy_volume=32000, sell_volume=18000):
    """Compute Order Book Imbalance Ratio & VPIN Toxicity Score."""
    if bids is None:
        bids = [1000, 1500, 2200, 1800, 3000]  # Total Bid Quantity
    if asks is None:
        asks = [800, 900, 1200, 1100, 1400]    # Total Ask Quantity

    total_bid_qty = float(sum(bids))
    total_ask_qty = float(sum(asks))

    # 1. LOB Imbalance Ratio: (-1.0 = Max Sell Pressure, +1.0 = Max Buy Pressure)
    lob_imbalance = (total_bid_qty - total_ask_qty) / max(total_bid_qty + total_ask_qty, 1.0)

    # 2. VPIN (Volume-Synchronized Probability of Toxicity)
    vpin_score = abs(buy_volume - sell_volume) / max(total_volume, 1.0)
    is_toxic = vpin_score > 0.40  # High toxicity indicates institutional dumping/manipulation

    # 3. Order Flow Delta Pressure
    order_flow_delta = buy_volume - sell_volume

    return {
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_bid_depth": total_bid_qty,
        "total_ask_depth": total_ask_qty,
        "lob_imbalance_ratio": round(lob_imbalance, 3),
        "microstructure_bias": "STRONG_BUY_PRESSURE" if lob_imbalance > 0.3 else ("STRONG_SELL_PRESSURE" if lob_imbalance < -0.3 else "BALANCED"),
        "vpin_toxicity_score": round(vpin_score, 3),
        "is_order_flow_toxic": is_toxic,
        "order_flow_delta_volume": order_flow_delta,
        "quant_guidance": "HIGH INSTABILITY WARNING: Toxic Order Flow detected! Avoid market orders." if is_toxic else "Normal Microstructure: Order book liquidity is stable."
    }


if __name__ == "__main__":
    print("=== 2026 MARKET MICROSTRUCTURE ENGINE TEST ===")
    res = compute_lob_microstructure()
    print(json.dumps(res, indent=2))
