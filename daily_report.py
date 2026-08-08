"""Daily combined options intelligence report.

Combines:
1. NSE live option chain -> OI walls / build-up / PCR / max-pain (Murarkar logic)
2. FII/DII institutional positioning + margin CE reading
3. Stock-flow scanner (which Nifty names are being accumulated)
4. Multi-timeframe strategy edge summary (from cached tf_scan.csv)

Run after market close (chain data) or during market hours (live).
"""
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _line(char="=", n=72):
    return char * n


def report_options_chain(symbol="NIFTY"):
    """Live chain analysis -> walls, build-up, PCR, matrix."""
    try:
        from nse_live import fetch_option_chain_live, close
    except ImportError:
        print("nse_live unavailable (playwright missing)")
        return
    print(_line())
    print(f"OPTION CHAIN  |  {symbol}  |  {dt.datetime.now():%Y-%m-%d %H:%M}")
    print(_line())
    try:
        chain, meta = fetch_option_chain_live(symbol)
    except Exception as e:
        print(f"  chain fetch failed: {e}")
        return
    if chain.empty:
        print("  empty chain")
        return

    import oi_intel
    spot = meta.get("underlying")
    try:
        spot = float(spot)
    except (TypeError, ValueError):
        spot = None

    print(f"  Spot ~{spot:,.0f} | expiry {meta.get('expiry')}")
    if spot:
        walls = oi_intel.oi_walls(chain, n=3, spot=spot)
        print(f"  CE walls (resistance): {walls['resistance_oi']}"
              f"  nearest: {walls.get('nearest_resistance')}")
        print(f"  PE walls (support):    {walls['support_oi']}"
              f"  nearest: {walls.get('nearest_support')}")

        pp = oi_intel.pcr_and_pain(chain, spot)
        print(f"  PCR {pp['pcr']} (oi-chg PCR {pp['pcr_oi_chg']}) | "
              f"max pain {pp['max_pain']} | CE tot {pp['ce_total_oi']:,} PE tot {pp['pe_total_oi']:,}")

        bu = oi_intel.detect_build_up(chain, top_n=4)
        ce_top = ", ".join(f"{b['strike']}(+{b['oi_chg']:,})" for b in bu["ce_build_up"][:4])
        pe_top = ", ".join(f"{b['strike']}(+{b['oi_chg']:,})" for b in bu["pe_build_up"][:4])
        print(f"  CE build-up strikes: {ce_top}")
        print(f"  PE build-up strikes: {pe_top}")

        mm = oi_intel.murarkar_matrix(chain, spot)
        print(f"  Matrix: CE chg {mm['ce_oi_change']:,} | PE chg {mm['pe_oi_change']:,} "
              f"| PCR rising {mm['pcr_rising']} => {mm['signal']}")
        oi_intel.save_history_json(chain, symbol, extra={"spot": spot})
    print()


def report_institutional():
    print(_line())
    print("INSTITUTIONAL FLOW  |  FII/DII + margin-CE read")
    print(_line())
    try:
        import institutional
        for line in institutional.format_scan(institutional.institutional_scan()):
            print(line)
    except Exception as e:
        print(f"  institutional failed: {e}")
    print()


def report_stock_flow(top=12):
    print(_line())
    print("STOCK FLOW  |  Nifty accumulation scan")
    print(_line())
    try:
        import stock_flow
        res, all_ = stock_flow.scan_universe(top=top)
        for line in stock_flow.format_flow(res):
            print(line)
    except Exception as e:
        print(f"  stock flow failed: {e}")
    print()


def report_tf_summary():
    print(_line())
    print("MULTI-TIMEFRAME EDGE  |  from cached tf_scan.csv")
    print(_line())
    path = os.path.join(DATA, "tf_scan.csv")
    if not os.path.exists(path):
        print("  no tf_scan.csv yet - run: python -c \"import multitf; ...\"")
        return
    import pandas as pd
    df = pd.read_csv(path)
    try:
        import multitf
        for line in multitf.best_tf_report(df)[:15]:
            print(line)
    except Exception as e:
        print(f"  tf summary failed: {e}")
    print()


def report_ml_context():
    print(_line())
    print("ML CONTEXT  |  strategy agreement (context, not trigger)")
    print(_line())
    try:
        import ml_engine
        res, err = ml_engine.meta_blender()
        if err:
            print(f"  ml context failed: {err}")
        else:
            for line in ml_engine.format_ml(res):
                print(line)
    except Exception as e:
        print(f"  ml context failed: {e}")
    print()


def report_regime_plan():
    print(_line())
    print("REGIME GATE + VIX  |  loss-avoidance core")
    print(_line())
    try:
        import regime_filter
        plan = regime_filter.trade_plan()
        print(regime_filter.format_plan(plan))
    except Exception as e:
        print(f"  regime plan failed: {e}")
    print()


def report_premium_seller():
    print(_line())
    print("PREMIUM SELLER  |  iron condor backtest (VIX+regime gated)")
    print(_line())
    try:
        import premium_seller
        t = premium_seller.premium_sell_backtest()
        for line in premium_seller.format_result(t):
            print(line)
    except Exception as e:
        print(f"  premium seller failed: {e}")
    print()


def main():
    report_regime_plan()
    report_options_chain("NIFTY")
    report_institutional()
    report_stock_flow(top=12)
    report_tf_summary()
    report_ml_context()
    report_premium_seller()
    try:
        from nse_live import close
        close()
    except Exception:
        pass
    if "--blog" in sys.argv:
        try:
            import blog_post
            blog_post.main()
        except Exception as e:
            print(f"blog post failed: {e}")


if __name__ == "__main__":
    main()
