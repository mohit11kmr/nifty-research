---
name: oi-intel
description: NIFTY options chain ka OI (Open Interest) analysis karna — max pain, PCR, OI walls, Murarkar matrix, gamma flip, Greeks (delta/gamma/theta/vega) interpret karna. Use karo jab user option chain ya OI ke baare me pooche.
---

# OI Intelligence Skill

## Data Access — MCP Tools (PREFERRED)

`nifty-trader` MCP se direct cached chain analysis lo:
- `option_chain_intel` → PCR, max pain, OI walls, Murarkar matrix
- `gamma_flip_intel` → gamma flip strike, long/short gamma regime, liquidity pools
- `market_snapshot` → chain + saara context ek sath

Agar MCP na ho, `python3 -c` se `oi_intel` use karo. SQLite `ticks` table ke liye `sqlite-nifty` MCP use karo.

## OI Analysis Framework

### Key Concepts

#### PCR (Put-Call Ratio)
```
PCR = Total Put OI / Total Call OI
```
| PCR Value | Meaning |
|---|---|
| PCR > 1.3 | Put Heavy → Bullish OI bias (writers expect support) |
| PCR 0.8–1.2 | Balanced → Sideways expected |
| PCR < 0.7 | Call Heavy → Bearish OI bias (writers expect resistance) |

#### Max Pain
> The strike price where the total payout to option BUYERS is MINIMUM
> = option sellers' favorite level; market gravitates here near expiry

**Correct Formula:**
```
For each strike S:
  CE holders get: max(0, SPOT - K) for all K ≤ SPOT
  PE holders get: max(0, K - SPOT) for all K ≥ SPOT
Max Pain = Strike that MINIMIZES total payout
```
*(Note: Argmin, NOT argmax — this was a bug that was fixed in this project)*

#### OI Walls
- **Call Writing Wall** (High CE OI) = Strong resistance zone
- **Put Writing Wall** (High PE OI) = Strong support zone
- Market typically oscillates between major OI walls

### Murarkar Matrix (oi_intel.py)

4 patterns based on Price vs OI change:

| Pattern | Price | OI | Interpretation |
|---|---|---|---|
| **Call Writing** | ↑ | CE OI ↑ | Writers adding shorts → Supply ceiling → **BEARISH** |
| **Put Writing** | ↓ | PE OI ↑ | Writers adding shorts → Demand floor → **BULLISH** |
| **Call Unwinding** | ↑ | CE OI ↓ | Short sellers covering → Fuel for rally → **BULLISH** |
| **Put Unwinding** | ↓ | PE OI ↓ | Put buyers exiting → Weak signal → **BEARISH** |

### Gamma Flip (gamma_flip.py)
- **GEX = Call OI × Γ_CE − Put OI × Γ_PE** (per strike)
- **Gamma Flip Strike** = jahan cumulative GEX zero cross hota hai
- Price **above** flip → Market makers stabilize (dip buying works)
- Price **below** flip → Short gamma, moves accelerate (volatility risk)

### Greeks Interpretation (greeks.py — Black-Scholes)

| Greek | What it means | Trading use |
|---|---|---|
| **Delta** | Price change per ₹1 spot move | ATM ≈ 0.5, Deep ITM ≈ 1.0 |
| **Gamma** | Delta change rate | High near expiry → risky |
| **Theta** | Daily time decay (₹) | Positive for sellers, negative for buyers |
| **Vega** | IV change sensitivity | High = options expensive relative to HV |

#### IV/HV Ratio
```
IV/HV < 1.0 → Options CHEAP → BUY side (long spreads)
IV/HV 1.0–1.4 → Fair value
IV/HV > 1.4 → Options EXPENSIVE → SELL side (iron condor, credit spreads)
```

## Common OI Patterns to Watch

### 1. "Max Pain Magnet" Setup
- PCR neutral (0.9–1.1), price far from max pain, near expiry (1–2 days)
- → Market likely to drift toward max pain

### 2. "Call Wall Rejection"
- Large CE OI at nearby strike, price approaching from below
- Murarkar: Call Writing active → high probability of stall at that strike

### 3. "Support Floor Hold"
- Large PE OI at nearby strike below, price near that level
- Murarkar: Put Writing active → strong support, puts expensive

### 4. "OI Unwind + Trend"
- Both CE and PE OI decreasing, price trending strongly
- → Trend continuation likely (no writer resistance/support)

## Caveats
> ⚠️ OI spike detection ke liye 6+ days history chahiye (snapshots accumulate
> daily via build_data.py). Abhi 2-3 snapshots hain — spike reads partial hain.
