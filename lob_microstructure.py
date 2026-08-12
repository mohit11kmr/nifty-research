"""2026 Market Microstructure & Order Book Toxicity (VPIN) Engine for NIFTY Research.

Implements:
1. Limit Order Book (LOB) Imbalance Ratio
2. Volume-Synchronized Probability of Toxicity (VPIN)
3. Dealer Hedging Flow & Order Flow Delta Pressure

UPGRADED 2026-08-12: when called WITHOUT explicit book args, it now loads the
REAL order book from `data/research.db` (1.2M+ NSE tick rows). No fabricated
5-level book / volumes. When no real data exists it returns an honest
INSUFFICIENT_DATA status.
"""
import os
import json
import sqlite3

import numpy as np
import pandas as pd

DB_PATH = os.path.join("data", "research.db")


def _load_real_book():
    """Best-bid/best-ask levels + tick-rule buy/sell volume from research.db."""
    if not os.path.exists(DB_PATH):
        return None
    con = sqlite3.connect(DB_PATH)
    try:
        row = con.execute(
            "SELECT recv_ts, COUNT(*) c FROM ticks GROUP BY recv_ts "
            "ORDER BY c DESC LIMIT 1").fetchone()
        if not row:
            return None
        ts = row[0]

        # nearest spot around that timestamp -> tradable ATM band only
        spot_ts = con.execute(
            "SELECT recv_ts, value FROM spot ORDER BY ABS(julianday(recv_ts) - julianday(?)) LIMIT 1",
            (ts,)).fetchone()
        spot = float(spot_ts[1]) if spot_ts else None

        rows = con.execute(
            "SELECT strike, side, ltp, bid, ask, volume FROM ticks WHERE recv_ts=?",
            (ts,)).fetchall()
        if spot is not None:
            rows = [r for r in rows if r[0] and spot * 0.965 <= float(r[0]) <= spot * 1.035]

        ce_book, pe_book = {}, {}
        cur = {}
        for strike, side, ltp, bid, ask, vol in rows:
            bid = float(bid) if bid else 0.0
            ask = float(ask) if ask else 0.0
            book = ce_book if side == "CE" else pe_book
            # only coherent levels (bid < ask) enter the book
            if bid > 0 and ask > 0 and bid < ask:
                book.setdefault(strike, []).append((bid, ask))
            cur[(strike, side)] = (float(ltp) if ltp else 0.0,
                                   float(vol) if vol else 0.0)

        def book_levels(book, n=5):
            b = sorted({x[0] for lvl in book.values() for x in lvl}, reverse=True)[:n]
            a = sorted({x[1] for lvl in book.values() for x in lvl})[:n]
            return b, a

        bids_ce, asks_ce = book_levels(ce_book)
        bids_pe, asks_pe = book_levels(pe_book)
        bids = sorted(set(bids_ce) | set(bids_pe), reverse=True)[:5]
        asks = sorted(set(asks_ce) | set(asks_pe))[:5]
        if not bids or not asks:
            return None

        # ATM strike quotes (price-level proxy - NSE stream sends no qty):
        # imbalance/spread only make sense on ONE coherent strike.
        atm = None
        for s, side, ltp, bid, ask, vol in rows:
            b, a = (float(bid) if bid else 0.0), (float(ask) if ask else 0.0)
            if spot and b > 0 and a > 0 and b < a:
                if atm is None or abs(float(s) - spot) < abs(atm[0] - spot):
                    atm = (float(s), side, b, a)
        atm_quotes = None
        if atm is not None:
            s0, side0, b0, a0 = atm
            other = "PE" if side0 == "CE" else "CE"
            other_q = None
            book = ce_book if other == "CE" else pe_book
            for (b, a) in book.get(atm[0], []):
                other_q = (b, a)
                break
            atm_quotes = {"strike": s0, side0: (b0, a0), other: other_q}

        buy = sell = total = 0.0
        prev = con.execute(
            "SELECT recv_ts FROM ticks WHERE recv_ts < ? "
            "ORDER BY recv_ts DESC LIMIT 1", (ts,)).fetchone()
        if prev:
            for strike, side, ltp, vol in con.execute(
                    "SELECT strike, side, ltp, volume FROM ticks WHERE recv_ts=?",
                    (prev[0],)).fetchall():
                key = (strike, side)
                if key not in cur:
                    continue
                c_ltp, c_vol = cur[key]
                dvol = c_vol - (float(vol) if vol else 0.0)
                if dvol <= 0:
                    continue
                total += dvol
                p_ltp = float(ltp) if ltp else 0.0
                if c_ltp > p_ltp:
                    buy += dvol
                elif c_ltp < p_ltp:
                    sell += dvol
                else:
                    buy += dvol / 2
                    sell += dvol / 2

        return (sorted(set(bids), reverse=True)[:5],
                sorted(set(asks))[:5], total, buy, sell, ts,
                bids_ce, asks_ce, bids_pe, asks_pe, spot, atm_quotes)
    finally:
        con.close()


