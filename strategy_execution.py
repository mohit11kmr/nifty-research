"""Phase I.2 - Generic Strategy Execution Layer (spec section 5).

Runs a compiled strategy proposal that is NOT one of the three engine-backed
strategies through a DETERMINISTIC execution family composed exclusively from
registered project primitives (backtest_frozen / multi_strategy_backtest /
expiry_calendar / indicators / cost_model).

Design invariants (spec sections 1/8/15/21):
  - nothing here executes arbitrary Python, eval, exec, shell or imports
  - no fabricated fills / quotes / OI / expiry; no future information
  - EOD resolution only (OPTIONS_EOD); an intraday/tick claim is rejected
  - family premium unit semantics are explicit (premium-per-unit, net credit,
    net debit); control premium is never reused across families
  - risk semantics are family-defined; never inferred from a generic field
  - the three frozen engine strategies are NEVER routed here
  - no parameter optimization, no mutation of the proposal after results

The research output is shaped identically to BacktestAdapter.run() so the
existing evaluation vector / baseline / result_hash pipeline is unchanged.
"""
import bisect
import datetime as dt

import backtest_frozen as bf
import expiry_calendar as exp_cal
import indicators
import multi_strategy_backtest as m
import strategy_schema as S
import strategy_execution_capabilities as C
from strategy_compiler import _apply, _coerce
from cost_model import COST_PER_TRADE, SLIPPAGE_PCT

# ---------------------------------------------------------------------------
# Reason vocabulary mapping (engine reasons -> spec exit vocabulary)
# ---------------------------------------------------------------------------
_REASON_MAP = {
    "STOP_LOSS": "STOP",
    "TAKE_PROFIT": "TARGET",
    "EXPIRY_SQUARE_OFF": "EXPIRY",
}

# ---------------------------------------------------------------------------
# Field resolution
# ---------------------------------------------------------------------------
# Indicators are trailing-only, so the full-frame value at date d equals the
# slice<=d value (the value the frozen evaluate_day funnel used). ema20/ema50
# are not produced by indicators.add_all_indicators and are added explicitly.
INDICATOR_FIELDS = {"ADX": "adx", "EMA20": "ema20", "EMA50": "ema50",
                    "RSI": "rsi14", "ATR": "atr14"}


def _oi_wall(ctx, rec, d):
    walls = rec.get("walls") or {}
    if walls.get("nearest_resistance") is not None:
        return float(walls["nearest_resistance"])
    if walls.get("nearest_support") is not None:
        return float(walls["nearest_support"])
    return None


FIELD_SOURCES = {
    "REGIME": lambda ctx, rec, d: rec.get("regime"),
    "VIX": lambda ctx, rec, d: rec.get("vix"),
    "VIX_ZONE": lambda ctx, rec, d: rec.get("vix_zone"),
    "PCR": lambda ctx, rec, d: rec.get("pcr"),
    "MAX_PAIN": lambda ctx, rec, d: rec.get("max_pain"),
    "FII_SENTIMENT": lambda ctx, rec, d: rec.get("fii_sentiment"),
    "ML_VERDICT": lambda ctx, rec, d: rec.get("ml_verdict"),
    "SPOT": lambda ctx, rec, d: rec.get("spot"),
    "GRADE": lambda ctx, rec, d: rec.get("grade"),
    "CONFLUENCE_SCORE": lambda ctx, rec, d: rec.get("confluence_score"),
    "ACTION": lambda ctx, rec, d: rec.get("action"),
    "SKEW": lambda ctx, rec, d: rec.get("skew_bias"),
    "OI_WALL": _oi_wall,
}


def field_value(ctx, rec, d, field):
    """The decision-time value of a spec field on day d. None when the field
    cannot be resolved on that day (never fabricated)."""
    if field in INDICATOR_FIELDS:
        return ctx.ind_row(d).get(INDICATOR_FIELDS[field])
    if rec is None:
        return None
    fn = FIELD_SOURCES.get(field)
    if fn is None:
        return None
    return fn(ctx, rec, d)


def _resolve_literal(ctx, rec, d, raw):
    """A condition's right-hand side: a field reference resolves to its value;
    everything else stays a literal."""
    if isinstance(raw, str) and (raw in FIELD_SOURCES or raw in INDICATOR_FIELDS):
        return field_value(ctx, rec, d, raw)
    return raw


