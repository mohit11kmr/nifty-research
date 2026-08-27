"""Phase I.4 - Historical market-lot service (F2 correction).

Authoritative, point-in-time NIFTY option market lot from the frozen
provenance-backed dataset. The NSE FO bhavcopy carries `NewBrdLotQty`
(exposed as `lot_size` in `data/historical/normalized/options_eod_expanded.csv`)
for every (date, expiry, strike, option_type) row. This module surfaces that
exact value and never falls back to a current-lot constant (no "75" anywhere).

Key semantics (verified against the frozen data):

* Market lot is defined per CONTRACT (expiry x strike x option_type), not per
  date. Different strikes of the same expiry can carry different lots, and NSE
  lot revisions apply to outstanding contracts (so a contract's lot can change
  mid-life on a revision date).
* The economically correct quantity for a backtested trade is the lot of the
  EXACT entry contract row on the ENTRY date: quantity is fixed at entry, and
  P&L = (exit_mark - entry_mark) x quantity.
* `get_lot_size(trade_date)` resolves the strategy default contract on that
  date (near-expiry ATM call) - deterministic and identical to what the
  research runner trades for a single-leg CALL/ATM proposal such as PK-RQ-03.

Observed near-expiry-ATM-CE lot boundaries (from frozen rows, 646 sessions):

  2024-01-01 -> 2024-04-25  lot 50
  2024-04-26 -> 2024-12-25  lot 25
  2024-12-26 -> 2025-12-29  lot 75
  2025-12-30 -> 2026-08-13  lot 65

Only reads frozen data. Writes nothing.
"""
import os

import pandas as pd

REPO = os.path.dirname(os.path.abspath(__file__))
OPTIONS_CSV = os.path.join(REPO, "data", "historical", "normalized", "options_eod_expanded.csv")

_LOT_COLS = ["date", "expiry", "strike", "option_type", "lot_size", "underlying_price"]
_lot_df = None


def _load():
    global _lot_df
    if _lot_df is None:
        _lot_df = pd.read_csv(OPTIONS_CSV, usecols=_LOT_COLS,
                              dtype={"date": str, "expiry": str})
    return _lot_df


def contract_lot(trade_date, expiry, strike, side):
    """Lot of the exact (date, expiry, strike, option_type) contract row.

    None when the exact row is absent (CONTRACT_UNAVAILABLE - the caller must
    not substitute a current-lot constant).
    """
    df = _load()
    rows = df[(df["date"] == trade_date) & (df["expiry"] == expiry)
              & (df["strike"] == strike) & (df["option_type"] == side)]
    if not len(rows):
        return None
    lot = rows["lot_size"].iloc[0]
    return int(lot) if lot == lot else None


def get_lot_size(trade_date, expiry=None, strike=None, side=None):
    """Market lot for a date. With no contract arguments resolves the strategy
    default contract (near-expiry ATM call), matching the research runner.

    Returns None when the contract is not in the frozen data.
    """
    if expiry is not None and strike is not None and side is not None:
        return contract_lot(trade_date, expiry, strike, side)
    df = _load()
    rows = df[df["date"] == trade_date]
    if not len(rows):
        return None
    near = rows.loc[rows["expiry"] > trade_date, "expiry"].min()
    if near is None:
        return None
    up = rows.loc[rows["expiry"] == near, "underlying_price"].median()
    atm = round(up / 50) * 50
    return contract_lot(trade_date, near, atm, "CE")
