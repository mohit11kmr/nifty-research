"""Web research module - live market cues via web search.

Agent fetches latest Nifty/FII/global news and converts key signals into
the reasoning pipeline (Hermes-agent style research step).
"""
import datetime as dt


def research_market():
    """Search live web/news RSS for Nifty/FII/global market cues."""
    results = {}
    # Try agent tool first if available
    try:
        from websearch import search
        queries = {
            "nifty": "Nifty 50 outlook today FII DII option expiry",
            "global": "stock market today US markets dollar rupee global cues",
            "fii": "FII DII data today net buying selling NSE",
        }
        for key, q in queries.items():
            results[key] = search(q)
        return results
    except Exception:
        pass

    # Fallback to free Google News RSS for live market cues
    import xml.etree.ElementTree as ET
    import requests
    queries = {
        "nifty": "Nifty+50+stock+market+India",
        "global": "US+markets+dollar+rupee+global+cues",
        "fii": "FII+DII+buying+selling+NSE+India",
    }
    headers = {"User-Agent": "Mozilla/5.0"}
    for key, q in queries.items():
        try:
            url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                titles = [item.find("title").text for item in root.findall(".//item")[:5] if item.find("title") is not None]
                results[key] = titles
        except Exception as e:
            results[key] = [f"Fetch error: {e}"]
    return results


def research_news():
    """Live web research using RSS or agent search tool."""
    cues = research_market()
    return {
        "timestamp": dt.datetime.now().isoformat(),
        "queries": [
            "Nifty 50 market outlook today",
            "FII DII buying selling today NSE",
            "USD INR rupee dollar trend today",
            "Nifty option chain OI analysis today",
        ],
        "live_headlines": cues,
        "note": "agent performs live web research via RSS/search tool",
    }

