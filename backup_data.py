"""Data backup job — safe, verified snapshots of critical state (REMEDIATION R4).

Backs up the SQLite research/audit DBs via the sqlite3 `.backup` API (a
consistent snapshot even while tick_recorder is writing) plus the JSON/CSV
state files the audit trail depends on. Every backup is verified: DB backups
get `PRAGMA integrity_check` + a row-count comparison against the live DB, and
the script exits non-zero on any failure.

Usage:
    python backup_data.py [--keep 14] [--dry-run]

Backups land in `backups/YYYYMMDD-HHMM/`. Older backup dirs beyond `--keep`
are pruned after a successful run.
"""
import os
import sys
import glob
import shutil
import sqlite3
import argparse
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(HERE, "backups")

DB_SOURCES = [
    os.path.join("data", "research.db"),
    os.path.join("data", "historical_audit.db"),
]
FILE_SOURCES = [
    os.path.join("data", "paper_account.json"),
    os.path.join("data", "signal_history.csv"),
    os.path.join("data", "tick_history.csv"),
    os.path.join("data", "paper_trade_journal.csv"),
    os.path.join("data", "adaptive_weights.json"),
    os.path.join("data", "enhancement_log.json"),
]


def _row_counts(db_path):
    con = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        con.close()


def verify_backup(db_path):
    """Check a backed-up SQLite DB is readable and internally consistent."""
    con = sqlite3.connect(db_path)
    try:
        status = con.execute("PRAGMA integrity_check").fetchone()[0]
        if status != "ok":
            return {"ok": False, "error": f"integrity_check: {status}"}
        return {"ok": True, "tables": _row_counts(db_path)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        con.close()


def _backup_db(src, dest):
    """Consistent SQLite snapshot (safe against concurrent writers)."""
    src_con = sqlite3.connect(src)
    dest_con = sqlite3.connect(dest)
    try:
        src_con.backup(dest_con)
        dest_con.commit()
    finally:
        dest_con.close()
        src_con.close()


def backup(backup_root=None, keep=14, dry_run=False):
    """Back up all existing sources into a dated dir; return a results dict."""
    backup_root = backup_root or BACKUP_ROOT
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    dest_dir = os.path.join(backup_root, stamp)
    results = {"dest": dest_dir, "files": [], "errors": []}

    if not dry_run:
        os.makedirs(dest_dir, exist_ok=True)

    for rel in DB_SOURCES + FILE_SOURCES:
        src = os.path.join(HERE, rel)
        if not os.path.exists(src):
            continue
        name = os.path.basename(rel)
        dest = os.path.join(dest_dir, name)
        try:
            if dry_run:
                results["files"].append(name)
                continue
            if rel in DB_SOURCES:
                _backup_db(src, dest)
                ver = verify_backup(dest)
                if not ver["ok"]:
                    raise RuntimeError(f"backup verification failed: {ver.get('error')}")
                live = _row_counts(src)
                if live != ver["tables"]:
                    raise RuntimeError(
                        f"row-count mismatch: live {live} vs backup {ver['tables']}")
            else:
                shutil.copy2(src, dest)
            results["files"].append(name)
        except Exception as e:
            results["errors"].append(f"{name}: {type(e).__name__}: {e}")

    if not dry_run and not results["errors"]:
        _prune_old(backup_root, keep)
    return results


def _prune_old(backup_root, keep):
    dirs = sorted(glob.glob(os.path.join(backup_root, "[0-9]" * 8 + "-*")))
    for old in dirs[:-keep]:
        shutil.rmtree(old, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Backup + verify project data")
    ap.add_argument("--keep", type=int, default=14, help="backup dirs to keep")
    ap.add_argument("--dry-run", action="store_true", help="list sources, back up nothing")
    args = ap.parse_args()

    res = backup(keep=args.keep, dry_run=args.dry_run)
    for f in res["files"]:
        print(f"  backed up: {f}")
    for e in res["errors"]:
        print(f"  ERROR: {e}")
    print(f"  destination: {res['dest']} (dry-run={args.dry_run})")
    if res["errors"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
