"""Phase I.3 - Feature Registry (spec section 13).

Every research feature must be declared here before the engine may produce it
and before any AI proposal may reference it. A feature declaration carries:

    feature_id        - stable identifier used in proposals/backtests
    description       - what it measures
    source_fields     - exact dataset columns consumed
    lookback          - max sessions of history used (0 = same-session only)
    point_in_time_safe- always True (verified by construction in the engine)
    granularity       - 'daily'
    formula_version   - bumps whenever the formula changes (invalidates cache)

Unknown features cannot enter AI proposals (research_ai_packet enforces this).
"""
FEATURES = [
    # ---- spot / returns / volatility --------------------------------------
    {"feature_id": "nifty_close", "description": "NIFTY close", "source_fields": ["nifty.close"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_ret_1d", "description": "1-session NIFTY return (close/close)", "source_fields": ["nifty.close"],
     "lookback": 1, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_ret_5d", "description": "5-session NIFTY return", "source_fields": ["nifty.close"],
     "lookback": 5, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_ret_20d", "description": "20-session NIFTY return", "source_fields": ["nifty.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_gap_pct", "description": "open vs previous close (%)", "source_fields": ["nifty.open", "nifty.close"],
     "lookback": 1, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_20d_hv", "description": "20-session realized volatility (annualized)", "source_fields": ["nifty.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_atr_14_pct", "description": "14-session ATR as % of close", "source_fields": ["nifty.open", "nifty.high", "nifty.low", "nifty.close"],
     "lookback": 14, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_ma20_dist_pct", "description": "close vs 20-session SMA (%)", "source_fields": ["nifty.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_ma50_dist_pct", "description": "close vs 50-session SMA (%)", "source_fields": ["nifty.close"],
     "lookback": 50, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_trend_20d", "description": "20-session linear-trend slope (%/session)", "source_fields": ["nifty.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_above_ma20", "description": "close > 20-session SMA (1/0)", "source_fields": ["nifty.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "nifty_above_ma50", "description": "close > 50-session SMA (1/0)", "source_fields": ["nifty.close"],
     "lookback": 50, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},

    # ---- VIX ---------------------------------------------------------------
    {"feature_id": "vix_close", "description": "India VIX close", "source_fields": ["vix.close"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "vix_ret_5d", "description": "5-session VIX change (%)", "source_fields": ["vix.close"],
     "lookback": 5, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "vix_ret_20d", "description": "20-session VIX change (%)", "source_fields": ["vix.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "vix_rank_252", "description": "percentile of VIX within trailing 252 sessions", "source_fields": ["vix.close"],
     "lookback": 252, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "vix_20d_mean", "description": "20-session mean VIX", "source_fields": ["vix.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "vix_20d_std", "description": "20-session std of VIX", "source_fields": ["vix.close"],
     "lookback": 20, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "vix_zone", "description": "premium zone 1-5 (CHEAP<12, NORMAL 12-16, RICH 16-20, HIGH 20-25, PANIC>25)",
     "source_fields": ["vix.close"], "lookback": 0, "point_in_time_safe": True,
     "granularity": "daily", "formula_version": "v1"},

    # ---- option chain (nearest expiry only) --------------------------------
    {"feature_id": "dte", "description": "days to nearest weekly expiry", "source_fields": ["options.expiry"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "expiry_day", "description": "1 when session is an option expiry", "source_fields": ["options.expiry"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "near_expiry", "description": "nearest weekly expiry date (> session)", "source_fields": ["options.expiry"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "pcr_oi", "description": "put/call open interest ratio (nearest expiry)", "source_fields": ["options.oi", "options.option_type"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "pcr_oi_chg", "description": "put/call OI-change ratio (nearest expiry)", "source_fields": ["options.oi_chg", "options.option_type"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "call_oi", "description": "total call OI (nearest expiry)", "source_fields": ["options.oi"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "put_oi", "description": "total put OI (nearest expiry)", "source_fields": ["options.oi"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "total_oi_near", "description": "total OI (nearest expiry)", "source_fields": ["options.oi"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "max_pain_strike", "description": "max-pain strike (ATM band, least total payout)", "source_fields": ["options.strike", "options.oi", "options.option_type"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "max_pain_dist_pct", "description": "|spot - max pain| / spot", "source_fields": ["options.strike", "options.oi"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "atm_strike", "description": "strike nearest to spot", "source_fields": ["options.strike", "options.underlying_price"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "atm_premium_pct", "description": "near-ATM option settle as % of spot (vol proxy)", "source_fields": ["options.settle_price", "options.strike", "options.underlying_price"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "otm_call_oi_share", "description": "share of call OI at strikes >1% above spot", "source_fields": ["options.oi", "options.strike"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "otm_put_oi_share", "description": "share of put OI at strikes >1% below spot", "source_fields": ["options.oi", "options.strike"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "chain_volume_total", "description": "total option volume (nearest expiry)", "source_fields": ["options.volume"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "chain_call_volume_share", "description": "call share of total option volume", "source_fields": ["options.volume", "options.option_type"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},

    # ---- market-wide OI + participant flow ---------------------------------
    {"feature_id": "oi_total", "description": "total option OI across all expiries", "source_fields": ["options.oi"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "oi_total_chg", "description": "total option OI change (all expiries)", "source_fields": ["options.oi_chg"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "oi_total_growth_5d", "description": "5-session growth of total option OI (%)", "source_fields": ["options.oi"],
     "lookback": 5, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "fii_oi_contracts", "description": "FII participant-OI contracts (EQ derivatives)", "source_fields": ["participant_oi.contracts"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "fii_oi_share", "description": "FII share of participant OI", "source_fields": ["participant_oi.contracts"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "fii_oi_share_chg_5d", "description": "5-session change in FII OI share (pp)", "source_fields": ["participant_oi.contracts"],
     "lookback": 5, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "client_oi_share", "description": "Client share of participant OI", "source_fields": ["participant_oi.contracts"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "pro_oi_share", "description": "Pro (proprietary) share of participant OI", "source_fields": ["participant_oi.contracts"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
    {"feature_id": "dii_oi_share", "description": "DII share of participant OI", "source_fields": ["participant_oi.contracts"],
     "lookback": 0, "point_in_time_safe": True, "granularity": "daily", "formula_version": "v1"},
]

BY_ID = {f["feature_id"]: f for f in FEATURES}


def feature_version():
    """Deterministic hash over every formula_version -> cache key component."""
    import hashlib
    payload = "\n".join(sorted(f"{f['feature_id']}={f['formula_version']}" for f in FEATURES))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def registered_ids():
    return set(BY_ID)


def get(feature_id):
    return BY_ID.get(feature_id)


def require_registered(feature_ids):
    """Raise when a proposal references an undeclared feature."""
    unknown = sorted(set(feature_ids) - registered_ids())
    if unknown:
        raise ValueError(f"unknown features referenced by proposal: {unknown}")