# ---------------------------------------------------------------------------
# Project-rule entry conditions (curated, allowlisted refs only)
# ---------------------------------------------------------------------------
def _ev_regime_gate(ctx, rec, d):
    if rec.get("gate") is None or rec.get("regime") is None:
        return None
    return rec["gate"] != "NO_TRADE" and rec["regime"] != "RANGE_LV"


def _ev_options_layer(ctx, rec, d):
    return rec.get("l4_status") == "PASSED"


def _ev_technical(ctx, rec, d):
    bias = rec.get("tech_bias")
    return bias not in (None, "NEUTRAL")


def _ev_institutional(ctx, rec, d):
    return rec.get("l5_status") == "PASSED"


def _ev_ml(ctx, rec, d):
    return rec.get("l6_status") == "PASSED"


def _ev_sell_ok(ctx, rec, d):
    from premium_seller import sell_ok
    result = sell_ok(rec.get("regime"), rec.get("vix"))
    return result[0] if isinstance(result, tuple) else result


# project_ref -> day-level gate evaluator. Construction refs (simulate_trade,
# build_condor, ...) are intentionally NOT entry gates: if a proposal uses one
# as an entry condition the condition is reported None (not evaluable) and the
# entry is blocked honestly.
PROJECT_RULE_EVALUATORS = {
    "backtest_frozen.regime_gate_at": _ev_regime_gate,
    "backtest_frozen.options_layer_at": _ev_options_layer,
    "backtest_frozen.technical_verdict_at": _ev_technical,
    "backtest_frozen.institutional_layer_at": _ev_institutional,
    "backtest_frozen.ml_predict_at": _ev_ml,
    "premium_seller.sell_ok": _ev_sell_ok,
}


def _eval_condition(ctx, rec, d, cond):
    if not isinstance(cond, dict):
        return None
    if "field" in cond:
        field = cond["field"]
        left = field_value(ctx, rec, d, field)
        right = _resolve_literal(ctx, rec, d, cond.get("value"))
        if left is None or right is None:
            return None
        ftype = S.FIELD_TYPES.get(field)
        try:
            return bool(_apply(cond.get("operator"),
                               _coerce(left, ftype), _coerce(right, ftype)))
        except (TypeError, ValueError):
            return None
    if cond.get("rule") == S.PROJECT_RULE_TOKEN:
        fn = PROJECT_RULE_EVALUATORS.get(cond.get("project_ref"))
        if fn is None:
            return None
        try:
            result = fn(ctx, rec, d)
        except Exception:
            return None
        if result is None:
            return None
        if isinstance(result, tuple):
            result = result[0]
        return bool(result)
    return None


def evaluate_conditions(ctx, spec, rec, d):
    """Evaluate a spec's entry conditions at day d. Every condition must
    resolve; a single unresolved (None) condition blocks the entry."""
    conds = ((spec.get("entry") or {}).get("conditions") or {})
    detail = {"all": {}, "any": {}, "allowed": False}

    def _block(block, key):
        for i, cond in enumerate(block or []):
            cid = f"{key}[{i}]:{cond.get('id') or i}"
            detail[key][cid] = _eval_condition(ctx, rec, d, cond)

    _block(conds.get("all"), "all")
    _block(conds.get("any"), "any")
    all_ok = all(v is True for v in detail["all"].values())
    any_ok = any(v is True for v in detail["any"].values())
    has_any = bool(detail["any"])
    detail["allowed"] = all_ok and (not has_any or any_ok)
    return detail


# ---------------------------------------------------------------------------
# Data-field coverage gate (entry fields available on <50% of window days)
# ---------------------------------------------------------------------------
def _data_field_gate(spec, ctx):
    conds = ((spec.get("entry") or {}).get("conditions") or {})
    fields = []
    for block in ("all", "any"):
        for cond in conds.get(block) or []:
            if isinstance(cond, dict) and "field" in cond \
                    and cond["field"] not in fields:
                fields.append(cond["field"])
    usable = [str(d) for d in ctx.window
              if not (ctx.recs.get(str(d)) or {}).get("skip")]
    if not usable:
        return None
    for field in fields:
        if field not in FIELD_SOURCES and field not in INDICATOR_FIELDS:
            continue
        available = sum(1 for ds in usable
                        if field_value(ctx, ctx.recs.get(ds), ds, field) is not None)
        pct = C.coverage_failed(available, usable)
        if pct is not None:
            return (C.DATA_FIELD_UNSUPPORTED,
                    f"entry field {field!r} available on only {available}/"
                    f"{len(usable)} ({pct}%) window days (< {C.COVERAGE_MIN_PCT}%)")
    return None


