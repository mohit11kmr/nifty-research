"""NSE live data via headless Chrome - stock quotes, option chain, FII/DII.

NSE has encrypted its JSON API payloads (2025+). The only reliable free path is
running the real browser and calling the API from inside its JS context, where
the page's own decryption runs automatically. We use Playwright + system Chrome.
"""
import os
import time
import json
import datetime as dt

import pandas as pd

SYMBOLS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN", "BHARTIARTL",
    "ITC", "LT", "AXISBANK", "KOTAKBANK", "HINDUNILVR", "BAJFINANCE", "TITAN",
    "MARUTI", "SUNPHARMA", "TATAMOTORS", "WIPRO", "HCLTECH", "NTPC",
    "ADANIENT", "ADANIPORTS", "BAJAJFINSV", "ASIANPAINT", "ULTRACEMCO",
    "NESTLEIND", "TATASTEEL", "POWERGRID", "JSWSTEEL", "M&M", "HDFCLIFE",
    "SBILIFE", "DRREDDY", "CIPLA", "TECHM", "ONGC", "COALINDIA", "BPCL",
    "TATACONSUM", "BRITANNIA", "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO",
    "INDUSINDBK", "DIVISLAB", "APOLLOHOSP", "GRASIM", "HINDALCO", "DLF",
    "TRENT", "SIEMENS", "BEL", "HAL", "BHEL", "RECLTD", "PFC", "JIOFIN",
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36")

_cache = {"browser": None, "context": None, "page": None, "last": 0}


def _browser():
    """Lazy singleton browser (system Chrome, stealth flags)."""
    from playwright.sync_api import sync_playwright
    if _cache["browser"] is None:
        _cache["pw"] = sync_playwright().start()
        _cache["browser"] = _cache["pw"].chromium.launch(
            headless=True, channel="chrome",
            args=["--disable-blink-features=AutomationControlled"])
        ctx = _cache["browser"].new_context(user_agent=UA)
        _cache["context"] = ctx
        _cache["page"] = ctx.new_page()
        _cache["page"].add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})')
    return _cache["page"]


def _eval_fetch(page, url):
    """Run fetch() inside the page JS context (decryption runs automatically)."""
    return page.evaluate(
        """async (u) => { const r = await fetch(u, {headers:{'accept':'application/json'}});
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return await r.json(); }""", url)


def _boot_nse(page, symbol="NIFTY"):
    """Load the option chain page once so NSE issues bot cookies + decrypt key."""
    if time.time() - _cache["last"] > 60:
        for attempt in range(3):
            try:
                page.goto("https://www.nseindia.com/option-chain",
                          wait_until="domcontentloaded", timeout=60000)
                break
            except Exception:
                page.wait_for_timeout(3000)
        page.wait_for_timeout(4000)
        _cache["last"] = time.time()
    # force the v3 chain to load once (sets state for any symbol)
    try:
        info = _eval_fetch(page, f"https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}")
        expiry = (info.get("expiryDates") or [None])[0]
        if expiry:
            _eval_fetch(page, f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol}&expiry={expiry}")
    except Exception:
        pass


def fetch_quote_page(symbols):
    """Fetch live NIFTY/stock quotes from NSE quote page (real-time values)."""
    page = _browser()
    _boot_nse(page)
    out = []
    # Quote endpoint returns compact JSON with key fields
    for i, sym in enumerate(symbols):
        try:
            d = _eval_fetch(page, f"https://www.nseindia.com/api/quote-equity?symbol={sym}&section=trade_info")
            pr = d.get("priceInfo", {})
            mkt = d.get("marketDeptOrderBook", {})
            trade = d.get("tradeInfo", {})
            out.append({
                "symbol": sym,
                "name": d.get("meta", {}).get("companyName"),
                "close": pr.get("lastPrice"),
                "open": pr.get("open"),
                "high": pr.get("intraDayHighLow", {}).get("max"),
                "low": pr.get("intraDayHighLow", {}).get("min"),
                "pct_chg": pr.get("pChange"),
                "volume": trade.get("totalTradedVolume"),
                "delivery_pct": (d.get("securityWiseDPR", {}) or {}).get("deliveryToTradedQuantity"),
                "buy_qty": mkt.get("totalBuyQuantity"),
                "sell_qty": mkt.get("totalSellQuantity"),
                "prev_close": pr.get("previousClose"),
                "yield": None,
            })
        except Exception as e:
            print(f"  quote fail {sym}: {str(e)[:50]}")
        if i % 10 == 9:
            page.wait_for_timeout(800)
    return pd.DataFrame(out)


def fetch_option_chain_live(symbol="NIFTY", expiry=None, timeout_sec=30):
    """Live NSE option chain via browser. Returns (df, meta)."""
    page = _browser()
    _boot_nse(page, symbol)
    # Resolve first available expiry when none given (v3 API needs an expiry)
    if not expiry:
        try:
            info = _eval_fetch(page, f"https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}")
            expiries = info.get("expiryDates") or []
            expiry = expiries[0] if expiries else None
        except Exception:
            pass
    url = f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol}"
    if expiry:
        url += f"&expiry={expiry}"
    data = _eval_fetch(page, url)
    recs = data.get("records", data)
    meta = {
        "underlying": recs.get("underlyingValue"),
        "timestamp": recs.get("timestamp"),
        "expiries": (recs.get("expiryDates") or [])[:6],
        "expiry": recs.get("expiryDate") or expiry,
    }
    rows = []
    for item in recs.get("data", []):
        ce = item.get("CE") or {}
        pe = item.get("PE") or {}
        rows.append({
            "expiry": item.get("expiryDate") or meta["expiry"],
            "strike": item.get("strikePrice"),
            "ce_oi": ce.get("openInterest"),
            "ce_oi_chg": ce.get("changeinOpenInterest"),
            "ce_pct_chg": ce.get("pchangeinOpenInterest"),
            "ce_volume": ce.get("totalTradedVolume"),
            "ce_iv": ce.get("impliedVolatility"),
            "ce_ltp": ce.get("lastPrice"),
            "ce_buy_qty": ce.get("totalBuyQuantity"),
            "ce_sell_qty": ce.get("totalSellQuantity"),
            "pe_oi": pe.get("openInterest"),
            "pe_oi_chg": pe.get("changeinOpenInterest"),
            "pe_pct_chg": pe.get("pchangeinOpenInterest"),
            "pe_volume": pe.get("totalTradedVolume"),
            "pe_iv": pe.get("impliedVolatility"),
            "pe_ltp": pe.get("lastPrice"),
            "pe_buy_qty": pe.get("totalBuyQuantity"),
            "pe_sell_qty": pe.get("totalSellQuantity"),
        })
    df = pd.DataFrame(rows)
    for c in df.columns:
        if c != "expiry":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("strike").reset_index(drop=True)
    return df, meta


def close():
    if _cache["browser"]:
        try:
            _cache["browser"].close()
        except Exception:
            pass
        _cache["browser"] = None


if __name__ == "__main__":
    df, meta = fetch_option_chain_live("NIFTY")
    print("meta:", meta)
    print("strikes:", len(df))
    print(df[["strike", "ce_oi", "pe_oi", "ce_oi_chg", "pe_oi_chg"]].head(10).to_string(index=False))
    close()
