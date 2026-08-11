# ⚡ NIFTY Multi-Asset Quant Engine & Capital Protection Suite

An institutional-grade, local-first quantitative research and trading platform for the Indian market (**Nifty 50 / Bank Nifty / FinNifty / Equities / MCX Commodities**). 

Combines **Prop-Desk Capital Preservation Rules (`capital_guard.py`)**, **Hedge Fund Gamma Exposure (`gamma_flip.py`)**, **5-Layer High-Precision Signal Filtering (`precision_signals.py`)**, **Interactive Hinglish Voice Coach (`voice_coach.py`)**, and **Angel One Broker Integration (`angel_one_client.py`)**.

> 🛑 **Capital Preservation First**: SEBI FY26 data shows retail traders lost ₹91,685 Crore in F&O. This engine is built to protect retail trader capital using strict 3% daily kill-switches, 0DTE expiry trap blocks, and event IV crush guards.

---

## 🚀 Key Modules & System Architecture

| Module | Purpose & Features |
|---|---|
| **`capital_guard.py`** | 🛡️ **Prop-Desk Capital Protection Suite**: 3% Daily Loss Kill-Switch, 0DTE Hero-Zero Trap Guard (blocks naked buying after 13:30 IST), Event IV Crush Guard, Drawdown De-risking Matrix (50% size cut at 5% DD). |
| **`precision_signals.py`** | 🎯 **5-Layer Confluence Signal Engine**: Filters out 90% noise. Issues ONLY `A+ Grade` signals with exact Entry Zone, Call/Put Strike, Stop-Loss points, and Targets. |
| **`voice_coach.py`** | 🎙️ **Interactive Audio Trading Assistant**: Speaks natural Hinglish alerts and risk warnings out loud during market hours. |
| **`gamma_flip.py`** | 🧠 **Hedge Fund GEX Engine**: Calculates Market Maker Net Gamma Exposure, exact **Gamma Flip Strike**, and Liquidity Sweep Pools. |
| **`web_dashboard.py`** | 🖥️ **Live Visual HTML Terminal**: Generates a sleek dark-themed interactive trading dashboard at `blog/live_terminal.html`. |
| **`skew.py`** | 📊 **Options Volatility Skew & Smile**: Computes Put IV / Call IV ratio & institutional downside hedging sentiment across NIFTY, BANKNIFTY, FINNIFTY. |
| **`equity_quant.py`** | 📈 **Mansfield Relative Strength (MRS)**: Scans Nifty 50 stocks outperforming Nifty 50 index + Sector Rotation Heatmap. |
| **`mcx_intel.py`** | 🛢️ **MCX Commodity Intelligence**: Tracks Gold, Silver, Crude Oil, Nat Gas, Dollar Index (DXY), and Gold/Silver Ratio extremes. |
| **`angel_one_client.py`** | 🔑 **Official SmartAPI Integration**: Session management via API Key, Client ID, PIN & TOTP (`pyotp`), order execution, and `SmartWebSocketV2` streaming. |
| **`empirical_proof.py`** | 🧪 **Mathematical Verification Suite**: Verifies Black-Scholes Greeks, Argmin Max Pain math, and walk-forward backtests. |
| **`systematic_report.py`** | 📑 **Structured Markdown Dashboard**: Generates clean table-formatted market reports at `results/systematic_dashboard.md`. |

---

## 🔑 Broker Credentials Setup (`.env`)

Create a `.env` file in the project root (see `.env.example` template):

```ini
# Angel One SmartAPI Credentials
ANGEL_API_KEY=your_api_key
ANGEL_CLIENT_CODE=your_client_code
ANGEL_PASSWORD=your_pin_or_password
ANGEL_TOTP_SECRET=your_totp_secret
```

*Note: `.env` and `data/research.db` are strictly listed in `.gitignore` to prevent credential exposure.*

---

## ⚡ Quick Start & Commands

### 1. Run High-Precision Signal Generator:
```bash
python3 precision_signals.py
```

### 2. Run Voice Coach Audio Alert:
```bash
python3 voice_coach.py
```

### 3. Generate Live HTML Visual Terminal:
```bash
python3 web_dashboard.py
# Open blog/live_terminal.html in your browser
```

### 4. Run Capital Guard Risk Audit:
```bash
python3 capital_guard.py
```

### 5. Run OpenCode AI Trading Commands:
```bash
opencode run "Aaj ke Market Regime aur Angel One profile ke mutabiq NIFTY trade setup batao." --auto
```

---

## 🛡️ Capital Protection Rules (`capital_guard.py`)

1. **Daily Loss Kill-Switch**: Max 3.0% daily account loss limit. If hit → LOCK TRADING for the day.
2. **0DTE Hero-Zero Protection**: No naked Call/Put buying after 13:30 IST on Expiry Days (95% expire worthless).
3. **Event Risk Protection**: No naked option buying 24h before RBI Policy / Budget / FED decisions due to IV crush.
4. **Drawdown De-risking**: Position size cut by 50% at 5% account drawdown, 75% at 10% drawdown.
5. **Fixed 1% Capital Risk**: Maximum loss per trade strictly ≤ 1% of account capital.

---

## 📜 License & Disclaimer

Educational and quantitative research platform. Markets carry inherent risk. Never risk money you cannot afford to lose. Always perform personal due diligence before executing orders.
