"""Fix-verification tests for the security/risk/honesty audit findings.

Each test maps to a finding fixed in this pass:
    R1  - precision_signals: honest confluence (score == passed layers, no fabrication)
    R3  - capital_guard: sub-lot risk blocks, invalid SL blocks, 1.5xATR structure SL
    R5  - config/angel_one_client: fail-closed without credentials, no live API call
    R7  - data_retention: purges only rows older than the keep-days window
    R11 - history_logger: WAL journal mode on every connection
    R13 - MCP broker gate: broker_status disabled by default; recent_ticks fails
          gracefully without data/research.db
Run from the repo root:  .venv/bin/python -m unittest tests.test_fix_verification -v
"""
import os
import re
import sys
import shutil
import sqlite3
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestR1PrecisionHonestConfluence(unittest.TestCase):
    """Confluence score must equal the count of PASSED layers - never inflated."""

    def setUp(self):
        import tempfile
        import ground_truth
        self._gt_dir = tempfile.mkdtemp()
        orig_db = ground_truth.DB_FILE
        ground_truth.DB_FILE = os.path.join(self._gt_dir, "ground_truth.db")
        try:
            import precision_signals
            self.sig = precision_signals.generate_precision_signal()
        finally:
            ground_truth.DB_FILE = orig_db

    def test_grade_key_present(self):
        self.assertIn("signal_grade", self.sig)

    def test_grade_is_no_signal_or_actionable(self):
        self.assertTrue(
            self.sig["signal_grade"].startswith("A+")
            or self.sig["signal_grade"].startswith("A ")
            or self.sig["signal_grade"].startswith("NO_SIGNAL")
        )

    def test_score_equals_passed_layer_count(self):
        checks = self.sig.get("confluence_checks", {})
        passed = sum(1 for c in checks.values() if c.get("status") == "PASSED")
        m = re.match(r"^(\d+)/(\d+)\s", str(self.sig["confluence_score"]))
        self.assertIsNotNone(m, "confluence_score must look like N/M (NN%)")
        self.assertEqual(int(m.group(1)), passed,
                         "confluence score must equal PASSED layer count (no inflation)")

    def test_six_layers_all_present(self):
        expected = {"regime_layer", "capital_guard_layer", "technical_layer",
                    "options_layer", "institutional_layer", "super_ai_ml_layer"}
        self.assertTrue(expected.issubset(self.sig["confluence_checks"].keys()))

    def test_honest_statuses_only(self):
        allowed = {"PASSED", "BLOCKED", "MIXED", "NEUTRAL", "NOT_COMPUTED",
                   "NO_SNAPSHOT", "NO_DATA", "ERROR"}
        for name, c in self.sig["confluence_checks"].items():
            self.assertIn(c.get("status"), allowed, f"{name} has fabricated status")

    def test_aplus_requires_regime_passed(self):
        if self.sig["signal_grade"].startswith("A+"):
            self.assertEqual(self.sig["confluence_checks"]["regime_layer"].get("status"), "PASSED")

    def test_nifty_strike_grid_is_50(self):
        levels = self.sig.get("precise_trade_levels", {})
        for key in ("recommended_call_strike", "recommended_put_strike"):
            val = levels.get(key)
            if val is not None:
                self.assertEqual(int(val) % 50, 0, f"{key} not on the 50-point grid")


