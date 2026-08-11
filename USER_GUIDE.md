# 📖 NIFTY QUANT PLATFORM — DAILY USER OPERATING GUIDELINE

**Welcome to the User Guide for your NIFTY Multi-Asset Quant Platform.**  
This guide details the exact step-by-step workflow to use the platform for pre-market research, live intraday trading, risk management, and post-market analysis.

---

## ⏰ DAILY OPERATING TIMELINE SUMMARY

```
08:30 IST ───► Pre-Market Routine (python3 run_all.py)
09:15 IST ───► Market Open & Opening Range Breakout (ORB)
09:45 IST ───► Institutional OI Build-Up & Precision Signal Scan (python3 precision_signals.py)
13:30 IST ───► 🛑 0DTE Expiry Cutoff (No Naked Buying)
15:30 IST ───► Market Close & Post-Market Summary (python3 systematic_report.py)
```

---

## 🌅 STEP 1: PRE-MARKET ROUTINE (08:30 – 09:00 IST)

Pehle subah market khulne se pehle ye steps follow karein:

### Command:
```bash
cd ~/Desktop/nifty-research
python3 run_all.py
```

### Checklist to Review:
1. **Regime Gate Check:**
   - `TREND_HV` / `TREND_LV` → ✅ **Trade Open (1.0x - 1.2x Sizing)**
   - `RANGE_LV` → ❌ **STAY OUT (0.0x Sizing — Low Volatility Chop)**
2. **Capital Guard Audit (`capital_guard.py`):**
   - Verify Kill-Switch is `OPEN` (0.0% Daily Loss).
   - Check if today is an Event Day (RBI Policy / Budget / FED).
3. **Open Visual Browser Terminal:**
   - Open [`blog/live_terminal.html`](file:///home/mohit/Desktop/nifty-research/blog/live_terminal.html) in Chrome or Firefox.

---

## ⚡ STEP 2: INTRADAY TRADING PROTOCOL (09:15 – 15:30 IST)

Live market hours ke dauran jab bhi setup check karna ho:

### 1. High-Precision Signal Scan:
```bash
python3 precision_signals.py
```
- **If Signal = `A+ GRADE (SUPER PRECISE)`**: Check exact Entry Zone, Strike (e.g. `24850 CE`), Stop Loss (`90 pts`), Target (`180 pts`).
- **If Signal = `NO_SIGNAL (FILTERED OUT NOISE)`**: **DO NOT TRADE**. Sit out and wait for high-confluence setups.

### 2. Check Gamma Flip Level:
```bash
python3 gamma_flip.py
```
- **Price Above Gamma Flip Strike (e.g., 24,550):** Market Makers stabilize market. Dip buying preferred.
- **Price Below Gamma Flip Strike:** Short Gamma volatility acceleration. Exercise caution.

### 3. Voice Coach Guidance:
```bash
python3 voice_coach.py
```
- Listen to real-time audio guidance in Hinglish regarding current market conditions and risk rules.

---

## 🛡️ STEP 3: NON-NEGOTIABLE RISK RULES

1. **1% Fixed Capital Risk Rule:**
   - Har trade par maximum loss strictly **1% of account capital** (e.g., ₹1,000 loss on ₹1 Lakh account).
2. **3% Daily Loss Kill-Switch:**
   - Agar din me ₹3,000 (3%) loss ho gaya → **STOP TRADING FOR THE DAY**. Close terminal.
3. **13:30 IST Expiry Cutoff:**
   - Expiry Day par 13:30 IST ke baad **Naked Call/Put buying BLOCKED**! Defined-risk Spreads (Iron Condor / Credit Spreads) only.

---

## 🗣️ STEP 4: OPENCODE NATURAL LANGUAGE COMMANDS

OpenCode CLI ya IDE chat box me aap ye commands pooch sakte hain:

- **Daily Setup:** `opencode run "Aaj ka NIFTY trade setup batao." --auto`
- **OI Analysis:** `opencode run "NIFTY PCR, Max Pain aur CE/PE Walls check karo." --auto`
- **Risk Audit:** `opencode run "Capital Guard Risk Audit run karke dikhao." --auto`

---

## 🌇 STEP 5: POST-MARKET ROUTINE (15:30 – 16:30 IST)

Market close hone ke baad daily performance aur data summary update karein:

```bash
python3 systematic_report.py
```
- Summary Report [`results/systematic_dashboard.md`](file:///home/mohit/Desktop/nifty-research/results/systematic_dashboard.md) me save ho jaayegi.

---

## 📂 FILE LOCATION QUICK REFERENCE

- **One-Click Launcher:** `run_all.py`
- **High-Precision Signals:** `precision_signals.py`
- **Voice Assistant:** `voice_coach.py`
- **Visual Web Terminal:** `blog/live_terminal.html`
- **Capital Protection Audit:** `capital_guard.py`
- **Master Decision Brain:** `live_trader_brain.py`
- **Long-Term 46-Year Backtest:** `long_term_backtest.py`