# ---------------------------------------------------------------------------
# Shared read-only research context (cached per data_root; immutable artifacts)
# ---------------------------------------------------------------------------
_CONTEXT_CACHE = {}


class GenericContext:
    """The frozen research dataset + day records + indicator frame, loaded once
    per data_root. Only immutable dataset artifacts are cached."""

    def __init__(self, data_root=None):
        self.data_root = data_root
        old_root, old_cal = bf.ROOT, exp_cal.CALENDAR_CSV
        try:
            self.nifty, self.vix, self.fii, self.ml, self.snaps = \
                m.load_inputs(data_root=data_root)
            self.nifty_dates = m.nifty_dates_of(self.nifty)
            self.window = [d for d in self.nifty_dates
                           if bf.WINDOW_START <= d <= bf.WINDOW_END]
            self.recs = m.day_records(self.window, self.nifty, self.vix,
                                      self.fii, self.ml, self.snaps,
                                      self.nifty_dates)
            self._build_indicator_frame()
        finally:
            bf.ROOT, exp_cal.CALENDAR_CSV = old_root, old_cal

    def _build_indicator_frame(self):
        df = self.nifty.copy()
        indicators.add_all_indicators(df)
        df["ema20"] = indicators.ema(df["close"], 20)
        df["ema50"] = indicators.ema(df["close"], 50)
        df = df.dropna(subset=["adx", "bb_upper", "bb_lower"]).reset_index(drop=True)
        df["_d"] = df["date"].dt.date
        self._ind_dates = list(df["_d"])
        self._ind_rows = {
            row["_d"]: {
                "adx": _f(row["adx"]), "ema20": _f(row["ema20"]),
                "ema50": _f(row["ema50"]), "rsi14": _f(row["rsi14"]),
                "atr14": _f(row["atr14"]),
            } for _, row in df.iterrows()
        }

    def ind_row(self, d):
        """Trailing indicator row at day d (exact match else last row <= d)."""
        if isinstance(d, str):
            d = dt.date.fromisoformat(d)
        if d in self._ind_rows:
            return self._ind_rows[d]
        i = bisect.bisect_left(self._ind_dates, d) - 1
        if i < 0:
            return {}
        return self._ind_rows[self._ind_dates[i]]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _context(data_root=None):
    ctx = _CONTEXT_CACHE.get(data_root)
    if ctx is None:
        ctx = GenericContext(data_root=data_root)
        _CONTEXT_CACHE[data_root] = ctx
    return ctx


# ---------------------------------------------------------------------------
# Option construction helpers
# ---------------------------------------------------------------------------
def _round_strike(x):
    return int(round(x / 50.0) * 50)


def _side_strike(ctx, rec, d, side):
    """Control-style strike for a directional leg (walls else 1% OTM)."""
    walls = rec.get("walls") or {}
    spot = rec.get("spot")
    if side == "CE":
        base = (walls.get("nearest_resistance")
                if walls.get("nearest_resistance") is not None
                else (spot * 1.01 if spot else None))
    else:
        base = (walls.get("nearest_support")
                if walls.get("nearest_support") is not None
                else (spot * 0.99 if spot else None))
    if base is None:
        return None
    return _round_strike(base)


def _contract_listed(ctx, d, expiry, strike, side):
    """(expiry, strike, side) must exist in the day's chain (Phase F2 rule).
    Unavailable contract -> no trade, no silent substitution."""
    cdf = ctx.snaps.get(d)
    if cdf is None or "strike" not in cdf.columns or "expiry" not in cdf.columns:
        return False
    e = expiry.strftime("%d-%b-%Y")
    return bool(((cdf["expiry"] == e) & (cdf["strike"] == strike)).any())


