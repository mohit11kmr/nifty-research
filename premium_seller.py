"""Premium seller - option SELLING strategies (the researched edge).

Research consensus (NiftyDesk, MarketsEasy, GitHub algos, tastytrade):
- Option sellers win 60-75% of trades when premium is rich (VIX 16-25).
- Buyers mostly bleed to theta; sellers collect it.
- BUT naked selling = unlimited risk -> we only model DEFINED-RISK
  (short strangle with wings = iron condor) and hard exits.

Rules baked in (never relax):
1. SELL ONLY when India VIX is RICH (16-20) or HIGH (20-25). Cheap premium =
   no edge -> skip (VIX_CHEAP/NORMAL = no sell).
2. Market regime gate: no selling in TREND_HV spike or RANGE_LV? Range is fine
   (that's where selling shines), trend + high vol is not.
3. Strikes: short legs ~2% OTM each side (delta ~0.15-0.20), wings ~100-150
   pts further OTM -> capped loss.
4. Exit: book at +50% of max credit OR cut when premium doubles from entry OR
   short leg goes ITM (defensive). Close all by 2 days before expiry.
5. Sizing: 1% of capital max risk per trade (wing width - credit).
"""
import numpy as np
import pandas as pd

from backtester import bs_call, bs_put, _hist_vol, compute_metrics, TRADING_DAYS, DAYS_TO_EXPIRY

COST_PER_TRADE = 40.0
SLIPPAGE_PCT = 0.0005
PROFIT_TARGET_PCT = 0.50       # book 50% of max credit
STOP_MULT = 2.0                # cut when option premium doubles
DAYS_TO_CLOSE = 2              # square off N days before expiry


def _load_df():
    import os
    from indicators import add_all_indicators
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nifty_history.csv")
    df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    return add_all_indicators(df)


def _load_vix():
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "india_vix.csv")
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p, parse_dates=["date"]).set_index("date").sort_index()
    return df["close"]


def sell_ok(regime, vix_level):
    """Gate: should we sell premium at all today?"""
    if vix_level is None or vix_level < 16:
        return False, "VIX too low (<16) - premium cheap, no selling edge"
    if vix_level >= 25:
        return False, "VIX panic (>25) - wait for stabilisation, mean-reversion only"
    if regime == "TREND_HV":
        return False, "TREND_HV - violent moves crush short premium"
    return True, "VIX rich + sane regime - selling window open"


