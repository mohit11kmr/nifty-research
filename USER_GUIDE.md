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

## 🌐 LIVE VISUAL TERMINAL URL (HTTP SERVER)

Chrome/Firefox me Terminal dekhne ke liye **http://127.0.0.1:8766/** ka upyog karein:

- **Primary Live Terminal URL (Recommended):** `http://127.0.0.1:8766/` (or `http://127.0.0.1:8766/live_terminal.html`)
- **Static File Backup:** `blog/live_terminal.html`

> 💡 *Note: `file://` URLs in Chrome block dynamic JavaScript auto-refresh due to browser security CORS policies. Always use `http://127.0.0.1:8766/` for full dynamic live terminal features.*

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
   - Open **http://127.0.0.1:8766/** in Chrome or Firefox.

---

## ⚡ STEP 2: INTRADAY TRADING PROTOCOL (09:15 – 15:30 IST)

Live market hours ke dauran jab bhi setup check karna ho:

### 1. Real-Time Market Spot Sync:
```bash
python3 live_market_fetch.py
```

### 2. High-Precision Signal Scan:
```bash
python3 precision_signals.py
```

### 3. Check Live Paper Trading Status:
```bash
python3 auto_paper_runner.py
```

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

- **Daily Setup:** `opencode run "/trade-setup" --auto`
- **Deep Research:** `opencode run "/deep-research Nifty Options Microstructure" --auto`
- **Auto Enhancement:** `opencode run "/auto-enhance" --auto`

---

## 📂 FILE LOCATION QUICK REFERENCE

- **Live Terminal Web Server:** `http://127.0.0.1:8766/`
- **One-Click Launcher:** `run_all.py`
- **High-Precision Signals:** `precision_signals.py`
- **Live Paper Trader:** `auto_paper_runner.py`
- **Permanent Audit Logger:** `history_logger.py`