# ---------------------------------------------------------------------------
# Credit vertical simulation (family-specific premium units + exit semantics)
# ---------------------------------------------------------------------------
def simulate_credit_vertical(t, spot, expiry, short_strike, long_strike, side,
                             nifty, snaps, nifty_dates):
    """Defined-risk CREDIT vertical. Sell ``short_strike``, buy ``long_strike``.

    CE credit spread: short < long (both calls; bearish fade).
    PE credit spread: long < short (both puts; bullish fade).

    Premium units are explicit: entry credit = short - long per unit.
    Day loop mirrors the frozen condor exit semantics (TARGET/STOP/TIME/EXPIRY/
    EOD) with 4 orders per round trip (canonical cost model).
    """
    ttm0 = max((expiry - t).days, 1)
    short_in = bf.price_strike_lookup(snaps, t, short_strike, side, expiry=expiry)
    short_in = short_in if short_in is not None \
        else bf.bs_premium(spot, short_strike, ttm0, bf.BS_SIGMA, side)
    long_in = bf.price_strike_lookup(snaps, t, long_strike, side, expiry=expiry)
    long_in = long_in if long_in is not None \
        else bf.bs_premium(spot, long_strike, ttm0, bf.BS_SIGMA, side)
    if short_in is None or long_in is None:
        return {"error": "NO_PRICE"}
    entry_credit = round(short_in - long_in, 2)
    if entry_credit <= 0:
        return {"error": "INVALID_CREDIT"}
    fill_in = round(short_in * (1 - SLIPPAGE_PCT) - long_in * (1 + SLIPPAGE_PCT), 2)
    dte = (expiry - t).days
    width = abs(long_strike - short_strike)
    max_loss = round(width - entry_credit, 2)

    idx = nifty_dates.index(t)
    mfe, mae = 0.0, 0.0
    log = []
    j = t
    for jj in nifty_dates[idx + 1:]:
        j = jj
        row = nifty[nifty["date"] == _ts(jj)].iloc[0]
        spot_j = float(row["close"])
        sm = m.contract_mark(snaps, jj, short_strike, side, expiry, spot=spot_j)
        lm = m.contract_mark(snaps, jj, long_strike, side, expiry, spot=spot_j)
        if sm is None or lm is None:
            continue
        cur_credit = round(sm - lm, 2)
        pnl = (entry_credit - cur_credit) * bf.LOT_SIZE
        mfe = max(mfe, pnl)
        mae = min(mae, pnl)
        reason = None
        if j == expiry:
            reason = "EXPIRY"
        elif cur_credit >= m.CONDOR_STOP_MULT * entry_credit:
            reason = "STOP"
        elif cur_credit <= (1 - m.CONDOR_TARGET_PCT) * entry_credit:
            reason = "TARGET"
        elif (jj - t).days >= dte - m.CONDOR_CLOSE_BEFORE_DAYS:
            reason = "TIME"
        if reason:
            fill_out = round(sm * (1 + SLIPPAGE_PCT) - lm * (1 - SLIPPAGE_PCT), 2)
            net = (fill_in - fill_out) * bf.LOT_SIZE - 4 * COST_PER_TRADE
            slip = SLIPPAGE_PCT * (short_in + long_in + sm + lm) * bf.LOT_SIZE
            return {"exit_date": str(j), "reason": reason,
                    "exit_credit": round(cur_credit, 2), "fill_out": round(fill_out, 2),
                    "net_pnl": round(net, 2), "slippage": round(slip, 2),
                    "mfe": round(mfe, 2), "mae": round(mae, 2),
                    "entry_credit": entry_credit, "max_loss": max_loss,
                    "days_held": (j - t).days, "log": log}
        log.append({"date": str(jj), "spot": spot_j, "credit": cur_credit})
    if j == t:
        return None
    sm = m.contract_mark(snaps, j, short_strike, side, expiry, spot=float(
        nifty[nifty["date"] == _ts(j)].iloc[0]["close"]))
    lm = m.contract_mark(snaps, j, long_strike, side, expiry, spot=float(
        nifty[nifty["date"] == _ts(j)].iloc[0]["close"]))
    if sm is None or lm is None:
        return None
    cur_credit = round(sm - lm, 2)
    fill_out = round(sm * (1 + SLIPPAGE_PCT) - lm * (1 - SLIPPAGE_PCT), 2)
    net = (fill_in - fill_out) * bf.LOT_SIZE - 4 * COST_PER_TRADE
    slip = SLIPPAGE_PCT * (short_in + long_in + sm + lm) * bf.LOT_SIZE
    return {"exit_date": str(j), "reason": "EOD", "exit_credit": round(cur_credit, 2),
            "fill_out": round(fill_out, 2), "net_pnl": round(net, 2),
            "slippage": round(slip, 2), "mfe": round(mfe, 2), "mae": round(mae, 2),
            "entry_credit": entry_credit, "max_loss": max_loss,
            "days_held": (j - t).days, "log": log}


def _ts(d):
    import pandas as pd
    return pd.Timestamp(d)


