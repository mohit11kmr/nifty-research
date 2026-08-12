"""Trade Journal Analyzer.

Reads a trade journal (backtester trades DF, or an exported brokerage CSV
such as Angel One / Zerodha) and outputs:

  1. Core numbers  - win rate, avg win, avg loss, profit factor, expectancy,
                     R-multiples, trading edge (% per trade), Sharpe, maxDD
  2. Segment edge  - which side / month / day-of-week / instrument actually
                     has the edge (Minervini: "know your numbers")
  3. Goal projection - how long at THIS style+size to reach a capital target
                     (video #3 core idea: "kitna time laggega?")
  4. Verdict        - plain-language read

Usage:
  python trade_journal.py --csv data/trades_angel.csv --capital 100000
  python trade_journal.py --from-backtest <name>   # run a strategy backtest,
                                                   # feed its trades in

Supports both formats:
  backtester: entry_date, exit_date, side, strike, pnl, ret_pct, premium_in,
              premium_out, lots
  brokerage : any CSV with a date col + qty col + buy/sell cols -> net pnl
"""
import argparse
import os
import sys
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
warnings.filterwarnings("ignore")

TRADING_DAYS = 252


# ----------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------
def load_trades(csv_path):
    """Load any trade CSV -> normalized DF with entry_date/exit_date/side/pnl."""
    df = pd.read_csv(csv_path)
    cols = {c.lower().strip(): c for c in df.columns}
    df.columns = [c.lower().strip() for c in df.columns]

    # Backtester format (has pnl directly)
    if "pnl" in df.columns and "side" in df.columns:
        return _normalize_backtester(df)

    # Brokerage format: need qty + price, reconstruct pnl per trade row
    return _normalize_brokerage(df)


def _normalize_backtester(df):
    out = df[["entry_date", "exit_date", "side", "pnl"]].copy()
    for c in ("entry_date", "exit_date"):
        out[c] = pd.to_datetime(out[c])
    out["side"] = out["side"].astype(str).str.upper()
    out = out[out["pnl"].notna()]
    return out.reset_index(drop=True)