class TestR3CapitalGuard(unittest.TestCase):
    """Sub-lot risk and invalid stops must BLOCK, never fabricate size."""

    def test_sub_lot_risk_blocks(self):
        import capital_guard
        cg = capital_guard.CapitalGuard(capital=100)  # 1% risk cap = 1 rupee
        r = cg.compute_position_size(entry_price=100, stop_loss_price=99, lot_size=75)
        self.assertEqual(r["allowed_lots"], 0)
        self.assertEqual(r["status"], "TRADE_BLOCKED")
        self.assertEqual(r["actual_risk_amount"], 0.0)

    def test_invalid_stop_blocks(self):
        import capital_guard
        cg = capital_guard.CapitalGuard()
        r = cg.compute_position_size(entry_price=100, stop_loss_price=150, lot_size=75)
        self.assertEqual(r["status"], "TRADE_BLOCKED")
        self.assertIn("invalid", r.get("reason", ""))

    def test_valid_size_is_compliant(self):
        import capital_guard
        cg = capital_guard.CapitalGuard(capital=100000)
        r = cg.compute_position_size(entry_price=100, stop_loss_price=98, lot_size=75)
        self.assertLessEqual(r["actual_risk_amount"], 1000.0)
        self.assertTrue(r["is_risk_compliant"])

    def test_audit_uses_real_premium_not_defaults(self):
        import capital_guard
        cg = capital_guard.CapitalGuard(capital=100000)
        audit = cg.full_capital_safety_audit(entry_price=100, stop_loss_price=98)
        sizing = audit["position_sizing"]
        self.assertEqual(sizing["risk_per_lot"], 150.0)
        self.assertIn("allowed_lots", sizing)
        self.assertIn("safety_status", audit)


class TestR5BrokerFailClosed(unittest.TestCase):
    """Without credentials the broker client must refuse, never call the API."""

    def _blank_client(self):
        import angel_one_client
        angel_one_client.CLIENT_CODE = ""
        angel_one_client.PASSWORD = ""
        angel_one_client.TOTP_SECRET = ""
        return angel_one_client.AngelOneManager()

    def test_login_fails_without_credentials(self):
        client = self._blank_client()
        ok = client.login()
        self.assertFalse(ok)
        self.assertIsNone(client.auth_token)
        self.assertIsNone(client.feed_token)

    def test_getters_return_none_without_session(self):
        client = self._blank_client()
        self.assertIsNone(client.get_profile())
        self.assertIsNone(client.get_holdings())

    def test_config_get_default(self):
        import config
        self.assertEqual(config.get("NO_SUCH_KEY_XYZ", "fallback"), "fallback")


class TestR7DataRetention(unittest.TestCase):
    """purge() must remove only rows older than the keep-days window."""

    def _make_db(self, path, t_recv_old, t_recv_new, s_recv_old, s_recv_new):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE ticks (recv_ts TEXT, symbol TEXT, strike REAL)")
        con.execute("CREATE TABLE spot (recv_ts TEXT, spot REAL)")
        for ts in (t_recv_old, t_recv_new):
            con.execute("INSERT INTO ticks VALUES (?, 'NIFTY', 25000)", (ts,))
        for ts in (s_recv_old, s_recv_new):
            con.execute("INSERT INTO spot VALUES (?, 25000)", (ts,))
        con.commit()
        con.close()

    def test_purge_removes_only_old_rows(self):
        import data_retention
        with tempfile.TemporaryDirectory() as td:
            db = os.path.join(td, "research.db")
            self._make_db(db, "2020-01-01T00:00:00", "2030-01-01T00:00:00",
                          "2020-01-01T00:00:00", "2030-01-01T00:00:00")
            orig = data_retention.DB_PATH
            data_retention.DB_PATH = db
            try:
                t, s = data_retention.purge(keep_days=30)
                self.assertEqual((t, s), (1, 1))
                con = sqlite3.connect(db)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM ticks").fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM spot").fetchone()[0], 1)
                con.close()
            finally:
                data_retention.DB_PATH = orig


class TestR11HistoryLoggerWal(unittest.TestCase):
    """Every SQLite connection must run in WAL mode (no locking churn)."""

    def test_connection_is_wal(self):
        import history_logger
        with tempfile.TemporaryDirectory() as td:
            orig_file, orig_conn = history_logger.DB_FILE, history_logger._conn
            history_logger.DB_FILE = os.path.join(td, "audit.db")
            history_logger._conn = None
            try:
                conn = history_logger._init_sqlite_db()
                mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(mode.lower(), "wal")
            finally:
                history_logger.DB_FILE = orig_file
                history_logger._conn = orig_conn