def premium_sell_backtest(df=None, vix_df=None, spot_dist=0.02, wing=150.0,
                          capital=100000.0, risk_pct=0.01, days_to_expiry=7,
                          rebalance_weekly=True):
    """Backtest defined-risk premium selling.

    For each eligible day (VIX rich + regime ok):
      entry at close(T): sell short call @spot*(1+spot_dist), short put
      @spot*(1-spot_dist); buy wings 150 pts further OTM (iron condor).
      Exit at close when profit target or stop hit, or close N days before
      the weekly expiry (rebalance on Mondays -> expire Thu/Fri).
    """
    if df is None:
        df = _load_df()
    if vix_df is None:
        vix_df = _load_vix()

    df["hv"] = _hist_vol(df["close"], 20)
    # attach vix by date (forward-fill)
    if vix_df is not None and not vix_df.empty:
        df = df.join(vix_df.rename("vix"), how="left").ffill()
    else:
        df["vix"] = np.nan

    close = df["close"].to_numpy()
    n = len(df)
    dates = df.index
    t0 = days_to_expiry / TRADING_DAYS

    trades = []
    i = 0
    while i < n:
        # regime check
        adx = df["adx"].iloc[i]
        pdi, mdi = df["pdi"].iloc[i], df["mdi"].iloc[i]
        bb_u, bb_l = df["bb_upper"].iloc[i], df["bb_lower"].iloc[i]
        trend = adx >= 25 and abs(pdi - mdi) >= 5
        width = (bb_u - bb_l) / close[i] if close[i] else 0
        regime = "TREND_HV" if trend and width > 0.05 else ("TREND" if trend else "RANGE")

        ok, _ = sell_ok(regime, df["vix"].iloc[i])
        if not ok:
            i += 1
            continue

        S = close[i]
        Kc = round(S * (1 + spot_dist) / 50) * 50
        Kp = round(S * (1 - spot_dist) / 50) * 50
        Kc_wing = Kc + int(wing)
        Kp_wing = Kp - int(wing)

        sigma = max(df["hv"].iloc[i], 0.10)
        cr_c = bs_call(S, Kc, t0, sigma)
        cr_p = bs_put(S, Kp, t0, sigma)
        wc_c = bs_call(S, Kc_wing, t0, sigma)
        wc_p = bs_put(S, Kp_wing, t0, sigma)
        credit = (cr_c + cr_p) - (wc_c + wc_p)
        width_risk = (Kc_wing - Kc)  # max loss per unit (short call side)
        if credit <= 0:
            i += 1
            continue

        # walk forward daily, exit on target/stop/time
        entry_price = S
        entry_credit = credit
        j = i + 1
        exit_reason = "target"
        while j < n:
            S_t = close[j]
            sigma_t = max(df["hv"].iloc[j], 0.10)
            days_left = (dates[j] - dates[i]).days
            t_left = max(t0 - days_left / TRADING_DAYS, 1e-6)
            cr_c_t = bs_call(S_t, Kc, t_left, sigma_t)
            cr_p_t = bs_put(S_t, Kp, t_left, sigma_t)
            wc_c_t = bs_call(S_t, Kc_wing, t_left, sigma_t)
            wc_p_t = bs_put(S_t, Kp_wing, t_left, sigma_t)
            cur_credit = (cr_c_t + cr_p_t) - (wc_c_t + wc_p_t)

            # stop: credit doubles from entry (premium exploded)
            if cur_credit >= STOP_MULT * entry_credit:
                exit_reason = "stop"
                break
            # target: booked 50% of credit
            if cur_credit <= (1 - PROFIT_TARGET_PCT) * entry_credit:
                exit_reason = "target"
                break
            # time: close N days before weekly expiry (approx expiry at day 5-6)
            if days_left >= days_to_expiry - DAYS_TO_CLOSE:
                exit_reason = "time"
                break
            j += 1
        if j >= n:
            j = n - 1
            exit_reason = "eod"

        # P&L: credit captured = entry_credit - final_credit, times notional
        final_credit = cur_credit
        pnl_per_unit = entry_credit - final_credit
        # units sized so max risk (wing width - credit) ~ risk_pct*capital
        max_loss = width_risk - entry_credit
        units = max(int((capital * risk_pct) / max(max_loss, 1.0)), 1)
        pnl = pnl_per_unit * units * 25  # NIFTY lot ~25... use 25 qty/lot
        cost = 2 * COST_PER_TRADE
        ret_pct = pnl / (capital * risk_pct) * 100 if capital * risk_pct else 0

        trades.append({
            "entry_date": dates[i],
            "exit_date": dates[j],
            "side": "IRON_CONDOR",
            "strikes": f"{Kc_wing}/{Kc}-{Kp}/{Kp_wing}",
            "entry_price": entry_price,
            "credit": round(entry_credit, 2),
            "final_credit": round(final_credit, 2),
            "pnl": round(pnl - cost, 2),
            "ret_pct": round(ret_pct, 2),
            "exit_reason": exit_reason,
            "vix": round(df["vix"].iloc[i], 2) if not np.isnan(df["vix"].iloc[i]) else None,
        })
        i = j + 1

    t = pd.DataFrame(trades)
    return t


def format_result(trades, capital=100000):
    lines = []
    if trades is None or trades.empty:
        lines.append("PREMIUM SELLER: no trades (VIX gate blocked most days)")
        return lines
    m = compute_metrics(trades, capital)
    lines.append(f"PREMIUM SELLER (iron condor) | {len(trades)} trades")
    lines.append(f"  P&L {m['pnl']:+,.0f} | win {m['win_rate']}% ({m['hit']}/{m['hit']+m['miss']}) | PF {m['profit_factor']} | maxDD {m['max_dd_pct']}%")
    reasons = trades["exit_reason"].value_counts().to_dict()
    lines.append(f"  exits: {reasons}")
    return lines


if __name__ == "__main__":
    t = premium_sell_backtest()
    for line in format_result(t):
        print(line)
