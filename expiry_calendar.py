"""Canonical NIFTY weekly-expiry service (single owner, Phase F3).

One authoritative expiry model shared by EVERY expiry-sensitive layer:

  * historical frozen replay     -> backtest_frozen.py
  * live/paper auto-exit engine  -> exit_evaluator.py (via paper_execution.py)
  * read-only expiry status      -> mcp_nifty.py / timing.py

Model (evidence-based, deterministic, no-lookahead):
  * Historical trade dates (inside the Phase F bhavcopy window): the EXACT
    observed expiry from data/historical/expiry_calendar.csv (derived by
    historical_expiry.py from the day-d bhavcopy listed-expiry evidence):
      - Thursday weeklies through 2025-08-28
      - Tuesday weeklies from 2025-09-02 (SEBI uniform weekly expiry)
      - Monday weekly shifts when the Tuesday is a market holiday
        (Diwali 2025-10-20, 2026-03-02, 2026-03-30, 2026-04-13)
  * Forward dates (beyond the window): the same post-transition Tuesday
    weekly convention; pre-transition dates use the Thursday convention.
    For LIVE paper positions the actual exchange-chain contract expiry
    (position/quote envelope) stays authoritative; this rule only fills the
    no-quote fallback and read-only status.

Contract-selection semantics (shared with the frozen model): the applicable
expiry for an entry on day d is the shortest-dated listed weekly expiry
STRICTLY after d ("current week's contract, unless it expires today").

Times are NOT duplicated here: square-off / last-entry times are read from
regime_filter (the single owner of risk/expiry-time constants).

No strategy logic lives in this module.
"""
import datetime as dt
import hashlib
import os

import historical_expiry as _hist

ROOT = os.path.dirname(os.path.abspath(__file__))
CALENDAR_CSV = os.path.join(ROOT, "data", "historical", "expiry_calendar.csv")

# ---- era boundary (evidence: historical_expiry.detect_transition) --------
TRANSITION_DATE = dt.date(2025, 9, 2)   # first Tuesday weekly (SEBI change)
LAST_THURSDAY_WEEKLY = dt.date(2025, 8, 28)

TUESDAY = 1
THURSDAY = 3

_CALENDAR = None


def _calendar():
    """Lazy-loaded historical calendar dict (date-iso -> (expiry, weekday, days, avail))."""
    global _CALENDAR
    if _CALENDAR is None:
        _CALENDAR = _hist.load_calendar(CALENDAR_CSV)
    return _CALENDAR


def _observed_expiry_dates():
    """Sorted distinct expiry dates observed in the historical calendar."""
    exps = sorted({rec[0] for rec in _calendar().values() if rec[0] is not None})
    return exps


# ---------------------------------------------------------------------------
# forward rule (dates outside the observed calendar window)
# ---------------------------------------------------------------------------
def _forward_expiry(d):
    """Canonical weekly expiry strictly after d for dates not in the calendar.

    Era-aware: Thursday before 2025-09-02, Tuesday from 2025-09-02.
    """
    target = THURSDAY if d < TRANSITION_DATE else TUESDAY
    delta = (target - d.weekday()) % 7
    if delta == 0:
        delta = 7
    return d + dt.timedelta(days=delta)


def _forward_is_expiry_day(d):
    """Forward expiry-day predicate for dates outside the observed window."""
    target = THURSDAY if d < TRANSITION_DATE else TUESDAY
    return d.weekday() == target


# ---------------------------------------------------------------------------
# public API (single-owner expiry truth)
# ---------------------------------------------------------------------------
def get_expiry_for_trade_date(d):
    """Applicable weekly contract expiry for trade date d (dt.date).

    Same semantics as the frozen model: current week's contract, unless it
    expires today -> the next weekly. Historical dates use the observed
    calendar; forward dates use the era's weekly convention.
    """
    rec = _calendar().get(d.isoformat())
    if rec is not None and rec[3] and rec[0] is not None:
        return rec[0]
    return _forward_expiry(d)


def is_expiry_day(d):
    """True if a NIFTY weekly contract expires on date d.

    In-window dates use the observed expiry set (catches holiday Monday
    shifts). Out-of-window dates use the era's weekly weekday.
    """
    obs = _observed_expiry_dates()
    if obs and obs[0] <= d <= obs[-1]:
        return d in set(obs)
    return _forward_is_expiry_day(d)


def next_expiry(d):
    """Next weekly expiry strictly after d (dt.date). Alias of get_expiry_for_trade_date."""
    return get_expiry_for_trade_date(d)


def expiry_era(d):
    """Convention era for date d: 'thursday' before transition else 'tuesday'."""
    return "thursday" if d < TRANSITION_DATE else "tuesday"


def describe(d):
    """Read-only status dict for a date (used by status tools and tests)."""
    expiry = get_expiry_for_trade_date(d)
    obs = _observed_expiry_dates()
    in_window = bool(obs and obs[0] <= d <= obs[-1])
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "era": expiry_era(d),
        "source": "historical_calendar" if in_window else "forward_rule",
        "next_expiry": expiry.isoformat(),
        "days_to_expiry": (expiry - d).days,
        "is_expiry_day": is_expiry_day(d),
    }


# ---------------------------------------------------------------------------
# time constants (single owner of the VALUES is regime_filter - no duplicate)
# ---------------------------------------------------------------------------
def squareoff_hhmm():
    """Square-off trigger time "HH:MM" (IST), inclusive.

    CANONICAL value "15:05" (the current source trigger, previously
    exit_evaluator.SQUARE_OFF_HHMM; regime_filter.EXPIRY_SQUARE_OFF_HOUR=15.0
    documents "square off by 15:05"). Held here as the single owner so the
    historical replay, paper exit, and status layers cannot diverge. Deliberately
    NOT derived arithmetically from 15.0 (would shift the trigger to 15:00).
    """
    return "15:05"


def last_entry_hhmm():
    """Last allowed entry time on an expiry day "HH:MM" (IST).

    Source: regime_filter.EXPIRY_LAST_ENTRY_HOUR = 14.5 (no new entries after
    14:30). Rendered here only.
    """
    from regime_filter import EXPIRY_LAST_ENTRY_HOUR
    hh = int(EXPIRY_LAST_ENTRY_HOUR)
    return f"{hh:02d}:{(EXPIRY_LAST_ENTRY_HOUR - hh) * 60:02.0f}"


# ---------------------------------------------------------------------------
# contract expiry-string parsing (single parser, shared by all layers)
# ---------------------------------------------------------------------------
def parse_expiry(value):
    """Parse a contract expiry string ('18-Aug-2026', '18 Aug 2026',
    '2026-08-18') to a dt.date. Returns None when unparseable."""
    if value is None:
        return None
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(str(value).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# provenance / determinism
# ---------------------------------------------------------------------------
def fingerprint():
    """sha256 of the calendar artifact (unchanged content -> unchanged hash)."""
    h = hashlib.sha256()
    with open(CALENDAR_CSV, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    for d in (dt.date(2025, 8, 28), dt.date(2025, 9, 1), dt.date(2025, 9, 2),
              dt.date(2025, 10, 20), dt.date(2026, 8, 11), dt.date(2026, 8, 13),
              dt.date(2026, 8, 18), dt.date(2026, 8, 25)):
        print(describe(d))
    print("square_off:", squareoff_hhmm(), " last_entry:", last_entry_hhmm())
    print("calendar fingerprint:", fingerprint()[:8])