# ---------------------------------------------------------------------------
# Execution families
# ---------------------------------------------------------------------------
class OptionBuyExecutor:
    """NAKED_OPTION + DIRECTIONAL, exactly one option_side."""

    family_id = "OPTION_BUY"
    candidate_key = "A_CURRENT_CONTROL"   # 2 orders / round trip

    def __init__(self, compilation, family):
        self.compilation = compilation
        self.family = family
        self.spec = compilation.compiled.spec
        self.sides = tuple(self.spec.get("instrument", {}).get("option_side") or [])
        if len(self.sides) != 1:
            raise ValueError(
                f"EXECUTION_UNSUPPORTED: {C.POSITION_CONSTRUCTION_UNSUPPORTED}: "
                f"NAKED_OPTION DIRECTIONAL requires exactly one option_side "
                f"(got {list(self.sides)})")

    def run(self, ctx):
        trades = []
        side = self.sides[0]
        for d in ctx.nifty_dates:
            rec = ctx.recs.get(str(d))
            if not rec or rec.get("skip"):
                continue
            if not evaluate_conditions(ctx, self.spec, rec, d)["allowed"]:
                continue
            expiry = exp_cal.get_expiry_for_trade_date(d)
            if expiry is None:
                continue  # EXPIRY_UNRESOLVED -> no trade (spec section 13)
            strike = _side_strike(ctx, rec, d, side)
            if strike is None or not _contract_listed(ctx, d, expiry, strike, side):
                continue
            spot = rec["spot"]
            ttm = max((expiry - d).days, 1)
            ltp = bf.price_strike_lookup(ctx.snaps, d, strike, side, expiry=expiry)
            entry = ltp if ltp is not None \
                else bf.bs_premium(spot, strike, ttm, bf.BS_SIGMA, side)
            if not entry or entry <= 0:
                entry = round(spot * 0.006, 2)
            entry = round(float(entry), 2)
            atr = max(10.0, entry * 0.25)
            sl = round(max(2.0, entry - 1.5 * atr), 2)
            target = round(entry + 2.0 * (entry - sl), 2)
            sim = bf.simulate_trade(d, spot, entry, sl, target, strike, side,
                                    expiry, ctx.nifty, ctx.snaps, ctx.nifty_dates)
            if sim is None:
                continue
            sim = dict(sim)
            sim["reason"] = _REASON_MAP.get(sim["reason"], sim["reason"])
            mfe, mae = m._control_mfe_mae(d, expiry, strike, side, entry,
                                          ctx.nifty, ctx.snaps, ctx.nifty_dates, sim)
            out = dict(rec)
            out["expiry"] = str(expiry)
            out["option_type"] = side
            out["strike"] = strike
            out["entry_premium"] = entry
            out["sl_premium"] = sl
            out["target_premium"] = target
            out["simulation"] = sim
            out["mfe"] = mfe
            out["mae"] = mae
            trades.append(out)
        return trades


class CreditVerticalExecutor:
    """DEFINED_RISK_DIRECTIONAL credit spread (CALL or PUT)."""

    candidate_key = "B_DIRECTIONAL_SPREAD"   # 4 orders / round trip

    def __init__(self, compilation, family):
        self.compilation = compilation
        self.family = family
        self.spec = compilation.compiled.spec
        self.family_id = family.family_id
        self.sides = tuple(self.spec.get("instrument", {}).get("option_side") or [])
        if len(self.sides) != 1:
            raise ValueError(
                f"EXECUTION_UNSUPPORTED: {C.POSITION_CONSTRUCTION_UNSUPPORTED}: "
                f"credit vertical requires exactly one option_side "
                f"(got {list(self.sides)})")
        if self.family_id not in ("CALL_CREDIT_SPREAD", "PUT_CREDIT_SPREAD"):
            raise ValueError(
                f"EXECUTION_UNSUPPORTED: {C.FAMILY_NOT_REGISTERED}: debit "
                f"verticals are resolved but not registered this phase "
                f"(family {self.family_id!r})")

    def run(self, ctx):
        trades = []
        side = self.sides[0]
        for d in ctx.nifty_dates:
            rec = ctx.recs.get(str(d))
            if not rec or rec.get("skip"):
                continue
            if not evaluate_conditions(ctx, self.spec, rec, d)["allowed"]:
                continue
            expiry = exp_cal.get_expiry_for_trade_date(d)
            if expiry is None:
                continue
            short_strike = _side_strike(ctx, rec, d, side)
            if short_strike is None:
                continue
            sign = 1 if side == "CE" else -1
            long_strike = short_strike + sign * m.SPREAD_WIDTH
            if not _contract_listed(ctx, d, expiry, short_strike, side) \
                    or not _contract_listed(ctx, d, expiry, long_strike, side):
                continue
            sim = simulate_credit_vertical(d, rec["spot"], expiry, short_strike,
                                           long_strike, side, ctx.nifty,
                                           ctx.snaps, ctx.nifty_dates)
            if sim is None:
                continue
            if sim.get("error"):
                continue
            out = dict(rec)
            out["expiry"] = str(expiry)
            out["option_type"] = self.family_id
            out["strike"] = short_strike
            out["short_strike"] = long_strike
            out["spread_width"] = abs(long_strike - short_strike)
            out["simulation"] = sim
            out["mfe"] = sim.get("mfe")
            out["mae"] = sim.get("mae")
            trades.append(out)
        return trades


