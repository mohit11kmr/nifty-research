# 📊 OPTION TRADERS MASTER INTELLIGENCE GUIDE & DAILY BLUEPRINT

**Engine:** `nifty-research` Multi-Asset Quant Platform  
**Target Market:** NSE Nifty 50, Bank Nifty, FinNifty Options  
**Broker Integration:** Angel One SmartAPI (`M450789` - MOHIT KUMAR)

---

## 🎯 1. OPTION BUYING VS SELLING DECISION MATRIX (India VIX)

| India VIX Range | Market Regime | Best Option Strategy | Risk Type | Position Size |
|---|---|---|---|:---:|
| **< 12.0** | `CHEAP PREMIUM` | **Long Call / Long Put** | Limited Debit | 1.0x |
| **12.0 – 16.0** | `NORMAL PREMIUM` | **Bull Call Spread / Bear Put Spread** | Defined Risk | 1.0x |
| **16.0 – 20.0** | `RICH PREMIUM` | **Iron Condor / Credit Spreads** | Defined Risk | 0.8x |
| **20.0 – 25.0** | `HIGH VOLATILITY` | **Aggressive Iron Condor / Short Spreads** | Defined Risk | 0.5x |
| **> 25.0** | `PANIC VOLATILITY` | **Mean-Reversion Spreads / Cash / Sit Out** | High Risk | 0.25x / 0x |

---

## ⏱️ 2. INTRADAY TIMING & EXPIRY WINDOWS

| Time Window (IST) | Market Phase | Actionable Rule for Option Traders |
|---|---|---|
| **09:15 – 09:45** | **Opening Range Breakout (ORB)** | High Volatility — Trade 15-min range break with tight SL. |
| **09:45 – 11:00** | **Institutional OI Build-Up** | Best window for Options Buying & Directional Spreads. |
| **11:00 – 13:00** | **Mid-Day Consolidation** | Fade extremes at Call/Put Walls. |
| **13:00 – 14:30** | **Lunch Lull** | Avoid fresh naked option buying (theta decay risk). |
| **13:30 (Expiry)** | **0DTE Cutoff Gate** | 🛑 **NO NAKED BUYING AFTER 13:30 IST** on Expiry Day! |
| **14:30 – 15:15** | **Power Hour** | Strong directional push before close. |

---

## 📊 3. OPTION CHAIN METRICS CHEAT SHEET

### Put-Call Ratio (PCR)
- **PCR > 1.30**: Put Heavy → Writers building support → **Bullish OI Bias**
- **PCR 0.80 – 1.20**: Balanced → Sideways Range
- **PCR < 0.80**: Call Heavy → Writers building resistance → **Bearish OI Bias**

### Max Pain Level
- Option buyers का maximum payout loss level.
- Expiry Day par Nifty spot price Max Pain level ke taraf gravitation magnet ki tarah pull hota hai.

### Option Walls (Support & Resistance)
- **Call Wall (Highest CE OI)** = Major Resistance Ceiling (Short sellers capped upside).
- **Put Wall (Highest PE OI)** = Major Support Floor (Short sellers capped downside).

---

## 🧮 4. BLACK-SCHOLES GREEKS CHEAT SHEET FOR TRADERS

| Greek | What it Measures | Rule for Option Buyers | Rule for Option Sellers |
|---|---|---|---|
| **Delta** | Spot movement sensitivity | ATM ≈ 0.50 (Buy ATM/ITM, avoid deep OTM) | Short ITM/ATM carries high delta risk |
| **Gamma** | Delta rate of change | High near expiry → Violent moves | High Gamma = High Risk near expiry |
| **Theta** | Daily time decay (₹) | Enemy #1 (Decays daily) | Best Friend (Earns daily decay) |
| **Vega** | IV sensitivity (₹ per 1% IV) | High IV = Options expensive | Sell High IV, Buy Low IV |

---

## 🛡️ 5. CAPITAL GUARD PROTECTION RULES (`capital_guard.py`)

1. **Daily Loss Kill-Switch:** Max 3.0% daily account loss limit. If hit → LOCK TRADING.
2. **Fixed 1% Capital Risk Limit:** Maximum loss per trade strictly ≤ 1% of capital.
3. **0DTE Hero-Zero Protection:** No naked buying after 13:30 IST on expiry.
4. **Event Risk Protection:** No naked buying 24h before RBI / Budget / FED decisions.
5. **Drawdown De-risking:** Position size cut by 50% if account drawdown ≥ 5%.

---

## 🚀 6. ACTIONABLE OPENCODE COMMANDS

- **Run High-Precision Signal:** `python3 precision_signals.py`
- **Run Full Systematic Dashboard:** `python3 systematic_report.py`
- **Run Capital Guard Safety Audit:** `python3 capital_guard.py`
- **Run OpenCode AI Engine:** `opencode run "Aaj ka NIFTY trade setup batao." --auto`
