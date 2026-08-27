# HISTORICAL NIFTY EXPIRY CALENDAR (Phase F2)

Window: **2025-08-13 -> 2026-08-13** (245 trading days + the 2026-08-11 gap day = 246 observation dates with bhavcopy).

## Source of truth

Derived deterministically from the Phase F bhavcopy manifest (`data/historical/manifest.json`, 246 entries, each with source URL + zip-sha256).
For each observation day `d`, the applicable weekly contract = the shortest-dated listed expiry strictly after `d` in the day-`d` chain (`min{e : e > d}`). This is exactly the historical analog of the frozen `next_thursday` model: the current-week contract, unless it expires today.

Machine-readable artifact: `data/historical/expiry_calendar.csv` (246 rows, sha256 `3abbe4ccb003d9f9228d9bdfaf73041403dae5ed4a43f30e223bc9fc6b426ad2`).

## Weekly expiry convention & transition

- **Thursday convention** through **2025-08-28** (last Thursday weekly).
- **Tuesday convention** from **2025-09-02** (SEBI uniform weekly-expiry change).
- Holiday-shifted **Monday** weeklies occur when the Tuesday is a market holiday (2025-10-20 Diwali, 2026-03-02, 2026-03-30, 2026-04-13).

Transition (repository evidence - bhavcopy listed-expiry series):

| | |
|---|---|
| last Thursday weekly | 2025-08-28 |
| first Tuesday weekly | 2025-09-02 |
| new weekday | Tuesday |

## Complete weekly expiry series (54 weeklies)

| # | expiry | weekday | gap(days) |
|---|--------|---------|-----------|
| 1 | 2025-08-14 | Thursday |  |
| 2 | 2025-08-21 | Thursday | 7 |
| 3 | 2025-08-28 | Thursday | 7 |
| 4 | 2025-09-02 | Tuesday | 5 |
| 5 | 2025-09-09 | Tuesday | 7 |
| 6 | 2025-09-16 | Tuesday | 7 |
| 7 | 2025-09-23 | Tuesday | 7 |
| 8 | 2025-09-30 | Tuesday | 7 |
| 9 | 2025-10-07 | Tuesday | 7 |
| 10 | 2025-10-14 | Tuesday | 7 |
| 11 | 2025-10-20 | Monday | 6 |
| 12 | 2025-10-28 | Tuesday | 8 |
| 13 | 2025-11-04 | Tuesday | 7 |
| 14 | 2025-11-11 | Tuesday | 7 |
| 15 | 2025-11-18 | Tuesday | 7 |
| 16 | 2025-11-25 | Tuesday | 7 |
| 17 | 2025-12-02 | Tuesday | 7 |
| 18 | 2025-12-09 | Tuesday | 7 |
| 19 | 2025-12-16 | Tuesday | 7 |
| 20 | 2025-12-23 | Tuesday | 7 |
| 21 | 2025-12-30 | Tuesday | 7 |
| 22 | 2026-01-06 | Tuesday | 7 |
| 23 | 2026-01-13 | Tuesday | 7 |
| 24 | 2026-01-20 | Tuesday | 7 |
| 25 | 2026-01-27 | Tuesday | 7 |
| 26 | 2026-02-03 | Tuesday | 7 |
| 27 | 2026-02-10 | Tuesday | 7 |
| 28 | 2026-02-17 | Tuesday | 7 |
| 29 | 2026-02-24 | Tuesday | 7 |
| 30 | 2026-03-02 | Monday | 6 |
| 31 | 2026-03-10 | Tuesday | 8 |
| 32 | 2026-03-17 | Tuesday | 7 |
| 33 | 2026-03-24 | Tuesday | 7 |
| 34 | 2026-03-30 | Monday | 6 |
| 35 | 2026-04-07 | Tuesday | 8 |
| 36 | 2026-04-13 | Monday | 6 |
| 37 | 2026-04-21 | Tuesday | 8 |
| 38 | 2026-04-28 | Tuesday | 7 |
| 39 | 2026-05-05 | Tuesday | 7 |
| 40 | 2026-05-12 | Tuesday | 7 |
| 41 | 2026-05-19 | Tuesday | 7 |
| 42 | 2026-05-26 | Tuesday | 7 |
| 43 | 2026-06-02 | Tuesday | 7 |
| 44 | 2026-06-09 | Tuesday | 7 |
| 45 | 2026-06-16 | Tuesday | 7 |
| 46 | 2026-06-23 | Tuesday | 7 |
| 47 | 2026-06-30 | Tuesday | 7 |
| 48 | 2026-07-07 | Tuesday | 7 |
| 49 | 2026-07-14 | Tuesday | 7 |
| 50 | 2026-07-21 | Tuesday | 7 |
| 51 | 2026-07-28 | Tuesday | 7 |
| 52 | 2026-08-04 | Tuesday | 7 |
| 53 | 2026-08-11 | Tuesday | 7 |
| 54 | 2026-08-18 | Tuesday | 7 |

## Observation -> applicable expiry (coverage)

- observation dates with an applicable contract: **246/246**
- dates without (no future expiry listed): **0**
- days_to_expiry min: **1**
- days_to_expiry max (holiday/long-week gap): **8**

## No-lookahead

Only the expiry list published/listed ON day `d` (from the day-`d` bhavcopy) is used. Contract expiry dates are exchange-listed weeks in advance and were knowable at the decision timestamp; no future outcome is inspected. The mapping is fixed and deterministic (artifact hash above).