class TestR13McpBrokerGate(unittest.TestCase):
    """Broker exposure is off by default; tick queries fail gracefully."""

    def test_broker_status_disabled_by_default(self):
        os.environ.pop("BROKER_MCP_ENABLED", None)
        import mcp_nifty
        r = mcp_nifty.broker_status()
        self.assertFalse(r.get("ok", True))
        self.assertIn("disabled", r.get("error", ""))

    def test_recent_ticks_graceful_without_db(self):
        import mcp_nifty
        with tempfile.TemporaryDirectory() as td:
            orig = os.getcwd()
            os.chdir(td)
            try:
                r = mcp_nifty.recent_ticks()
                self.assertFalse(r.get("ok", True))
                self.assertIn("missing", r.get("error", ""))
            finally:
                os.chdir(orig)


class TestBrokerSessionLifecycle(unittest.TestCase):
    """S-M3: token expiry detection, re-auth gate, and logout revocation."""

    def _manager(self):
        import angel_one_client
        angel_one_client.CLIENT_CODE = ""
        angel_one_client.PASSWORD = ""
        angel_one_client.TOTP_SECRET = ""
        return angel_one_client.AngelOneManager()

    def test_session_expired_when_token_old(self):
        import time
        import angel_one_client
        m = self._manager()
        m.smart_api = object()  # simulate a logged-in session
        m.token_issued_at = time.time() - angel_one_client.TOKEN_TTL_SECONDS - 60
        self.assertTrue(m._session_expired())

    def test_session_fresh_not_expired(self):
        import time
        m = self._manager()
        m.smart_api = object()
        m.token_issued_at = time.time()
        self.assertFalse(m._session_expired())

    def test_no_session_always_expired(self):
        m = self._manager()
        self.assertTrue(m._session_expired())

    def test_ensure_session_fails_without_credentials(self):
        m = self._manager()
        self.assertFalse(m._ensure_session())

    def test_logout_revokes_everything(self):
        m = self._manager()
        m.smart_api = object()
        m.auth_token = "jwt"
        m.refresh_token = "refresh"
        m.feed_token = "feed"
        m.token_issued_at = 123.0
        m.logout()
        self.assertIsNone(m.smart_api)
        self.assertIsNone(m.auth_token)
        self.assertIsNone(m.refresh_token)
        self.assertIsNone(m.feed_token)
        self.assertIsNone(m.token_issued_at)

    def test_login_failure_resets_stale_tokens(self):
        m = self._manager()
        m.auth_token = "stale"
        ok = m.login()
        self.assertFalse(ok)
        self.assertIsNone(m.auth_token)
        self.assertIsNone(m.smart_api)


class TestMaxPainParity(unittest.TestCase):
    """PF-M3: vectorized max pain must match the reference O(n^2) loop."""

    def _chain(self):
        import numpy as np
        import pandas as pd
        strikes = np.arange(24400, 25300, 50)
        n = len(strikes)
        rng = np.random.default_rng(7)
        return pd.DataFrame({
            "strike": strikes,
            "ce_oi": rng.integers(1000, 800000, n),
            "pe_oi": rng.integers(1000, 800000, n),
            "ce_oi_chg": rng.integers(-50000, 50000, n),
            "pe_oi_chg": rng.integers(-50000, 50000, n),
        })

    def test_vectorized_matches_reference(self):
        import numpy as np
        import oi_intel
        chain = self._chain()
        spot = 24850.0
        band = chain[chain["strike"].between(spot * 0.92, spot * 1.08)]
        strikes = band["strike"].to_numpy()
        ce_oi = band["ce_oi"].fillna(0).to_numpy()
        pe_oi = band["pe_oi"].fillna(0).to_numpy()

        best, pain_best = None, None
        for i, k in enumerate(strikes):
            payout = 0.0
            for j, s in enumerate(strikes):
                payout += max(0.0, k - s) * ce_oi[j]
                payout += max(0.0, s - k) * pe_oi[j]
            if pain_best is None or payout < pain_best:
                pain_best, best = payout, k

        res = oi_intel.pcr_and_pain(chain, spot=spot)
        self.assertEqual(res["max_pain"], int(best))

    def test_empty_chain_returns_none(self):
        import pandas as pd
        import oi_intel
        empty = pd.DataFrame(columns=["strike", "ce_oi", "pe_oi", "ce_oi_chg", "pe_oi_chg"])
        self.assertIsNone(oi_intel.pcr_and_pain(empty).get("max_pain"))


