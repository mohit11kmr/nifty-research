"""LIVE MARKET AGENT - full-stack reasoning.

Integrates:
- NIFTY technicals + regime + consensus (market_brain)
- Global snapshot (USDINR, S&P/Nasdaq/Dow, DXY, Gold/Silver/Crude, BTC)
- FII/DII positioning
- Options sentiment (PCR/max-pain from chain when NSE reachable)
- Greeks/IV analysis
- Web research (Hermes-style) when available
Outputs a trader-grade analysis + logged prediction.
"""
import os
import sys
import json
import datetime as dt

import pandas as pd

import indicators
import market_brain as brain
import data_fetcher
import global_data as gd
import sentiment as sent
import greeks
import timing
import web_research

DATA_DIR = "data"
LOG = os.path.join("results", "live_predictions.csv")


def load_latest_df():
    path = os.path.join(DATA_DIR, "nifty_history.csv")
    if not os.path.exists(path):
        print("No cached data. Run: python main.py fetch-data")
        sys.exit(1)
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return indicators.add_all_indicators(df)


def get_chain_data():
    """Option chain + computed metrics. Returns (chain_df, metrics_dict)."""
    try:
        chain = data_fetcher.fetch_option_chain("NIFTY")
        if chain is not None and not chain.empty:
            metrics = data_fetcher.compute_chain_metrics(chain)
            return chain, metrics
    except Exception as e:  # noqa: BLE001
        print(f"  (chain unavailable: {str(e)[:60]})")
    return None, None


