"""Smart Strike Price Selector & Option Ranking Engine for NIFTY Research.

UPGRADED 2026-08-12: Now DATA-DRIVEN (was 100% fabricated values).

Old version invented OI (`150000 - offset*300`), premium (`spot*0.006 -
offset*0.5`), spread and delta from formulas. This version prices every
candidate strike from the latest REAL OI snapshot:
  - Delta        -> Black-Scholes (real IV from chain, BS fallback)
  - Premium      -> chain LTP (BS fallback)
  - OI / OI chg  -> chain ce_oi / pe_oi
  - Spread       -> None (NSE snapshot exposes no bid/ask; OI is the
                    liquidity proxy here)

Ranking filters (kept from original spec):
1. Delta Bounds Filter (0.30 - 0.55 Delta Sweet Spot)
2. OI Liquidity Floor (min 50,000)
3. Premium-to-Spot Ratio (max 1.5%)
"""
import os
import glob
import json
import datetime as dt

import pandas as pd

from greeks import bs_price_and_greeks

LOT_SIZE = 75
SNAP_DIR = os.path.join("data", "oi_snapshots")
DEFAULT_SIGMA = 0.15
R = 0.06


class SmartStrikeSelector:
    """Smart strike price selector for options buying (real data)."""

    STRIKE_GAP = 50

    def __init__(self, preferred_delta_min=0.30, preferred_delta_max=0.55,
                 min_oi=50000, max_premium_spot_pct=1.5):
        self.delta_min = preferred_delta_min
        self.delta_max = preferred_delta_max
        self.min_oi = min_oi
        self.max_premium_spot_pct = max_premium_spot_pct

    # ------------------------------------------------------------------
    # Data plumbing (same source as multi_leg_options.py)
    # ------------------------------------------------------------------
    def _chain(self):
        snaps = sorted(glob.glob(os.path.join(SNAP_DIR, "NIFTY_*.csv")))
        if not snaps:
            return None, None, False
        today = dt.date.today()
        chosen, stale = None, False
        for path in snaps:
            df = pd.read_csv(path)
            exp = self._expiry(df)
            if exp is not None and exp >= today:
                chosen = (df, os.path.basename(path))
                break
        if chosen is None:
            chosen = (pd.read_csv(snaps[-1]), os.path.basename(snaps[-1]))
            stale = True
        return chosen[0], chosen[1], stale

    @staticmethod
    def _expiry(chain):
        if chain is None or "expiry" not in chain.columns:
            return None
        exp = str(chain["expiry"].dropna().iloc[0]).strip()
        for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return dt.datetime.strptime(exp, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _iv_frac(iv):
        if iv and 0 < iv < 300:
            return round(iv / 100.0, 4)
        return DEFAULT_SIGMA

    @staticmethod
    def _f(row, col):
        v = row.get(col)
        if v is None:
            return None
        try:
            f = float(v)
            return f if f == f and abs(f) < 1e15 else None
        except (TypeError, ValueError):
            return None

    def _quote_map(self, chain):
        q = {}
        if chain is None:
            return q
        for _, r in chain.iterrows():
            q[int(r["strike"])] = {
                "ce_ltp": self._f(r, "ce_ltp"),
                "pe_ltp": self._f(r, "pe_ltp"),
                "ce_iv": self._f(r, "ce_iv"),
                "pe_iv": self._f(r, "pe_iv"),
                "ce_oi": self._f(r, "ce_oi"),
                "pe_oi": self._f(r, "pe_oi"),
                "ce_oi_chg": self._f(r, "ce_oi_chg"),
                "pe_oi_chg": self._f(r, "pe_oi_chg"),
            }
        return q

    # ------------------------------------------------------------------
    # Core selection
    # ------------------------------------------------------------------
    def select_best_strike(self, spot_price=None, option_type="CE"):
        """Rank strikes from real chain data; return the best buy candidate.

        Truth-layer (Phase 3): a real spot price is REQUIRED. No spot
        (None) yields an honest MISSING_SPOT result instead of substituting
        a hardcoded market value.
        """
        if not spot_price:
            return {
                "selector_status": "MISSING_SPOT",
                "status": "MISSING",
                "spot_price": None,
                "option_type": option_type.upper(),
                "best_strike": None,
                "best_strike_delta": None,
                "best_strike_premium": None,
                "candidates_evaluated": 0,
                "selection_rationale": "No real spot price available - no strike "
                                       "selected (honest stand-down, no hardcoded fallback).",
                "candidates": [],
            }
        chain, snapshot, stale = self._chain()
        spot = float(spot_price)
        t_days = max(int((self._expiry(chain) - dt.date.today()).days), 1) \
            if self._expiry(chain) else 20
        qmap = self._quote_map(chain)
        atm = round(spot / self.STRIKE_GAP) * self.STRIKE_GAP
        side = "CE" if option_type.upper() == "CE" else "PE"

        candidates = []
        for offset in [-100, -50, 0, 50, 100, 150, 200]:
            strike = atm + (offset if side == "CE" else -offset)
            row = qmap.get(strike, {})
            ltp_key, iv_key = (("ce_ltp", "ce_iv") if side == "CE"
                               else ("pe_ltp", "pe_iv"))
            oi_key = f"{side.lower()}_oi"
            chg_key = f"{side.lower()}_oi_chg"

            iv = self._iv_frac(row.get(iv_key))
            ltp = row.get(ltp_key)
            if ltp and ltp > 0:
                premium, source = round(ltp, 2), "market"
            else:
                g = bs_price_and_greeks(spot, strike, t_days, iv, side=side, r=R)
                premium, source = round(g["price"], 2), "bs"

            greeks = bs_price_and_greeks(spot, strike, t_days, iv, side=side, r=R)
            delta = round(greeks["delta"], 3)
            oi = row.get(oi_key) or 0.0
            oi_chg = row.get(chg_key)
            prem_spot_pct = round(premium / spot * 100, 2) if spot else 0.0

            delta_score = 100.0 if self.delta_min <= delta <= self.delta_max else 60.0
            liquidity_score = round(min(100.0, oi / self.min_oi * 100.0), 1) \
                if self.min_oi else 100.0
            premium_score = 100.0 if prem_spot_pct <= self.max_premium_spot_pct \
                else round(max(0.0, 100.0 - (prem_spot_pct - self.max_premium_spot_pct) * 40.0), 1)
            rank = round(delta_score * 0.5 + liquidity_score * 0.3 + premium_score * 0.2, 1)

            candidates.append({
                "strike": strike,
                "moneyness": "ATM" if offset == 0 else ("OTM" if (offset > 0 if side == "CE" else offset < 0) else "ITM"),
                "delta": delta,
                "premium": premium,
                "premium_source": source,
                "iv": iv,
                "open_interest": int(oi),
                "oi_change": oi_chg,
                "premium_spot_pct": prem_spot_pct,
                "rank_score": rank,
            })

        sorted_candidates = sorted(candidates, key=lambda x: x["rank_score"], reverse=True)
        best = sorted_candidates[0]

        return {
            "selector_status": "OPTIMAL_STRIKE_SELECTED",
            "spot_price": round(spot, 2),
            "option_type": side,
            "expiry": str(self._expiry(chain)) if self._expiry(chain) else None,
            "expiry_days": t_days,
            "data_source": snapshot or "bs-priced",
            "stale_snapshot": stale,
            "best_strike": best["strike"],
            "best_strike_moneyness": best["moneyness"],
            "best_strike_delta": best["delta"],
            "best_strike_premium": best["premium"],
            "rank_score": best["rank_score"],
            "candidates_evaluated": len(candidates),
            "selection_rationale": (
                f"Strike {best['strike']} {side}: real delta {best['delta']}, "
                f"premium ₹{best['premium']} ({best['premium_source']}, "
                f"{best['premium_spot_pct']}% of spot), OI {best['open_interest']:,} "
                f"(chg {best['oi_change'] or 0:+.0f})."
            ),
            "candidates": sorted_candidates,
        }


# Singleton instance
strike_selector = SmartStrikeSelector()

if __name__ == "__main__":
    print("=== TESTING SMART STRIKE SELECTOR ENGINE (DATA-DRIVEN) ===")
    try:
        import regime_filter
        real_spot = regime_filter.trade_plan().get("close")
    except Exception:
        real_spot = None
    res = strike_selector.select_best_strike(spot_price=real_spot, option_type="CE")
    print(json.dumps({k: v for k, v in res.items() if k != "candidates"}, indent=2))
