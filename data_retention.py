"""Data retention job - keeps data/research.db bounded (PERFORMANCE-AUDIT H2).

Deletes tick/spot rows older than --keep-days from research.db, then optionally
VACUUMs. Safe to run from cron daily. Does not touch the historical audit DB.

Usage:
    python data_retention.py [--keep-days 30] [--vacuum]
"""
import argparse
import datetime as dt
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "research.db")


def purge(keep_days=30, vacuum=False):
    if not os.path.exists(DB_PATH):
        print("no research.db - nothing to purge")
        return 0, 0
    con = sqlite3.connect(DB_PATH, timeout=10)
    try:
        cutoff = (dt.datetime.now() - dt.timedelta(days=keep_days)).strftime("%Y-%m-%dT00:00:00")
        t = con.execute("DELETE FROM ticks WHERE recv_ts < ?", (cutoff,)).rowcount
        s = con.execute("DELETE FROM spot WHERE recv_ts < ?", (cutoff,)).rowcount
        con.commit()
        if vacuum and (t or s):
            con.execute("VACUUM")
        return t, s
    finally:
        con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-days", type=int, default=30)
    ap.add_argument("--vacuum", action="store_true")
    args = ap.parse_args()
    ticks, spots = purge(args.keep_days, args.vacuum)
    print(f"purged {ticks:,} tick-rows, {spots:,} spot-rows (keep {args.keep_days} days)")
