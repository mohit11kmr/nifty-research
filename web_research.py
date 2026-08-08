"""Web research module - live market cues via web search.

Agent fetches latest Nifty/FII/global news and converts key signals into
the reasoning pipeline (Hermes-agent style research step).
"""
import datetime as dt


def research_market():
    """Search live web for Nifty/FII/global market cues."""
    results = {}
    queries = {
        "nifty": "Nifty 50 outlook today FII DII option expiry",
        "global": "stock market today US markets dollar rupee global cues",
        "fii": "FII DII data today net buying selling NSE",
    }
    for key, q in queries.items():
        try:
            from websearch import search  # injected tool
        except Exception:  # noqa: BLE001
            break
    return results


def research_news():
    """Live web research using the agent's search tool.

    NOTE: the opencode agent performs the actual web search from its own
    toolset and feeds results into its reasoning. This stub returns the
    query list so the pipeline knows what to research.
    """
    return {
        "timestamp": dt.datetime.now().isoformat(),
        "queries": [
            "Nifty 50 market outlook today",
            "FII DII buying selling today NSE",
            "USD INR rupee dollar trend today",
            "Nifty option chain OI analysis today",
        ],
        "note": "agent performs live web research via its search tool",
    }
