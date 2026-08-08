"""Report generation - markdown research reports."""
import datetime as dt
import pandas as pd


def _pct(x):
    return f"{x:.2f}%" if x is not None else "N/A"


def format_money(x):
    return f"Rs {x:,.0f}" if x is not None else "N/A"


def generate_market_report(hist_df, chain_metrics, out_path):
    last = hist_df.iloc[-1]
    prev = hist_df.iloc[-2] if len(hist_df) > 1 else last
    chg = last["close"] - prev["close"]
    chg_pct = chg / prev["close"] * 100

    lines = []
    lines.append("# NSE Market Research Report")
    lines.append(f"\n_Generated: {dt.datetime.now():%d %b %Y %H:%M}_\n")
    lines.append("## Market Snapshot")
    lines.append(f"- **Close:** {last['close']:,.2f}  ({(chg_pct):+.2f}% / {chg:+,.2f})")
    lines.append(f"- **Open:** {last['open']:,.2f} | **High:** {last['high']:,.2f} | **Low:** {last['low']:,.2f}")
    lines.append(f"- **20-day SMA:** {last.get('sma20', float('nan')):,.2f} | **50-day SMA:** {last.get('sma50', float('nan')):,.2f} | **200-day SMA:** {last.get('sma200', float('nan')):,.2f}")
    lines.append(f"- **RSI(14):** {last.get('rsi14', float('nan')):.1f} | **ADX(14):** {last.get('adx', float('nan')):.1f} | **MACD hist:** {last.get('macd_hist', float('nan')):+.1f}")
    lines.append(f"- **20-day return:** {(hist_df['close'].iloc[-1]/hist_df['close'].iloc[-21]-1)*100:+.2f}%  (last 20 sessions)")

    lines.append("\n## Options Sentiment (live chain)")
    if chain_metrics:
        cm = chain_metrics
        lines.append(f"- **ATM strike:** {cm['atm']}")
        lines.append(f"- **Put-Call Ratio (PCR):** {cm['pcr']}")
        lines.append(f"- **Max Pain:** {cm['max_pain']}")
        lines.append(f"- **OI Support (highest PE OI):** {', '.join(map(str, cm['support_oi']))}")
        lines.append(f"- **OI Resistance (highest CE OI):** {', '.join(map(str, cm['resistance_oi']))}")
        lines.append(f"- _Interpretation: PCR>1.5 = extreme bearish (contrarian buy signal), PCR<0.7 = extreme bullish_")
    else:
        lines.append("- Chain data unavailable right now.")

    lines.append("\n## Technical State")
    trend = "Uptrend" if last["close"] > last["sma50"] else "Downtrend"
    lines.append(f"- Price vs 50-SMA: **{trend}**")
    adx = last.get("adx", 0)
    strength = "Strong trend" if adx > 25 else ("Weak trend" if adx > 20 else "Range-bound/Choppy")
    lines.append(f"- Trend strength (ADX): **{strength}**")
    rsi = last.get("rsi14", 50)
    zone = "Overbought" if rsi > 70 else ("Oversold" if rsi < 30 else "Neutral")
    lines.append(f"- RSI zone: **{zone}**")
    if last["close"] > last["bb_upper"]:
        bb = "Price ABOVE upper band (overbought)"
    elif last["close"] < last["bb_lower"]:
        bb = "Price BELOW lower band (oversold)"
    else:
        bb = "Price inside bands"
    lines.append(f"- Bollinger: **{bb}**")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return "\n".join(lines)


def generate_backtest_report(grid_results, out_path, top_n=15, oos=None):
    rows = []
    for r in grid_results:
        m = r["metrics"]
        rows.append({
            "Strategy": r["name"],
            "Params": str(r["params"]),
            "Hold": r.get("hold", 1),
            "Trades": m["trades"],
            "PnL": m["pnl"],
            "WinRate%": m["win_rate"],
            "ProfitFactor": m["profit_factor"],
            "AvgRet%": m["avg_ret_pct"],
            "MaxDD%": m["max_dd_pct"],
            "Sharpe": m["sharpe"],
            "CAGR%": m["cagr_pct"],
        })
    df = pd.DataFrame(rows)

    lines = []
    lines.append("# Strategy Research Report (Options Buying)")
    lines.append(f"\n_Generated: {dt.datetime.now():%d %b %Y %H:%M}_\n")
    lines.append(f"- Total configurations tested: **{len(df)}**")
    lines.append(f"- Positive PnL strategies: **{(df['PnL'] > 0).sum()}**")
    lines.append(f"- Minimum 20 trades filter (avoid overfit): applied to rankings below\n")

    df_stat = df[df["Trades"] >= 20].copy()

    lines.append("## Top Performers (by PnL, min 20 trades)")
    lines.append("\n| " + " | ".join(df_stat.columns) + " |")
    lines.append("|" + "|".join(["---"] * len(df_stat.columns)) + "|")
    for _, row in df_stat.sort_values("PnL", ascending=False).head(top_n).iterrows():
        lines.append("| " + " | ".join(str(x) for x in row.values) + " |")

    lines.append("\n## Best Win Rate (min 20 trades)")
    lines.append("\n| " + " | ".join(df_stat.columns) + " |")
    lines.append("|" + "|".join(["---"] * len(df_stat.columns)) + "|")
    for _, row in df_stat.sort_values("WinRate%", ascending=False).head(5).iterrows():
        lines.append("| " + " | ".join(str(x) for x in row.values) + " |")

    lines.append("\n## Best Risk-Adjusted (Sharpe, min 20 trades)")
    lines.append("\n| " + " | ".join(df_stat.columns) + " |")
    lines.append("|" + "|".join(["---"] * len(df_stat.columns)) + "|")
    for _, row in df_stat.sort_values("Sharpe", ascending=False).head(5).iterrows():
        lines.append("| " + " | ".join(str(x) for x in row.values) + " |")

    lines.append("\n## Out-of-Sample Validation (top candidates on last 40% data)")
    if oos:
        lines.append("\n_Overfit check: backtest sirf last 40% dates pe. Agar yahan bhi positive ho = strategy robust._\n")
        lines.append("| Strategy | Params | Hold | Trades | PnL | WinRate% | ProfitFactor | MaxDD% | Sharpe |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in oos:
            m = r["metrics"]
            lines.append(f"| {r['name']} | {r['params']} | {r['hold']} | {m['trades']} | {m['pnl']} | "
                         f"{m['win_rate']} | {m['profit_factor']} | {m['max_dd_pct']} | {m['sharpe']} |")
    else:
        lines.append("- Not available.")

    lines.append("\n## Full Results CSV: see `results/research_results.csv`")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    df.to_csv("results/research_results.csv", index=False)
    return "\n".join(lines)
