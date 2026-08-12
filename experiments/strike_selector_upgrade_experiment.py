"""EXPERIMENT: Fake-data vs Real-data Smart Strike Selector.

Old version invented OI/premium/delta/spread. New version prices every
strike from the latest REAL NSE OI snapshot (BS fallback for missing LTP).

Compares both outputs for the same spot to show the upgrade impact.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smart_strike_selector import strike_selector


def old_fake_selector(spot_price=24403.10, option_type="CE"):
    """Replicates the PRE-upgrade fabricated logic (for comparison)."""
    atm = round(spot_price / 50) * 50
    candidates = []
    for offset in [-100, -50, 0, 50, 100, 150, 200]:
        strike = atm + (offset if option_type == "CE" else -offset)
        if offset == 0:
            approx_delta = 0.50
        elif offset > 0:
            approx_delta = max(0.20, 0.50 - (offset / 500.0))
        else:
            approx_delta = min(0.80, 0.50 + (abs(offset) / 500.0))
        approx_premium = round(max(30.0, spot_price * 0.006 - (offset * 0.5)), 2)
        bid_ask_spread_pct = round(0.5 + (offset * 0.01), 2)
        open_interest = 150000 - (abs(offset) * 300)
        delta_score = 100.0 if 0.30 <= approx_delta <= 0.55 else 50.0
        liquidity_score = 100.0 if (bid_ask_spread_pct <= 3.0 and open_interest >= 50000) else 40.0
        rank = round(delta_score * 0.6 + liquidity_score * 0.4, 1)
        candidates.append((strike, approx_delta, approx_premium, open_interest, rank))
    candidates.sort(key=lambda x: x[4], reverse=True)
    return candidates[0], candidates


SPOT = 24435.95

print("=" * 74)
print("EXPERIMENT: OLD (fabricated) vs NEW (real OI snapshot) strike selector")
print("=" * 74)
old_best, old_cands = old_fake_selector(SPOT, "CE")
new = strike_selector.select_best_strike(spot_price=SPOT, option_type="CE")

print(f"\nSpot: {SPOT:,.2f} | Snapshot: {new['data_source']} | Stale: {new['stale_snapshot']}")
print(f"\n--- BEST STRIKE ---")
print(f"{'':20}{'OLD (fake)':>24}{'NEW (real)':>24}")
print(f"{'strike':20}{old_best[0]:>24}{new['best_strike']:>24}")
print(f"{'delta':20}{old_best[1]:>24}{new['best_strike_delta']:>24}")
print(f"{'premium':20}{old_best[2]:>24}{new['best_strike_premium']:>24}")
print(f"{'OI':20}{old_best[3]:>24,}{new.get('candidates', [{}])[0]['open_interest']:>24,}")
print(f"{'rank':20}{old_best[4]:>24}{new['rank_score']:>24}")

print("\n--- OLD candidates (ALL fabricated OI = 150000-ish, premium = formula) ---")
print(f"{'strike':>7} {'delta':>7} {'prem':>8} {'OI':>9} {'rank':>6}")
for s, d, p, oi, r in old_cands:
    print(f"{s:>7} {d:>7} {p:>8} {oi:>9,} {r:>6}")

print("\n--- NEW candidates (REAL OI / real premium / BS delta) ---")
print(f"{'strike':>7} {'delta':>7} {'prem':>8} {'src':>6} {'OI':>9} {'OIchg':>8} {'rank':>6}")
for c in new["candidates"]:
    print(f"{c['strike']:>7} {c['delta']:>7} {c['premium']:>8} {c['premium_source']:>6} "
          f"{c['open_interest']:>9,} {c['oi_change'] if c['oi_change'] is not None else 0:>8.0f} {c['rank_score']:>6}")

print("\n--- VERDICT ---")
old_oi, new_oi = old_best[3], new["candidates"][0]["open_interest"]
print(f"Old selector picked strike {old_best[0]} quoting FABRICATED OI {old_oi:,} "
      f"and fake premium ₹{old_best[2]}.")
print(f"New selector picked strike {new['best_strike']} using REAL OI {new_oi:,} "
      f"and real premium ₹{new['best_strike_premium']} (source: {new['data_source']}).")
print("Impact: paper/live orders previously entered at made-up prices and OI ->")
print("the upgraded selector ranks on actual liquidity & BS delta.")