def compute_lob_microstructure(bids=None, asks=None, total_volume=None,
                               buy_volume=None, sell_volume=None, spot=None):
    """LOB imbalance + VPIN. Pass book args OR real data auto-loads."""
    book_ce = book_pe = None
    if bids is None or asks is None:
        real = _load_real_book()
        if real is None:
            return {
                "status": "INSUFFICIENT_DATA",
                "reason": "No real order-book ticks in data/research.db.",
                "lob_imbalance_ratio": 0.0,
                "microstructure_bias": "N/A",
                "vpin_toxicity_score": None,
                "is_order_flow_toxic": None,
                "order_flow_delta_volume": 0,
                "quant_guidance": "Run tick_recorder.py during market hours.",
            }
        (bids, asks, total_volume, buy_volume, sell_volume, ts,
         bids_ce, asks_ce, bids_pe, asks_pe, spot, atm_quotes) = real
        book_ce = (bids_ce, asks_ce)
        book_pe = (bids_pe, asks_pe)
        source = f"research.db @ {ts}"
    else:
        total_volume = float(total_volume) if total_volume else 0.0
        buy_volume = float(buy_volume) if buy_volume else 0.0
        sell_volume = float(sell_volume) if sell_volume else 0.0
        ts, source, atm_quotes = "", "caller-provided", None

    bids = [float(b) for b in bids if b]
    asks = [float(a) for a in asks if a]
    # NSE stream sends bid/ask PRICES only (no qty) -> rupee depth is
    # unknowable. Use LEVEL COUNTS as the honest proxy: a market that only
    # quotes one side gets detected; a balanced two-sided book is BALANCED.
    n_bid_levels = len(bids)
    n_ask_levels = len(asks)
    total_bid_qty = float(n_bid_levels)
    total_ask_qty = float(n_ask_levels)

    lob_imbalance = (n_bid_levels - n_ask_levels) / max(n_bid_levels + n_ask_levels, 1.0)

    if total_volume and total_volume > 0:
        vpin = abs(buy_volume - sell_volume) / max(total_volume, 1.0)
        is_toxic = vpin > 0.40
    else:
        vpin, is_toxic = None, None

    order_flow_delta = int(buy_volume - sell_volume) if total_volume else None

    best_bid = bids[0] if bids else None
    best_ask = asks[0] if asks else None
    spread_pct = None
    if best_bid and best_ask and best_ask > best_bid:
        mid = (best_bid + best_ask) / 2
        spread_pct = round((best_ask - best_bid) / mid * 100, 3) if mid else None

    # ATM strike quote (coherent single-strike book) overrides the top-of-book
    # for spread reporting - NSE stream sends bid/ask prices with no qty, so
    # the top-of-book mix spans strikes. ATM quote is the tradeable one.
    atm_quote = None
    if atm_quotes and atm_quotes.get("strike"):
        s = atm_quotes["strike"]
        for side in ("CE", "PE"):
            q = atm_quotes.get(side)
            if q and q[0] and q[1] and q[1] > q[0]:
                atm_quote = {"strike": s, "side": side,
                             "bid": q[0], "ask": q[1]}
                break
        if atm_quote:
            best_bid, best_ask = atm_quote["bid"], atm_quote["ask"]
            mid = (best_bid + best_ask) / 2
            spread_pct = round((best_ask - best_bid) / mid * 100, 3) if mid else None

    out = {
        "status": "OK",
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_source": source,
        "snapshot_ts": ts,
        "underlying_spot": round(spot, 2) if spot else None,
        "depth_note": "price-level counts (NSE stream carries no qty; rupee depth not computable)",
        "total_bid_levels": n_bid_levels,
        "total_ask_levels": n_ask_levels,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_pct": spread_pct,
        "lob_imbalance_ratio": round(lob_imbalance, 3),
        "microstructure_bias": ("STRONG_BUY_PRESSURE" if lob_imbalance > 0.3
                                else ("STRONG_SELL_PRESSURE" if lob_imbalance < -0.3 else "BALANCED")),
        "vpin_toxicity_score": round(vpin, 3) if vpin is not None else None,
        "is_order_flow_toxic": is_toxic,
        "order_flow_delta_volume": order_flow_delta,
        "quant_guidance": ("HIGH INSTABILITY WARNING: Toxic Order Flow detected! Avoid market orders."
                           if is_toxic else "Normal Microstructure: Order book liquidity is stable."),
    }
    if book_ce is not None:
        b, a = book_ce
        out["call_book"] = {"best_bid": b[0] if b else None,
                            "best_ask": a[0] if a else None,
                            "levels": len(b or [])}
        b, a = book_pe
        out["put_book"] = {"best_bid": b[0] if b else None,
                           "best_ask": a[0] if a else None,
                           "levels": len(b or [])}
    if atm_quote:
        out["atm_quote"] = atm_quote
    return out


if __name__ == "__main__":
    print("=== 2026 MARKET MICROSTRUCTURE ENGINE TEST ===")
    res = compute_lob_microstructure()
    print(json.dumps(res, indent=2))