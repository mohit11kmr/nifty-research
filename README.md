<div align="center">

# ⚡ NIFTY Multi-Asset Quant Platform & Append-Only Audit Logger

**An Institutional-Grade, Local-First Quantitative Trading & Autonomous AI Swarm System for Nifty 50, Bank Nifty, FinNifty, Equities & MCX Commodities.**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Market: NSE & MCX](https://img.shields.io/badge/Market-NSE%20%7C%20MCX-orange.svg)](https://www.nseindia.com/)
[![Audit Logger: SQLite Active](https://img.shields.io/badge/Audit%20Logger-SQLite%20Active-brightgreen.svg)]()
[![Paper Trading: Active](https://img.shields.io/badge/Paper%20Trading-Active%20%E2%82%B91L-blue.svg)]()
[![AI Swarm: 2026 Active](https://img.shields.io/badge/AI%20Swarm-2026%20Active-green.svg)]()
[![Auto-Enhancer: RL Active](https://img.shields.io/badge/Auto--Enhancer-RL%20Active-purple.svg)]()
[![Capital Guard: 100% Secure](https://img.shields.io/badge/Capital%20Guard-100%25%20Secure-red.svg)]()

[Architecture](#-system-architecture) • [Audit Logger](#-permanent-append-only-audit-logger) • [Paper Trading](#-live-paper-trading-simulation) • [Auto-Enhancer](#-continuous-auto-enhancement-engine) • [Backtest Proof](#-46-year-multi-decade-backtest-proof) • [Quick Start](#-quick-start)

---

</div>

> 🛑 **Capital Protection & Permanent Audit Logging First**: SEBI FY26 data shows retail traders lost ₹91,685 Crore in F&O. This platform incorporates an **Append-Only Historical Record & Audit Logger (`history_logger.py`)** that stores every live market tick, trade signal, and paper execution permanently in SQLite (`data/historical_audit.db`) for backtest accuracy verification.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Data & Audit Layer
        A1[Live Market Tick Stream live_market_fetch.py]
        A2[Permanent Append-Only SQLite DB history_logger.py]
        A3[NSE Playwright Live Option Chain]
        A4[Yahoo Finance Global Cues]
    end

    subgraph 2026 Intelligence & Auto-Enhancer
        B1[Macro Intelligence Agent]
        B2[Microstructure & LOB VPIN Agent]
        B3[Super-AI ML Ensemble XGBoost/LightGBM]
        B4[Reinforcement Learning Auto-Enhancer adaptive_weights.py]
    end

    subgraph Capital & Paper Execution
        C1[Capital Guard 3% Daily Kill-Switch]
        C2[0DTE Expiry Trap Filter]
        C3[Live Paper Trading Engine paper_trader.py]
        C4[Monte Carlo 10k Survival Matrix]
    end

    subgraph Execution & Output
        D1[6-Layer High-Precision Signals]
        D2[Hinglish Audio Voice Coach]
        D3[Live HTML Visual Terminal blog/live_terminal.html]
        D4[Angel One SmartAPI Execution]
    end

    A1 & A2 & A3 & A4 --> B1 & B2 & B3 & B4
    B1 & B2 & B3 & B4 --> C1 & C2 & C3 & C4
    C1 & C2 & C3 & C4 --> D1 & D2 & D3 & D4
```

---

## 🗄️ Permanent Append-Only Audit Logger (`history_logger.py`)

- **SQLite Database (`data/historical_audit.db`):** Stores live market ticks, VIX, PCR, Max Pain, and signal history permanently without overwriting past records.
- **Signal Accuracy Tracking (`data/signal_history.csv`):** Logs every generated A+ signal to track signal win rate and performance over time.
- **Trade Journal (`data/paper_trade_journal.csv`):** Keeps a complete trade log of paper trade entries, exits, realized PnL, and win rate.

---

## 📝 Live Paper Trading Simulation (`paper_trader.py`, `auto_paper_runner.py`)

- **Virtual Capital Ledger (`data/paper_account.json`):** Starts with ₹1,00,000 virtual capital to test trading strategies in real time without financial risk.
- **Automated Virtual Order Placement:** Automatically executes virtual paper orders when A+ Grade signals occur.

---

## 🔄 Continuous Auto-Enhancement Engine (`auto_enhancer.py`)

- **RL Adaptive Weights (`adaptive_weights.py`):** Uses Q-learning feedback to adjust indicator weights based on 20-bar historical accuracy.
- **Volume Profile POC & Value Area (`volume_profile.py`):** Dynamically calculates Point of Control (POC), Value Area High (VAH), and Value Area Low (VAL).

---

## 📜 46-Year Multi-Decade Backtest Proof (`long_term_backtest.py`)

Tested across **46 Years of Real Historical Market Data (1980 - 2026 | 11,747 Daily Bars)**:

| Market Benchmark | Timeframe | Historical Period | Total Trades | Win Rate % | Profit Factor | Max Drawdown % | Robustness Score |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **S&P 500 Benchmark** | **Daily (`1D`)** | **1980 – 2026 (46.6 Yrs)** | **122** | **`83.61%`** | **`3.60`** | **`-20.91%`** | 🟢 **ULTRA_ROBUST** |
| **S&P 500 Benchmark** | **Weekly (`1W`)** | **1980 – 2026 (46.6 Yrs)** | **21** | **`90.48%`** | **`4.45`** | **`-33.70%`** | 🟡 **HIGH_ACCURACY** |
| **BSE Sensex Benchmark** | **Daily (`1D`)** | **1997 – 2026 (29.1 Yrs)** | **66** | **`65.15%`** | **`1.98`** | **`-22.96%`** | 🟢 **ULTRA_ROBUST** |

---

## 🚀 Quick Start Guide

### 1. Installation
```bash
git clone https://github.com/mohit11kmr/nifty-research.git
cd nifty-research
pip install -r requirements.txt
playwright install chrome
```

### 2. Run Live Master Launcher
```bash
python3 run_all.py
```

### 3. View Historical Audit Summary
```bash
python3 history_logger.py
```

---

## 🗂️ Module Map

- `run_all.py` — One-Click Master Launcher Script
- `history_logger.py` — Permanent Append-Only SQLite Audit Database & Signal Tracker
- `paper_trader.py` — Live Paper Trading Simulation Engine & Virtual Ledger
- `auto_paper_runner.py` — Autonomous Auto Paper Order Execution System
- `live_market_fetch.py` — Real-Time Intraday Market Spot Tick Fetcher
- `auto_enhancer.py` — Autonomous Reinforcement Learning Self-Optimization Engine
- `adaptive_weights.py` — Dynamic RL Indicator Weight Recalibration Engine
- `volume_profile.py` — Volume Profile Point of Control (POC) & Value Area Engine
- `multi_agent_swarm.py` — 2026 Autonomous AI Trading Swarm Architecture
- `capital_guard.py` — Prop-Desk 3% Kill-Switch & 0DTE Trap Filter
- `profit_engine.py` — Positive Expectancy & 1:2 RRR Profit Engine
- `live_trader_brain.py` — 5-Dimensional Intellectual Master Decision Brain
- `trader_psychology.py` — Emotional Tilt, FOMO & Revenge Trading Defense
- `smc_intelligence.py` — Smart Money Concepts (FVG & Order Blocks)
- `super_ai_ml.py` — XGBoost + LightGBM + Random Forest ML Ensemble
- `lob_microstructure.py` — Limit Order Book Imbalance & VPIN Toxicity
- `anti_spoofing.py` — Adversarial Anti-Spoofing & Fake Wall Filter
- `long_term_backtest.py` — 46-Year Multi-Timeframe Backtest Engine
- `precision_signals.py` — 6-Layer High Confluence Signal Generator
- `voice_coach.py` — Interactive Hinglish Audio Assistant
- `web_dashboard.py` — Sleek Dark-Themed Visual Web Terminal
- `angel_one_client.py` — Official Angel One SmartAPI Integration

---

## 📜 License & Disclaimer

Released under the [MIT License](LICENSE).  
*Disclaimer: Educational and quantitative research platform. Financial markets carry inherent risk. Never risk money you cannot afford to lose.*