def _normalize_brokerage(df):
    """Best-effort conversion for plain trade exports.

    Looks for: date, symbol/script, qty/quantity, buy price, sell price,
    (or a single avg-price + buy/sell flag). If a 'pnl' column exists use it.
    Otherwise pairs buy/sell rows per symbol (FIFO) into round-trip PnL.
    """
    if "pnl" in df.columns:
        dcol = df["date"] if "date" in df.columns else df.iloc[:, 0]
        side = df["side"] if "side" in df.columns else pd.Series("X", index=df.index)
        return pd.DataFrame({
            "entry_date": pd.to_datetime(dcol),
            "exit_date": pd.to_datetime(dcol),
            "side": side.astype(str).str.upper(),
            "pnl": df["pnl"].astype(float),
        })

    date_col = next((c for c in df.columns if "date" in c or "time" in c), None)
    sym_col = next((c for c in df.columns if c in ("symbol", "script", "trading symbol", "symbol name", "instrument")), None)
    if date_col is None:
        raise ValueError("Cannot identify date column in CSV.")

    # FIFO pairing of buys and sells per symbol into round trips
    qty_col = next((c for c in df.columns if c in ("qty", "quantity", "lots", "lot size")), None)
    price_col = next((c for c in df.columns if c in ("price", "buy price", "sell price", "avg price", "avg. price")), None)
    if qty_col is None or price_col is None:
        raise ValueError("Need qty + price columns to pair trades, or a pnl column.")

    action_col = next((c for c in df.columns if c in ("action", "buy/sell", "side", "trade type")), None)
    if action_col is None:
        raise ValueError("Need an action (Buy/Sell) column to pair trades.")

    df = df[[date_col, sym_col, qty_col, price_col, action_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df[qty_col] = df[qty_col].astype(float)
    df[price_col] = df[price_col].astype(float)
    df["_buy"] = df[action_col].astype(str).str.lower().str.contains("buy")

    # FIFO round-trip pairing, symmetric for long AND short
    trades = []
    for sym, grp in df.groupby(sym_col, sort=False):
        grp = grp.sort_values(date_col)
        position = 0.0      # + long open qty, - short open qty
        avg_price = 0.0
        for _, r in grp.iterrows():
            qty, px = r[qty_col], r[price_col]
            buy = r["_buy"]
            if (buy and position >= 0) or (not buy and position <= 0):
                # same-direction add: opens or adds to a position
                new_pos = position + (qty if buy else -qty)
                avg_price = (avg_price * abs(position) + px * qty) / (qty + abs(position)) if position != 0 else px
                position = new_pos
            else:
                # opposite-direction: closes (partially) the open position
                sign = 1 if position > 0 else -1
                close_qty = min(qty, abs(position))
                pnl = (px - avg_price) * close_qty * sign
                trades.append({
                    "entry_date": r[date_col], "exit_date": r[date_col],
                    "side": "CALL" if "CE" in str(sym).upper() else ("PUT" if "PE" in str(sym).upper() else "X"),
                    "pnl": pnl,
                })
                position = position - close_qty * sign
                qty -= close_qty
                if qty > 0:
                    # remaining flips into a new opposite position
                    position = position + (qty if buy else -qty)
                    avg_price = px

    if not trades:
        raise ValueError("No round trips could be paired from this CSV.")
    return pd.DataFrame(trades)


# ----------------------------------------------------------------------------
# Core numbers
# ----------------------------------------------------------------------------
def edge_stats(trades, capital):
    n = len(trades)
    if n == 0:
        return {}
    pnl = trades["pnl"]
    wins = trades[trades["pnl"] > 0]
    losses = trades[trades["pnl"] < 0]
    gw, gl = wins["pnl"].sum(), abs(losses["pnl"].sum())
    pf = gw / gl if gl else (np.inf if gw else 0.0)

    avg_win = wins["pnl"].mean() if len(wins) else 0.0
    avg_loss = abs(losses["pnl"].mean()) if len(losses) else 0.0
    payoff = avg_win / avg_loss if avg_loss else 0.0
    winrate = len(wins) / n

    # R-multiples: risk = avg loss (or 1% of capital if no losses yet)
    risk = avg_loss if avg_loss > 0 else capital * 0.01
    r = (pnl / risk).replace([np.inf, -np.inf], np.nan).fillna(0)

    expectancy = (winrate * avg_win - (1 - winrate) * avg_loss) / risk

    # time span
    try:
        days = max((trades["exit_date"].max() - trades["entry_date"].min()).days, 1)
    except (TypeError, AttributeError):
        days = n
    trades_per_day = n / days
    edge_per_trade_pct = pnl.mean() / capital * 100

    eq = (capital + pnl.cumsum()).to_numpy()
    peak = np.maximum.accumulate(eq)
    dd = ((eq - peak) / peak).min() if len(eq) else 0.0

    return {
        "n": n,
        "pnl": round(pnl.sum(), 2),
        "win_rate": round(winrate * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "payoff": round(payoff, 2),
        "profit_factor": round(pf, 2),
        "expectancy_r": round(float(expectancy), 2),
        "avg_r": round(float(r.mean()), 2),
        "edge_per_trade_pct": round(edge_per_trade_pct, 3),
        "trades_per_day": round(trades_per_day, 2),
        "span_days": days,
        "max_dd_pct": round(dd * 100, 2),
        "capital": capital,
    }


# ----------------------------------------------------------------------------
# Segment edge
# ----------------------------------------------------------------------------
def segment_edge(trades, capital):
    """Edge broken by side / month / weekday / instrument."""
    seg = {}
    for key, col in (("SIDE", "side"), ("MONTH", "month"), ("WEEKDAY", "dow")):
        tmp = trades.copy()
        tmp["month"] = tmp["entry_date"].dt.to_period("M").astype(str)
        tmp["dow"] = tmp["entry_date"].dt.day_name()
        rows = []
        for val, grp in tmp.groupby(col):
            s = edge_stats(grp, capital)
            if s:
                rows.append({"group": str(val), "n": s["n"],
                             "win_rate": s["win_rate"], "pf": s["profit_factor"],
                             "expectancy_r": s["expectancy_r"], "pnl": s["pnl"]})
        seg[key] = rows
    return seg


# ----------------------------------------------------------------------------
# Goal projection
# ----------------------------------------------------------------------------
def goal_projection(stats, targets, current_capital=None):
    """How long to hit each target at this edge + trade frequency.

    Compounding: capital *= (1 + edge_per_trade_pct/100 * n_trades_per_day)
    per day. R-multiple growth: capital *= (1 + avg_r * risk% )^trades.
    """
    cap = stats.get("capital") or current_capital or 100000
    e_per_trade = stats.get("edge_per_trade_pct", 0) / 100.0
    tpd = stats.get("trades_per_day", 0)
    out = []
    for tgt in targets:
        days = 0
        c = cap
        if e_per_trade <= 0 or tpd <= 0:
            days = None
        else:
            while c < tgt and days < 365 * 100:
                c *= (1 + e_per_trade * tpd)
                days += 1
        years = days / TRADING_DAYS if days else None
        out.append({
            "target": tgt,
            "days": days,
            "years": round(years, 1) if years else None,
            "note": None if days else "negative/zero edge -> target unreachable at this style",
        })
    return out


# ----------------------------------------------------------------------------
# Verdict
# ----------------------------------------------------------------------------
def verdict(stats):
    s = stats
    if not s:
        return "No trades."
    lines = []
    if s["expectancy_r"] > 0.2:
        lines.append(f"POSITIVE edge: {s['expectancy_r']:.2f}R per trade")
    elif s["expectancy_r"] > 0:
        lines.append(f"Thin positive edge ({s['expectancy_r']:.2f}R) - fees/slippage can kill it")
    else:
        lines.append(f"NEGATIVE edge ({s['expectancy_r']:.2f}R) - this style is a leak")
    if s["win_rate"] < 40 and s["payoff"] >= 2:
        lines.append("Low win rate + high payoff = trend/breakout profile (trade small, cut fast)")
    elif s["win_rate"] > 60 and s["payoff"] < 1:
        lines.append("High win rate + low payoff = scalp/mean-rev profile (protect winners)")
    if s["profit_factor"] < 1:
        lines.append(f"Profit factor {s['profit_factor']} < 1 -> not tradeable as-is")
    elif s["profit_factor"] < 1.5:
        lines.append(f"Profit factor {s['profit_factor']} - tradeable only with tight risk controls")
    return " | ".join(lines)


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------
def report(trades, capital, targets):
    stats = edge_stats(trades, capital)
    seg = segment_edge(trades, capital)
    proj = goal_projection(stats, targets, capital)

    print("=" * 70)
    print("TRADE JOURNAL ANALYSIS")
    print("=" * 70)
    if stats:
        print(f"  trades      : {stats['n']}   (span {stats['span_days']}d, "
              f"{stats['trades_per_day']:.2f}/day)")
        print(f"  total P&L   : Rs {stats['pnl']:,.0f}   on capital Rs {capital:,.0f}")
        print(f"  win rate    : {stats['win_rate']}%   avg win Rs {stats['avg_win']:,.0f} "
              f"| avg loss Rs {stats['avg_loss']:,.0f}")
        print(f"  payoff      : {stats['payoff']}   profit factor {stats['profit_factor']}")
        print(f"  expectancy  : {stats['expectancy_r']} R/trade   (avg trade "
              f"{stats['avg_r']}R)")
        print(f"  edge/trade  : {stats['edge_per_trade_pct']}% of capital   "
              f"maxDD {stats['max_dd_pct']}%")
    print()
    for key in ("SIDE", "MONTH", "WEEKDAY"):
        rows = seg.get(key, [])
        if not rows:
            continue
        print(f"  [{key}] edge by segment:")
        for r in sorted(rows, key=lambda x: x["pnl"], reverse=True):
            print(f"    {r['group']:<12} n={r['n']:>3}  WR {r['win_rate']:>5}%  "
                  f"PF {r['pf']:>5}  E {r['expectancy_r']:>+6.2f}R  PnL Rs {r['pnl']:>9,.0f}")
        print()
    print("  [GOAL PROJECTION] (current style + size, compounding)")
    for p in proj:
        if p["years"] is None:
            print(f"    -> Rs {p['target']:>10,}: {p['note']}")
        else:
            print(f"    -> Rs {p['target']:>10,}: ~{p['years']} years "
                  f"({p['days']} trading days)")
    print()
    print(f"  [VERDICT] {verdict(stats)}")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="path to trade journal CSV")
    ap.add_argument("--from-backtest", help="strategy name from strategies.py "
                    "to backtest then analyze")
    ap.add_argument("--capital", type=float, default=100000)
    ap.add_argument("--targets", default="1000000,5000000",
                    help="comma list of capital goals")
    args = ap.parse_args()

    if args.from_backtest:
        from backtester import run_backtest
        from indicators import add_all_indicators
        import strategies
        df = pd.read_csv(os.path.join(HERE, "data", "nifty_history.csv"))
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = add_all_indicators(df)
        fn = strategies.ALL_STRATEGIES.get(args.from_backtest)
        if fn is None:
            sys.exit(f"Unknown strategy: {args.from_backtest}. "
                     f"Available: {list(strategies.ALL_STRATEGIES)}")
        sig = fn(df)
        trades = run_backtest(df, sig, mode="underlying")
    elif args.csv:
        trades = load_trades(args.csv)
    else:
        ap.print_help()
        sys.exit("Provide --csv or --from-backtest")

    targets = [int(t.strip()) for t in args.targets.split(",")]
    report(trades, args.capital, targets)


if __name__ == "__main__":
    main()