def run():
    df = load_latest_df()
    print("=" * 66)
    print("LIVE MARKET AGENT - FULL RESEARCH")
    print(f"Date: {df.index[-1]:%d %b %Y}  |  NIFTY close: {df['close'].iloc[-1]:,.2f}")
    print("=" * 66)

    # 1. Global snapshot
    print("\n[1] GLOBAL MARKETS")
    try:
        snap = gd.fetch_global_snapshot(days=60)
        print(gd.format_global_snapshot(snap))
    except Exception as e:  # noqa: BLE001
        snap = {}
        print(f"  Global data failed: {str(e)[:80]}")

    # 2. FII/DII
    print("\n[2] FII / DII")
    try:
        fdi = gd.fetch_fii_dii()
        if "error" in fdi:
            print(f"  {fdi['error']}")
        else:
            for k, v in fdi.items():
                print(f"  {k}: {v}")
    except Exception as e:  # noqa: BLE001
        fdi = {"error": str(e)[:80]}
        print(f"  FII/DII failed: {str(e)[:80]}")

    # 3. Option chain + Greeks
    print("\n[3] OPTIONS CHAIN / GREEKS")
    chain, chain_metrics = get_chain_data()
    spot = float(df["close"].iloc[-1])
    iv_pct = None
    if chain is not None:
        ana = greeks.analyze_chain(chain, spot, t_days=20)
        if ana:
            iv_pct = ana["avg_iv"]
            print(greeks.interpret_greeks(ana, spot))
            gdf = ana["greeks"].sort_values("strike")
            print("  ATM/ITM/OTM sample (top 3 OI):")
            atm = gdf.loc[(gdf["strike"] - spot).abs().idxmin()]
            print(f"    ATM {int(atm['strike'])}  CE d={atm['delta']:.2f} IV={atm['iv']}")
    else:
        print("  Chain unavailable (NSE blocked / market closed).")

    # 4. Sentiment aggregation
    print("\n[4] SENTIMENT ENGINE")
    pcr = chain_metrics["pcr"] if chain_metrics else None
    max_pain = chain_metrics["max_pain"] if chain_metrics else None
    agg = sent.aggregate(snap, fdi, pcr=pcr, max_pain=max_pain, spot=spot)
    print(f"  Overall: {agg['label']} (score {agg['score']:+})")
    for n in agg["notes"]:
        print(f"  - {n}")

    # 5. Technical reasoning
    print("\n[5] TECHNICAL REASONING")
    res = brain.analyze_market(df, iv=iv_pct)
    v = res["verdict"]
    print(f"  Regime: {res['regime']}")
    for line in res["regime_reasons"]:
        print(f"    - {line}")
    print(f"  Consensus: {res['consensus_score']}/{res['total_votes']}")
    for k, val in res["votes"].items():
        print(f"    {'UP ' if val==1 else ('DN ' if val==-1 else '-- ')} {k}")

    # 6. Web research
    print("\n[6] WEB RESEARCH")
    wr = web_research.research_news()
    if "error" in wr:
        print(f"  {wr['error']}")
    else:
        print("  Agent will research live via its search tool:")
        for q in wr.get("queries", []):
            print(f"    - {q}")

    # Web cues (Hermes-style: research results fed into pipeline)
    web_cues = {}
    if os.path.exists(os.path.join("results", "web_cues.json")):
        try:
            with open(os.path.join("results", "web_cues.json")) as f:
                web_cues = json.load(f)
            print("\n  [Web cues integrated]")
            for ck, cv in web_cues.items():
                print(f"    - {ck}: {cv}")
        except Exception as e:  # noqa: BLE001
            print(f"  (web cues read failed: {e})")

    cue_adjust = 0
    if web_cues.get("fii_net_short_futures"):
        cue_adjust -= 1
        print("    -> FII futures short: -1 sentiment (hedging cap on upside)")
    if web_cues.get("geopolitical"):
        if any(w in web_cues["geopolitical"].lower() for w in ["tension", "conflict", "war", "spike"]):
            cue_adjust -= 1
            print("    -> Geopolitical risk: -1 sentiment")
    agg["score"] += cue_adjust
    if agg["score"] <= 0 and agg["label"] != "NEUTRAL":
        agg["label"] = "NEUTRAL"
        print("    -> Cue-adjusted sentiment downgraded to NEUTRAL")

    # 7. Integrated verdict
    print("\n[7] INTEGRATED VERDICT")
    # Timing stats feed the verdict as additional votes (gap edge, IV aftermath, day-of-week)
    try:
        gaps = timing.analyze_gaps(df)
        dow_stats = timing.day_of_week_stats(df)
        vix_data = timing.fetch_vix()
        iv_ana = timing.analyze_iv_spike(vix_data["india"], df.reset_index())
        t_votes, t_score = timing.timing_votes(
            df, gaps, dow_stats, iv_ana,
            today_dow=dt.datetime.now().strftime("%a"),
        )
    except Exception as e:  # noqa: BLE001
        t_votes, t_score = [], 0.0
        print(f"  (timing votes unavailable: {str(e)[:60]})")
    for tv in t_votes:
        print(f"    [timing] {tv['signal']}: {'UP ' if tv['dir']>0 else 'DN '} w={tv['weight']} - {tv['note']}")
    if t_score:
        print(f"    Timing vote score: {t_score:+.2f}")

    sent_dir = 1 if agg["score"] > 0 else (-1 if agg["score"] < 0 else 0)
    tech_dir = 1 if v["bias"] == "CALL" else (-1 if v["bias"] == "PUT" else 0)
    timing_dir = 1 if t_score > 0.25 else (-1 if t_score < -0.25 else 0)
    agree = sent_dir == tech_dir == timing_dir and sent_dir != 0
    if agree:
        final_bias, final_conf = v["bias"], min(v["confidence"] + 8, 80)
        logic = "Sentiment + Technicals + Timing AGREE (high conviction setup)"
    elif sent_dir != 0 and tech_dir != 0:
        final_bias, final_conf = v["bias"], 50
        logic = "Sentiment and Technicals CONFLICT - reduce size, wait for alignment"
    else:
        final_bias, final_conf = v["bias"], v["confidence"]
        logic = "One side neutral - follow the active signal with caution"

    print(f"  Final: {final_bias} | Confidence ~{final_conf:.0f}% | {logic}")
    print(f"  Strength: {v['strength']} | Favored: {', '.join(v['favored_strategies'])}")
    if v["levels"]["support"]:
        print(f"  Support: {v['levels']['support']:,.0f} | Resistance: {v['levels']['resistance']:,.0f}")

    # 8. Timing intelligence
    print("\n[8] TIMING INTELLIGENCE")
    try:
        gaps = timing.analyze_gaps(df)
        for line in timing.interpret_gaps(gaps):
            print(f"  {line}")
    except Exception as e:  # noqa: BLE001
        print(f"  (gap analysis failed: {str(e)[:60]})")

    try:
        dow = timing.day_of_week_stats(df)
        for line in timing.interpret_dow(dow):
            print(f"  {line}")
    except Exception:  # noqa: BLE001
        pass

    try:
        vix_data = timing.fetch_vix()
        iv_ana = timing.analyze_iv_spike(vix_data["india"], df.reset_index())
        for line in timing.interpret_iv_spike(iv_ana):
            print(f"  {line}")
    except Exception as e:  # noqa: BLE001
        print(f"  (IV spike analysis failed: {str(e)[:60]})")

    try:
        intra = timing.fetch_intraday("15m", "5d")
        iana = timing.intraday_analysis(intra)
        if iana:
            latest_key = sorted(iana.keys())[-1]
            ld = iana[latest_key]
            print(f"  Intraday {latest_key}: open {ld['open']:,.0f} close {ld['close']:,.0f}, "
                  f"OR {ld['or_low']:,.0f}-{ld['or_high']:,.0f}, "
                  f"close vs VWAP {ld['closing_vs_vwap']:+.2f}%, range {ld['range_pct']:.2f}%")
            if ld["broke_or_up"]:
                print("  -> Market closed ABOVE opening range = intraday bulls in control")
            elif ld["broke_or_dn"]:
                print("  -> Market closed BELOW opening range = intraday bears in control")
    except Exception as e:  # noqa: BLE001
        print(f"  (intraday analysis failed: {str(e)[:60]})")

    for line in timing.trade_timing_logic(df.index[-1]):
        print(f"  {line}")

    # Log prediction
    rec = {
        "date": pd.Timestamp(dt.date.today()),
        "close": round(spot, 2),
        "regime": res["regime"],
        "bias": final_bias,
        "confidence": round(final_conf, 0),
        "sentiment": agg["label"],
        "sentiment_score": agg["score"],
        "fii_cash": (fdi or {}).get("fii_equity_cash"),
        "dii_cash": (fdi or {}).get("dii_equity_cash"),
        "hit": "",
    }
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    new = pd.DataFrame([rec])
    if os.path.exists(LOG):
        old = pd.read_csv(LOG)
        new = pd.concat([old, new], ignore_index=True).drop_duplicates("date", keep="last")
    new.to_csv(LOG, index=False)
    print(f"\nPrediction logged -> {LOG}")
    return rec


if __name__ == "__main__":
    run()