class IronCondorExecutor:
    """DEFINED_RISK_RANGE symmetric four-leg condor (single position at a time,
    mirroring run_candidate_c's position management)."""

    family_id = "IRON_CONDOR"
    candidate_key = "C_RANGE_HV_IRON_CONDOR"   # 8 orders / round trip

    def __init__(self, compilation, family):
        self.compilation = compilation
        self.family = family
        self.spec = compilation.compiled.spec

    def run(self, ctx):
        trades = []
        pos = None
        for d in ctx.nifty_dates:
            if pos is not None:
                if pos["sim"] is not None and str(d) == pos["sim"]["exit_date"]:
                    sim = pos["sim"]
                    rec = dict(pos["rec"])
                    rec["simulation"] = sim
                    rec["mfe"] = sim.get("mfe")
                    rec["mae"] = sim.get("mae")
                    rec["option_type"] = "IRON_CONDOR"
                    rec["strike"] = (f"{pos['strikes'][2]:.0f}/{pos['strikes'][0]:.0f}-"
                                     f"{pos['strikes'][1]:.0f}/{pos['strikes'][3]:.0f}")
                    trades.append(rec)
                    pos = None
                continue
            rec = ctx.recs.get(str(d))
            if not rec or rec.get("skip"):
                continue
            if not evaluate_conditions(ctx, self.spec, rec, d)["allowed"]:
                continue
            expiry = exp_cal.get_expiry_for_trade_date(d)
            if expiry is None:
                continue
            strikes = m.build_condor(rec["spot"], expiry, ctx.snaps, d)
            if strikes is None:
                continue
            legs = m.condor_legs(ctx.snaps, d, expiry, *strikes, rec["spot"])
            if legs is None:
                continue
            credit = (legs["Kc"] + legs["Kp"]) - (legs["KcW"] + legs["KpW"])
            if credit <= 0:
                continue
            sim = m.simulate_condor(d, rec["spot"], expiry, strikes,
                                    ctx.nifty, ctx.snaps, ctx.nifty_dates)
            if sim is None or not sim.get("exit_date"):
                continue
            pos = {"sim": sim, "expiry": expiry, "strikes": strikes, "rec": dict(rec)}
        return trades


# ---------------------------------------------------------------------------
# Generic run (research-output shape identical to BacktestAdapter.run)
# ---------------------------------------------------------------------------
def run_generic(compilation, data_root=None):
    """Deterministic generic backtest for a compiled proposal.

    Raises ValueError("EXECUTION_UNSUPPORTED: <CODE>: <reason>") when the
    proposal cannot be executed by a registered deterministic family.
    """
    executor = None
    from strategy_execution_registry import default_registry
    executor = default_registry().compile_executor(compilation)

    ctx = _context(data_root)
    gate = _data_field_gate(compilation.compiled.spec, ctx)
    if gate:
        raise ValueError(f"EXECUTION_UNSUPPORTED: {gate[0]}: {gate[1]}")

    trades = executor.run(ctx)
    rows = m.trade_rows(executor.candidate_key, trades)
    metrics = m.compute_metrics(executor.candidate_key, rows, len(ctx.window))
    metrics["candidate"] = executor.family_id
    return {
        "strategy_id": compilation.strategy_id,
        "candidate_key": executor.family_id,
        "trades": rows,
        "metrics": metrics,
        "by_regime": m.group_by(rows, "regime"),
        "monthly": m.monthly_rows(rows),
        "fingerprints": m.fingerprints(ctx.nifty, ctx.vix, ctx.fii, ctx.ml,
                                       ctx.snaps, data_root=data_root),
        "spec_hash": compilation.spec_hash,
    }
