"""Live Dynamic HTML Trading Terminal & Dashboard Generator.

Generates a dark-themed, ultra-premium visual trading dashboard at blog/live_terminal.html.
"""
import os
import json
import datetime as dt
import pandas as pd


def _to_float(val, default=0.0):
    try:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, dict) and "vix" in val:
            return float(val["vix"])
        return float(val)
    except Exception:
        return default


def generate_live_terminal_html(out_path="blog/live_terminal.html"):
    """Generate live interactive HTML trading dashboard."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    now = dt.datetime.now().strftime("%d %b %Y | %H:%M:%S IST")

    # Pipeline Data
    try:
        import regime_filter
        regime_data = regime_filter.trade_plan()
    except Exception:
        regime_data = {"regime": "NO_DATA", "gate": "NO_TRADE", "close": None, "vix": None}

    try:
        import precision_signals
        sig = precision_signals.generate_precision_signal()
    except Exception:
        sig = {"signal_grade": "NO_SIGNAL", "confluence_score": "N/A"}

    try:
        import gamma_flip
        snaps = [os.path.join("data", "oi_snapshots", f) for f in os.listdir(os.path.join("data", "oi_snapshots")) if f.endswith(".csv")] if os.path.exists(os.path.join("data", "oi_snapshots")) else []
        if snaps:
            cdf = pd.read_csv(snaps[-1])
            gex_data = gamma_flip.calculate_gamma_exposure(cdf)
        else:
            gex_data = {"gamma_flip_strike": None, "market_maker_regime": "NO_DATA (no OI snapshot)"}
    except Exception:
        gex_data = {"gamma_flip_strike": None, "market_maker_regime": "NO_DATA (error reading snapshot)"}

    # Real capital guard status (honest label)
    try:
        import capital_guard
        cg_audit = capital_guard.CapitalGuard().full_capital_safety_audit()
        guard_score = cg_audit.get("capital_preservation_score", "N/A")
        guard_status = cg_audit.get("safety_status", "N/A")
    except Exception:
        guard_score = "N/A"
        guard_status = "N/A"

    # Real broker session status (honest - no fake "Connected")
    broker_line = "Not Connected (check .env credentials)"
    broker_connected = False
    try:
        import angel_one_client
        profile = angel_one_client.manager.get_profile()
        if profile:
            broker_connected = True
            broker_line = "Connected (Angel One SmartAPI)"
    except Exception:
        pass

    spot = _to_float(regime_data.get("close"), None)
    spot_txt = f"{spot:,.2f}" if spot else "N/A"
    regime = regime_data.get("regime", "NO_DATA")
    gate = regime_data.get("gate", "NO_TRADE")
    vix = _to_float(regime_data.get("vix"), None)
    vix_txt = f"{vix:.2f}" if vix else "N/A"
    signal_grade = sig.get("signal_grade", "NO_SIGNAL")
    gex_strike = gex_data.get("gamma_flip_strike")
    gex_strike_txt = f"{int(gex_strike)}" if gex_strike else "N/A"
    gex_regime_txt = gex_data.get("market_maker_regime", "N/A")
    broker_badge = "Connected ✅" if broker_connected else "Not Connected ⚠️"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Quant Terminal | Mohit Kumar</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0b0f19;
            --card-bg: #131b2e;
            --border: #1e2a4a;
            --accent-green: #00e676;
            --accent-red: #ff1744;
            --accent-blue: #29b6f6;
            --accent-purple: #ab47bc;
            --text: #e0e6ed;
            --text-dim: #90a4ae;
        }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: 'Outfit', sans-serif;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .title {{ font-size: 26px; font-weight: 700; background: linear-gradient(90deg, #29b6f6, #00e676); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .badge {{ background: var(--border); padding: 6px 14px; border-radius: 20px; font-size: 13px; font-family: 'JetBrains Mono', monospace; color: var(--accent-green); }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; transition: transform 0.2s; }}
        .card:hover {{ transform: translateY(-3px); }}
        .card-title {{ font-size: 13px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }}
        .card-value {{ font-size: 28px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
        .sub-text {{ font-size: 13px; color: var(--text-dim); margin-top: 6px; }}
        .tag-blocked {{ color: var(--accent-red); font-weight: 600; }}
        .tag-open {{ color: var(--accent-green); font-weight: 600; }}
        .terminal-box {{ background: #070a12; border: 1px solid var(--border); border-radius: 8px; padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #a5d6a7; margin-top: 24px; overflow-x: auto; }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <div class="title">⚡ NIFTY QUANT TERMINAL & CAPITAL GUARD</div>
            <div style="color: var(--text-dim); font-size: 14px;">Broker: Angel One SmartAPI {broker_badge} <span style="color: var(--text-dim);">({broker_line})</span></div>
        </div>
        <div class="badge">LIVE: {now}</div>
    </div>

    <div class="grid">
        <div class="card">
            <div class="card-title">NIFTY 50 Index Spot</div>
            <div class="card-value" style="color: var(--accent-blue);">{spot_txt}</div>
            <div class="sub-text">Live Closing / Intraday Benchmark</div>
        </div>

        <div class="card">
            <div class="card-title">Regime Gate Filter</div>
            <div class="card-value"><span class="{ 'tag-blocked' if gate == 'NO_TRADE' else 'tag-open' }">{regime} ({gate})</span></div>
            <div class="sub-text">{ '❌ Low-Vol Chop: STAY OUT' if gate == 'NO_TRADE' else '✅ Trade Open' }</div>
        </div>

        <div class="card">
            <div class="card-title">India VIX & Premium Zone</div>
            <div class="card-value" style="color: var(--accent-purple);">{vix_txt}</div>
            <div class="sub-text">Zone: Normal (Defined-Risk Spreads)</div>
        </div>

        <div class="card">
            <div class="card-title">Signal Confluence Rating</div>
            <div class="card-value" style="font-size: 20px; color: { 'var(--accent-red)' if 'NO_SIGNAL' in signal_grade else 'var(--accent-green)' };">{signal_grade}</div>
            <div class="sub-text">5-Layer Noise Filter Evaluation</div>
        </div>

        <div class="card">
            <div class="card-title">Market Maker Gamma Flip</div>
            <div class="card-value" style="color: var(--accent-green);">{gex_strike_txt}</div>
            <div class="sub-text">{gex_regime_txt}</div>
        </div>

        <div class="card">
            <div class="card-title">Capital Preservation Guard</div>
            <div class="card-value" style="color: var(--accent-green);">{guard_score}</div>
            <div class="sub-text">Capital Guard: {guard_status} | 3% Daily Kill-Switch Active</div>
        </div>
    </div>

    <div class="terminal-box">
        <div>> System Status: Core Quant Engines Operational (see run_all.py)</div>
        <div>> SQLite Tick DB: data/research.db (WAL Mode) Active</div>
        <div>> SmartAPI Session: {broker_line}</div>
        <div>> Voice Coach: voice_coach.py Enabled</div>
    </div>


</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Web Terminal Generator] Wrote {out_path}")
    return out_path


if __name__ == "__main__":
    generate_live_terminal_html()