class TestChainMetricsParity(unittest.TestCase):
    """R8: data_fetcher.compute_chain_metrics agrees with oi_intel (single owner)."""

    def test_pcr_and_max_pain_match_oi_intel(self):
        import numpy as np
        import pandas as pd
        import data_fetcher
        import oi_intel
        strikes = np.arange(24400, 25300, 50)
        n = len(strikes)
        rng = np.random.default_rng(11)
        chain = pd.DataFrame({
            "strike": strikes,
            "ce_oi": rng.integers(1000, 800000, n),
            "pe_oi": rng.integers(1000, 800000, n),
            "ce_oi_chg": rng.integers(-50000, 50000, n),
            "pe_oi_chg": rng.integers(-50000, 50000, n),
        })
        metrics = data_fetcher.compute_chain_metrics(chain)
        atm = metrics["atm"]
        pain = oi_intel.pcr_and_pain(chain, spot=atm)
        self.assertEqual(metrics["max_pain"], pain["max_pain"])
        self.assertAlmostEqual(metrics["pcr"] or 0.0, round(pain["pcr"] or 0.0, 3))
        self.assertIn("support_oi", metrics)
        self.assertIn("resistance_oi", metrics)
        self.assertIsNotNone(metrics["atm"])


class TestBackupScript(unittest.TestCase):
    """R4: backup_data.py snapshots + verifies + restores; retention prunes."""

    def _make_sources(self, td):
        db = os.path.join(td, "research.db")
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE ticks (recv_ts TEXT)")
        con.execute("CREATE TABLE spot (recv_ts TEXT)")
        con.execute("INSERT INTO ticks VALUES ('2026-08-13T10:00:00')")
        con.execute("INSERT INTO ticks VALUES ('2026-08-13T10:00:01')")
        con.execute("INSERT INTO spot VALUES ('2026-08-13T10:00:00')")
        con.commit()
        con.close()
        paper = os.path.join(td, "paper_account.json")
        with open(paper, "w") as f:
            f.write('{"capital": 100000}')
        return db, paper

    def test_backup_verify_and_restore(self):
        import backup_data
        with tempfile.TemporaryDirectory() as td:
            src_root = os.path.join(td, "src")
            bkp_root = os.path.join(td, "bkp")
            os.makedirs(os.path.join(src_root, "data"))
            db, paper = self._make_sources(os.path.join(src_root, "data"))

            orig = backup_data.HERE
            backup_data.HERE = src_root
            try:
                res = backup_data.backup(backup_root=bkp_root, keep=2)
            finally:
                backup_data.HERE = orig
            self.assertEqual(res["errors"], [])
            self.assertEqual(sorted(res["files"]),
                             ["paper_account.json", "research.db"])
            self.assertTrue(os.path.isdir(res["dest"]))

            bkp_db = os.path.join(res["dest"], "research.db")
            self.assertTrue(backup_data.verify_backup(bkp_db)["ok"])

            # Restore = copy the verified backup back over a live path.
            restored = os.path.join(td, "restored.db")
            shutil.copy2(bkp_db, restored)
            rcon = sqlite3.connect(restored)
            self.assertEqual(rcon.execute("SELECT COUNT(*) FROM ticks").fetchone()[0], 2)
            self.assertEqual(rcon.execute("SELECT COUNT(*) FROM spot").fetchone()[0], 1)
            rcon.close()

    def test_retention_prunes_old_backups(self):
        import backup_data
        with tempfile.TemporaryDirectory() as td:
            bkp_root = os.path.join(td, "bkp")
            old = os.path.join(bkp_root, "20260101-0000")
            new = os.path.join(bkp_root, "20260813-1200")
            os.makedirs(old)
            os.makedirs(new)
            backup_data._prune_old(bkp_root, keep=1)
            self.assertFalse(os.path.exists(old))
            self.assertTrue(os.path.exists(new))


if __name__ == "__main__":
    unittest.main(verbosity=2)
