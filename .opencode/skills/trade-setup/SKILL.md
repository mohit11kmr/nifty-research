---
name: trade-setup
description: NIFTY options, Equity, aur MCX commodities ke liye complete trade setup banana — entry, exit, position size, risk/reward, conviction score, aur SEBI capital preservation rules. Use karo jab user specific trade plan maange.
---

# Trade Setup & Capital Preservation Skill

Tu sirf RESEARCH assistant hai. Orders kabhi automatically mat lagana.
Hamesha user ko manual execution ke liye kaho (Angel One app/web).

## Data Access — MCP Tools (PREFERRED)

Trade setup banane ke liye ye tools ek hi baar me chalao:
1. `market_snapshot` — regime gate + VIX zone + chain intel + FII/DII + technicals
2. `capital_guard_audit` — 3% kill-switch + 0DTE trap + event risk + 1% sizing
3. `precision_signal` — 6-layer confluence signal (A+ / NO_SIGNAL)
4. `expiry_status` — kya aaj expiry day hai, 13:30 cutoff
5. `broker_status` — live positions/holdings dekhne ke liye

## SEBI & Prop-Desk Capital Preservation Rules (capital_guard.py)

> 🚨 SEBI Data: Retail F&O traders lost ₹91,685 Crore in FY26.
> Har trade setup me Capital Protection Rules STRICTLY enforce karo:

1. **Daily Loss Kill-Switch**: Max 3% daily account loss limit. If hit → NO MORE TRADES FOR DAY.
2. **Expiry 0DTE Hero-Zero Trap Guard**: After 13:30 IST on Expiry Day → NO Naked Call/Put Buying. Defined-risk spreads / Iron Condor only.
3. **Event Risk IV Crush Guard**: 24h before RBI Policy / Budget / FED → NO Naked Option Buying (IV Crush risk).
4. **Drawdown De-risking**: If account drawdown > 5% → cut position size multiplier by 50%.
5. **Fixed 1% Capital Risk Limit**: Maximum loss per trade must NOT exceed 1% of account capital.

## 5-Point Conviction Framework

Har trade setup me **5 checks** karo. Score batao.

### Check 1: Regime Gate (market_snapshot → regime)
- `TREND_HV` → ✅ OPEN (1.0x size)
- `TREND_LV` → ✅ OPEN (1.2x size)
- `RANGE_HV` → ⚠️ OPEN SMALL (0.7x, mean-rev only)
- `RANGE_LV` → ❌ BLOCKED (0x — don't trade)

### Check 2: VIX Zone (market_snapshot → vix)
- VIX < 12: CHEAP → Option Buying
- VIX 12–16: NORMAL → Directional Spreads
- VIX 16–20: RICH → Start Selling (Iron Condor)
- VIX 20–25: HIGH → Sell Aggressively
- VIX > 25: PANIC → Sit Out / Reduce Size

### Check 3: Capital Guard Audit (capital_guard_audit)
Kill-switch OPEN? Expiry trap clear? Event risk clear? Drawdown size multiplier?

### Check 4: OI Walls & IV Skew (option_chain_intel)
- PCR & Max Pain
- IV Skew Ratio (Put IV / Call IV)
- Gamma flip level vs current price

### Check 5: Technical Consensus (technical_consensus)
Multi-indicator bias + support/resistance alignment.

## Conviction Scoring
```
5/5 → HIGH → Strong setup
4/5 → MEDIUM-HIGH → Good setup, take trade
3/5 → MEDIUM → Small size, strict SL
2/5 → LOW → Skip
1/5 → NO → Definitely skip
```

## Position Sizing Rules

```
Trade Risk = Capital × 1%  (e.g. ₹1,00,000 → ₹1,000 max loss)
NIFTY lot = 75 units
Lots = Risk / (Premium diff entry→SL)
Regime multiplier: TREND_HV 1.0x, TREND_LV 1.2x, RANGE_HV 0.7x, RANGE_LV 0x
```

## Strategy Templates (VIX-based)

| VIX Zone | Strategy |
|---|---|
| < 12 CHEAP | Long ATM/ITM options, target 2x, stop 50% premium |
| 12–16 NORMAL | Directional spreads (bull call / bear put) |
| 16–20 RICH | Iron condor (~2% OTM shorts + 150pt wings), target +50% credit |
| 20–25 HIGH | Sell aggressive, smaller size |
| > 25 PANIC | Mean-revert or sit out |

## Output Format for Trade Setup

```
📊 TRADE SETUP & CAPITAL PROTECTION REPORT — [Date]

Conviction: X/5 (HIGH/MEDIUM/LOW)
🛡️ Capital Protection Status: APPROVED / DERISKED

✅ Regime Gate: TREND_HV (OPEN)
✅ VIX Zone: 18.2 (RICH — Premium Selling)
✅ Capital Guard: Kill-Switch Safe | Expiry Trap Clear | Event Risk Clear
✅ OI & Skew: PCR 0.72 | Skew Ratio 1.09 | Gamma Flip 24,550
✅ Technicals: 4/6 indicators agree

📋 SETUP: Defined-Risk Iron Condor / Spread
  BUY/SELL Legs...

🎯 Target: +50% Credit / 2x Reward
🛑 Stop Loss: Strict 1% Capital Risk (Max ₹1,000)
📅 Expiry Rule: Close 2 days before expiry

⚠️ Position Size: Exactly X Lot(s) (1% max risk compliant)
⚡ ACTION: MANUAL ORDER — Angel One app/web se lagao
```

## Risk Rules (Non-Negotiable)
1. Max 1% capital at risk per trade
2. RANGE_LV me ZERO trades
3. VIX > 25 me Iron Condor mat karo
4. Expiry ke 2 din pehle iron condor close karo
5. SL hit hone pe immediately exit — no averaging down, ever
6. Max 2 open positions at once
