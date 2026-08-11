# ⚡ NIFTY Multi-Asset Quant Platform & 2026 AI Swarm Architecture

An institutional-grade, local-first quantitative trading and research platform for the Indian and global markets (**Nifty 50 / Bank Nifty / FinNifty / Equities / MCX Commodities / Global Indices**). 

Combines **2026 Multi-Agent Swarm Intelligence (`multi_agent_swarm.py`)**, **Prop-Desk Capital Protection (`capital_guard.py`)**, **Profit Generation Engine (`profit_engine.py`)**, **Smart Money Concepts (`smc_intelligence.py`)**, and **46-Year Multi-Decade Backtesting (`long_term_backtest.py`)**.

> 🛑 **Capital Preservation & Profitability First**: SEBI FY26 data shows retail traders lost ₹91,685 Crore in F&O. This engine is engineered to protect capital using 3% daily kill-switches, 0DTE expiry trap blocks, and positive expected value (+EV) filters.

---

## 🤖 2026 Cutting-Edge Technologies & Module Map

| Module | Category | Capabilities & Features |
|---|---|---|
| **`multi_agent_swarm.py`** | 🤖 **2026 AI Swarm** | Deploys 4 Specialized Subagents: Macro Agent, Microstructure Agent, Capital Guard Agent, and Executive Swarm Leader. |
| **`lob_microstructure.py`** | ⚡ **Microstructure** | Limit Order Book (LOB) Imbalance Ratio & Volume-Synchronized Probability of Toxicity (VPIN) score. |
| **`anti_spoofing.py`** | 🛡️ **Anti-Spoofing** | Detects institutional fake liquidity walls, quote stuffing, and sudden order cancellations. |
| **`profit_engine.py`** | 💰 **Profit Engine** | Master Profit Generator enforcing Positive Expectancy (+EV), 1:2.0 Minimum RRR, and ATR Profit Trailing. |
| **`expectancy_calculator.py`** | 🧮 **Mathematical Edge** | Calculates Expected Value (EV) per Rupee Risk over 100-trade sequences. |
| **`dynamic_trailing.py`** | 📈 **Profit Trailing** | 2.5x ATR Chandelier Exit locking +50% and +150% profits as price moves. |
| **`live_trader_brain.py`** | 🧠 **Intellectual Brain** | Synthesizes Psychology, SMC, Monte Carlo Risk, Super-AI ML, and Capital Guard into 1 Decision. |
| **`trader_psychology.py`** | 🧘 **Psychology Guard** | Prevents FOMO chasing, Revenge Trading tilt, Over-confidence, and Lot Size inflation. |
| **`smc_intelligence.py`** | 🏛️ **Smart Money (SMC)** | Identifies Fair Value Gaps (FVG), Demand/Supply Order Blocks (OB), and Market Structure Shifts (MSS). |
| **`monte_carlo.py`** | 🎲 **Monte Carlo** | Runs 10,000 Statistical Trade Sequence Simulations for 100% Account Survival Verification. |
| **`pattern_recognition.py`** | 🔍 **Pattern Engine** | Identifies Double Bottom (W), Double Top (M), Head & Shoulders, Engulfing, Hammer, and Doji candles. |
| **`mcp_pattern_bridge.py`** | 🔌 **MCP Bridge** | Logs recognized patterns into SQLite MCP (`data/research.db`) table `pattern_logs`. |
| **`long_term_backtest.py`** | 📜 **46-Year Backtest** | Multi-timeframe backtest engine across 46 Years (1980–2026 | 11,747 bars) surviving 1987, 2000, 2008, 2020 crashes. |
| **`super_ai_ml.py`** | 🧠 **Super-AI ML** | Multi-model ML ensemble combining **XGBoost**, **LightGBM**, and **Random Forest** classifiers. |
| **`capital_guard.py`** | 🛡️ **Capital Preservation**| Prop-desk 3% Daily Loss Kill-Switch, 0DTE Expiry Trap Filter (13:30 IST cutoff), and Event IV Crush Guard. |
| **`precision_signals.py`** | 🎯 **Signal Engine** | 6-Layer High Confluence Noise Filter. Issues ONLY A+ Grade Signals with exact Entry, Strike, SL, and Target levels. |
| **`voice_coach.py`** | 🎙️ **Voice Assistant** | Real-time Hinglish audio alerts and risk warnings spoken out loud during market hours. |
| **`gamma_flip.py`** | 🧠 **Hedge Fund GEX** | Calculates Market Maker Net Gamma Exposure, exact **Gamma Flip Strike**, and Liquidity Sweep Pools. |
| **`web_dashboard.py`** | 🖥️ **Live Visual Terminal**| Dark-themed live browser dashboard generated at `blog/live_terminal.html`. |

---

## 🔑 Broker Credentials Setup (`.env`)

Create a local `.env` file in the project root (use `.env.example` template):

```ini
# Angel One SmartAPI Credentials (LOCAL ONLY)
ANGEL_API_KEY=your_api_key
ANGEL_CLIENT_CODE=your_client_code
ANGEL_PASSWORD=your_pin_or_password
ANGEL_TOTP_SECRET=your_totp_secret
```

*.env and data/research.db are strictly ignored in `.gitignore` to guarantee credential safety.*

---

## ⚡ Master Execution Commands

### 1. One-Click Master Launcher (Executes All Engines):
```bash
python3 run_all.py
```

### 2. Run 2026 Autonomous Multi-Agent Trading Swarm:
```bash
python3 multi_agent_swarm.py
```

### 3. Run Master Decision Brain Synthesis:
```bash
python3 live_trader_brain.py
```

### 4. Run Master Profit Generation Engine:
```bash
python3 profit_engine.py
```

### 5. Run 46-Year Multi-Timeframe Backtest (1980 - 2026):
```bash
python3 long_term_backtest.py
```

---

## 📜 License & Disclaimer

Educational and quantitative research platform. Financial markets carry risk. Never risk capital you cannot afford to lose. Perform independent verification before placing orders.
