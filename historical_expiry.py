"""Phase F2: historical NIFTY expiry/contract calendar (point-in-time).

Derives the ACTUAL weekly option contract applicable on each historical
observation day from the Phase F bhavcopy manifest. The bhavcopy for day `d`
lists every contract expiry that was listed/tradable on day `d`; the applicable
weekly contract for an entry on day `d` is the shortest-dated listed expiry
strictly after `d` (same "current week's contract, unless it expires today"
semantics as the frozen `next_thursday` model, but using the real calendar).

This automatically captures:
  * Thursday weekly convention (through 2025-08-28)
  * Tuesday weekly convention (from 2025-09-02, SEBI uniform weekly expiry)
  * holiday-shifted Monday weeklies (Diwali 2025-10-20, etc.)

No-lookahead: only the expiry list of day `d` itself is used — the contract
dates were published/listed before the decision timestamp.

Only the expiry/contract LOOKUP is corrected here. No strategy logic lives in
this module.
"""
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(ROOT, "data", "historical", "manifest.json")
CALENDAR_CSV = os.path.join(ROOT, "data", "historical", "expiry_calendar.csv")


def load_manifest():
    with open(MANIFEST) as f:
        return json.load(f)


def build_expiry_calendar(manifest=None):
    """observation_date -> applicable weekly expiry (min expiry > d listed on d).

    Returns list of dicts (date, expiry, weekday, days_to_expiry, available).
    Deterministic (sorted by date).
    """
    manifest = manifest or load_manifest()
    out = []
    for key in sorted(manifest):
        d = dt.date.fromisoformat(key)
        exps = sorted(manifest[key].get("expiries", []))
        future = [e for e in exps if e > key]
        if not future:
            out.append({"date": key, "expiry": None, "weekday": None,
                        "days_to_expiry": None, "available": False})
            continue
        exp = dt.date.fromisoformat(future[0])
        out.append({"date": key, "expiry": future[0],
                    "weekday": exp.strftime("%A"), "days_to_expiry": (exp - d).days,
                    "available": True})
    return out


def save_calendar(rows=None, path=CALENDAR_CSV):
    import pandas as pd
    rows = rows if rows is not None else build_expiry_calendar()
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def load_calendar(path=CALENDAR_CSV):
    """dict date-iso -> (expiry-date, weekday, days_to_expiry, available)."""
    import pandas as pd
    if not os.path.exists(path):
        rows = build_expiry_calendar()
        save_calendar(rows, path)
        df = pd.DataFrame(rows)
    else:
        df = pd.read_csv(path)
    d = {}
    for _, r in df.iterrows():
        d[str(r["date"])] = (
            dt.date.fromisoformat(str(r["expiry"])) if r.get("expiry") and str(r["expiry"]) != "nan" else None,
            r.get("weekday"),
            None if r.get("days_to_expiry") != r.get("days_to_expiry") else int(r["days_to_expiry"]),
            bool(r.get("available")),
        )
    return d


def applicable_expiry(d, calendar=None):
    """Applicable contract expiry date for observation date d (dt.date)."""
    if calendar is None:
        calendar = load_calendar()
    rec = calendar.get(d.isoformat())
    if rec is None or rec[3] is False:
        return None
    return rec[0]


def weekly_expiry_series(rows=None):
    """Distinct applicable expiry dates in order with weekday and gap."""
    rows = rows if rows is not None else build_expiry_calendar()
    seen, order = {}, []
    for r in rows:
        if r["expiry"] and r["expiry"] not in seen:
            seen[r["expiry"]] = r["weekday"]
            order.append((r["expiry"], r["weekday"]))
    return order


def detect_transition(rows=None):
    """Report the Thursday -> Tuesday weekly-expiry convention change.

    Evidence-driven: the first weekly expiry after a run of Thursdays whose
    weekday differs (gap skips the Thursday). Returns dict or None.
    """
    series = weekly_expiry_series(rows)
    prev_wd = None
    for exp, wd in series:
        if prev_wd == "Thursday" and wd != "Thursday":
            last_thu = series[series.index((exp, wd)) - 1][0]
            return {"last_thursday_weekly": last_thu,
                    "first_new_weekly": exp,
                    "new_weekday": wd,
                    "transition_observation": last_thu,
                    "evidence": "bhavcopy listed expiry series"}
        prev_wd = wd
    return None


if __name__ == "__main__":
    rows = build_expiry_calendar()
    save_calendar(rows)
    t = detect_transition(rows)
    series = weekly_expiry_series(rows)
    print(f"calendar rows: {len(rows)}  weekly expiries: {len(series)}")
    print(f"first weekly: {series[0]}")
    print(f"last weekly: {series[-1]}")
    print("transition:", t)
    print("example mapping (window edge days):")
    for d in ("2025-08-13", "2025-08-28", "2025-09-02", "2025-10-20",
              "2026-08-11", "2026-08-12"):
        print(" ", d, "->", applicable_expiry(dt.date.fromisoformat(d)))
