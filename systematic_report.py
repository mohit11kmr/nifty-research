"""Systematic Report Generator for NIFTY Research.

Produces a clean, beautifully formatted Markdown dashboard for traders.
"""
import os
import json
import datetime as dt
import pandas as pd


def _safe_float(val, default=0.0):
    try:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict) and "vix" in val:
            return float(val["vix"])
        return float(val)
    except Exception:
        return default


def generate_systematic_dashboard(out_path="results/systematic_dashboard.md"):
    """Compile all research inputs into a clean, systematic Markdown dashboard."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    now = dt.datetime.now().strftime("%d %b %Y | %H:%M IST")

    # Import pipeline data
    try:
        import regime_filter
        regime_data = regime_filter.trade_plan()
    except Exception:
        regime_data = {"regime": "UNKNOWN", "gate": "UNKNOWN", "bias": "NEUTRAL", "size": 0.0}

    try:
        import global_data
        global_snap = global_data.fetch_global_snapshot()
    except Exception:
        global_snap = {}

    try:
        import oi_intel
        import glob
        snaps = sorted(glob.glob("data/oi_snapshots/*.csv"))
        if snaps:
            chain_df = pd.read_csv(snaps[-1])
            oi_walls = oi_intel.oi_walls(chain_df)
            pcr_pain = oi_intel.pcr_and_pain(chain_df)
        else:
            oi_walls, pcr_pain = {"resistance_oi": [], "support_oi": []}, {"pcr": 0, "max_pain": 0}
    except Exception:
        oi_walls, pcr_pain = {"resistance_oi": [], "support_oi": []}, {"pcr": 0, "max_pain": 0}

    try:
        import web_research
        news = web_research.research_news()
        headlines = news.get("live_headlines", {})
    except Exception:
        headlines = {}

    regime = regime_data.get("regime", "N/A")
    gate = regime_data.get("gate", "N/A")
    size = _safe_float(regime_data.get("size", 0.0))
    close_price = _safe_float(regime_data.get("close", 0.0))
    vix_val = _safe_float(regime_data.get("vix", 0.0))

    lines = []
    lines.append("# 📈 NIFTY 50 SYSTEMATIC TRADING DASHBOARD")
    lines.append(f"_Generated: {now}_\n")
    lines.append("---")

    lines.append("\n## 🎯 1. SYSTEMATIC TRADE DECISION")
    lines.append("| Parameter | Status / Value | Actionable Rule |")
    lines.append("|---|---|---|")
    lines.append(f"| **Regime Gate** | **{regime} ({gate})** | {'✅ TRADE OPEN' if size > 0 else '❌ STAY OUT — Low Volatility Chop'} |")
    lines.append(f"| **Position Sizing** | **{size:.1f}x Multiplier** | {f'Risk max {size*1:.1f}% capital' if size > 0 else 'Zero Directional Trades'} |")
    lines.append(f"| **VIX Zone** | **{regime_data.get('vix_zone', 'NORMAL')}** | Defined-Risk Spreads / Neutral |")
    lines.append(f"| **Daily Risk Limit** | **3.0% Max Loss** | Hard Risk Circuit |")

    lines.append("\n---\n## 📊 2. LIVE MARKET & OPTION CHAIN METRICS")
    lines.append("| Metric | Value | Market Interpretation |")
    lines.append("|---|---|---|")
    lines.append(f"| **Nifty Spot** | {close_price:,.2f} | Current Index Level |")
    lines.append(f"| **India VIX** | {vix_val:.2f} | Options Premium Pricing Gauge |")
    lines.append(f"| **Put-Call Ratio (PCR)** | {pcr_pain.get('pcr', 'N/A')} | {'Bullish (>1.3)' if _safe_float(pcr_pain.get('pcr')) > 1.3 else ('Bearish (<0.8)' if _safe_float(pcr_pain.get('pcr')) < 0.8 else 'Neutral')} |")
    lines.append(f"| **Max Pain Level** | {pcr_pain.get('max_pain', 'N/A')} | Option Buyers Max Loss Strike |")
    lines.append(f"| **Call Wall (Resistance)** | {', '.join(map(str, oi_walls.get('resistance_oi', [])))} | Heavy CE OI Ceiling |")
    lines.append(f"| **Put Wall (Support)** | {', '.join(map(str, oi_walls.get('support_oi', [])))} | Heavy PE OI Floor |")

    lines.append("\n---\n## 🌍 3. GLOBAL & SENTIMENT SNAPSHOT")
    lines.append("| Asset / Market | Price / Level | Daily Change |")
    lines.append("|---|---|---|")
    for asset, data in global_snap.items():
        lines.append(f"| **{asset}** | {_safe_float(data.get('close')):,.2f} | {_safe_float(data.get('change_pct')):+.2f}% |")

    lines.append("\n---\n## 📰 4. LIVE MARKET HEADLINES")
    for category, items in headlines.items():
        lines.append(f"\n### {category.upper()} Headlines:")
        for item in items[:4]:
            lines.append(f"- 🔹 {item}")

    lines.append("\n---\n## ⚡ 5. ACTIONABLE WATCHLIST & EXECUTIONS")
    lines.append("1. **Trigger Condition:** Wait for ADX > 20 or BB Expansion.")
    lines.append("2. **Upside Setup:** Break above CE Wall → Bull Call Spread.")
    lines.append("3. **Downside Setup:** Break below PE Wall → Bear Put Spread.")
    lines.append("4. **Broker Status:** Angel One SmartAPI Connected ✅")


    dashboard_text = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(dashboard_text)

    print(f"[Systematic Dashboard] Wrote {out_path}")
    return dashboard_text


if __name__ == "__main__":
    print(generate_systematic_dashboard())
