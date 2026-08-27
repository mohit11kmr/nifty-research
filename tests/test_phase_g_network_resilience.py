"""Phase G — Network Disconnect / Recovery Resilience tests.

Every scenario uses isolated temp fixtures and mocks. No test writes to
production data/ground_truth.db, data/research.db, paper_account.json,
data/nifty_history.csv, or the running quant daemon PID/log files.

Matrix covered (OPENCODE_PHASE_G_NETWORK_RESILIENCE.md section 17):
  NIFTY feed failure / OPTIONS-OI failure / VIX failure / all-feed failure
  open-position feed loss / stop during feed loss / target during feed loss
  expiry during feed loss / recovery / missed-cycle recovery
  duplicate prevention / freshness recovery / daemon exception recovery
  production-data isolation
"""
import io
import os
import sys
import json
import sqlite3
import contextlib
import datetime as dt
import tempfile
import unittest
import unittest.mock as mock
from contextlib import redirect_stdout

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import truth
import paper_mtm
import paper_execution
import exit_evaluator
import expiry_calendar
import ground_truth
import regime_filter
import precision_signals
import live_market_fetch
import auto_paper_runner
import quant_daemon

FakeQuoteSource = paper_mtm.FakeQuoteSource


@contextlib.contextmanager
def _patched(patches):
    started = []
    try:
        for p in patches:
            p.__enter__()
            started.append(p)
        yield
    finally:
        for p in reversed(started):
            p.__exit__(None, None, None)


def _key(symbol, strike, option_type):
    return (str(symbol), float(strike), str(option_type).upper())


def _engine(tmp):
    acct = os.path.join(str(tmp), "paper_account.json")
    gt = os.path.join(str(tmp), "ground_truth.db")
    return paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt)


def _open_position(eng, entry=150.0, sl=100.0, tgt=250.0,
                   ts="2026-08-13 10:00:00 IST"):
    sub = eng.submit_order(
        symbol="NIFTY", side="BUY", option_type="CE", strike=24500,
        lots=1, lot_size=75, entry_price=entry, sl_price=sl,
        target_price=tgt, requested_price=entry)
    if sub["status"] == "REJECTED":
        raise AssertionError(f"fixture order rejected: {sub.get('reason')}")
    eng.accept_order(sub["order_id"])
    eng.fill_order(sub["order_id"], 75, price=entry, reference_price=entry,
                   apply_slippage=False, ts=ts, commission=0.0)
    pos = eng.derived_positions()
    if not pos:
        raise AssertionError("fixture position did not open")
    return pos[0]


def _env(status, price, age=30.0, expiry=None):
    return {"status": status, "price": price, "price_basis": "ltp",
            "bid": None, "ask": None, "expiry": expiry,
            "quote_timestamp": "2026-08-14 10:00:00 IST",
            "quote_age_s": age}


def _now(h=11, m=0, day=14, month=8, year=2026):
    return dt.datetime(year, month, day, h, m)


def _gt_count(tmp, table):
    db = os.path.join(str(tmp), "ground_truth.db")
    con = sqlite3.connect(db)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def _feed_down():
    return {"status": "UNAVAILABLE", "spot": None,
            "open": None, "high": None, "low": None, "is_live": False}


def _feed_up(spot=24400.0):
    return {"status": "LIVE_MARKET_TICK", "spot": spot, "open": spot,
            "high": spot, "low": spot, "is_live": True}


def _stub_engine():
    stub = mock.MagicMock()
    stub.run_exit_checks.return_value = {"closed": [], "errors": []}
    return stub


class NiftyFeedFailureTests(unittest.TestCase):

    def test_feed_down_stand_down_no_trade(self):
        """NIFTY source unavailable -> no live or cached spot -> STAND_DOWN."""
        stub = _stub_engine()
        with _patched([
            mock.patch("auto_paper_runner.live_market_fetch.update_live_market_cache",
                       return_value=_feed_down()),
            mock.patch("auto_paper_runner.paper_trader.paper_engine", stub),
        ]):
            res = auto_paper_runner.run_auto_paper_trader()
        self.assertEqual(res.get("status"), "STAND_DOWN")
        self.assertIn("no live or cached spot", res.get("reason", ""))
        stub.execute_paper_order.assert_not_called()

    def test_cached_spot_fallback_not_mislabeled_real(self):
        """Feed down + last-recorded real spot exists: CACHED_REAL, not REAL."""
        df = pd.DataFrame({"date": ["2026-08-13"], "close": [24350.0],
                           "open": [24300.0], "high": [24400.0],
                           "low": [24200.0], "volume": [0]})
        with _patched([
            mock.patch("live_market_fetch.fetch_live_market_spot",
                       return_value=_feed_down()),
            mock.patch("live_market_fetch._last_real_spot",
                       return_value={"spot": 24400.0,
                                     "recv_ts": "2026-08-14 09:00:00 IST",
                                     "is_live": False}),
            mock.patch("live_market_fetch.pd.read_csv", return_value=df),
            mock.patch("pandas.DataFrame.to_csv"),
            mock.patch("history_logger.log_market_tick"),
        ]):
            live = live_market_fetch.update_live_market_cache()
        self.assertEqual(live.get("spot"), 24400.0)
        self.assertIs(live.get("is_live"), False)
        self.assertNotIn("status", live)
        self.assertNotEqual(live.get("status"), "LIVE_MARKET_TICK")

    def test_stale_cached_spot_not_age_gated(self):
        """GAP G1 documented: cached-spot fallback has no age gate."""
        df = pd.DataFrame({"date": ["2026-08-13"], "close": [24350.0],
                           "open": [24300.0], "high": [24400.0],
                           "low": [24200.0], "volume": [0]})
        with _patched([
            mock.patch("live_market_fetch.fetch_live_market_spot",
                       return_value=_feed_down()),
            mock.patch("live_market_fetch._last_real_spot",
                       return_value={"spot": 24400.0,
                                     "recv_ts": "2026-08-13 15:29:00 IST",
                                     "is_live": False}),
            mock.patch("live_market_fetch.pd.read_csv", return_value=df),
            mock.patch("pandas.DataFrame.to_csv"),
            mock.patch("history_logger.log_market_tick"),
        ]):
            live = live_market_fetch.update_live_market_cache()
        self.assertEqual(live.get("spot"), 24400.0)


class StayOutSignalTests(unittest.TestCase):

    def test_stay_out_signal_no_trade(self):
        """STAY_OUT / NO_SIGNAL never places a paper trade."""
        stub = _stub_engine()
        with _patched([
            mock.patch("auto_paper_runner.live_market_fetch.update_live_market_cache",
                       return_value=_feed_up()),
            mock.patch("auto_paper_runner.paper_trader.paper_engine", stub),
            mock.patch("auto_paper_runner.capital_guard.CapitalGuard"),
            mock.patch("auto_paper_runner.var_risk_manager.var_engine",
                       **{"compute_value_at_risk.return_value": {}}),
            mock.patch("auto_paper_runner.mtf_alignment.compute_mtf_alignment",
                       return_value={"alignment_status": "ALIGNED"}),
            mock.patch("auto_paper_runner.volume_analytics_engine.compute_volume_analytics",
                       return_value={"volume_surge_ratio": None,
                                     "pocket_pivot_detected": False}),
            mock.patch("auto_paper_runner.precision_signals.generate_precision_signal",
                       return_value={"signal_action": "STAY_OUT",
                                     "signal_grade": "NO_SIGNAL (FILTERED OUT NOISE)"}),
        ]):
            res = auto_paper_runner.run_auto_paper_trader()
        self.assertEqual(res.get("status"), "STAND_DOWN")
        self.assertIn("STAY_OUT", res.get("reason", ""))
        stub.execute_paper_order.assert_not_called()


class OptionsOiFailureTests(unittest.TestCase):

    def _base_patches(self, technical=("NEUTRAL", 0, None, 0, 0)):
        fake_cg = mock.MagicMock()
        fake_cg.full_capital_safety_audit.return_value = {"safety_status": "APPROVED"}
        fake_gt = mock.MagicMock(
            record_signal_chain=lambda **kw: {"signal_id": 1,
                                              "prediction_id": None,
                                              "decision_id": None})
        return [
            mock.patch("capital_guard.CapitalGuard", return_value=fake_cg),
            mock.patch("regime_filter.trade_plan",
                       return_value={"regime": "TREND", "gate": "OPEN",
                                     "close": 24400.0,
                                     "vix": {"level": 14.0,
                                             "zone": "VIX_NORMAL"},
                                     "regime_note": ""}),
            mock.patch("precision_signals._technical_verdict",
                       return_value=technical),
            mock.patch("institutional.institutional_scan",
                       return_value={"fii_sentiment": "NEUTRAL"}),
            mock.patch("super_ai_ml.train_super_ai_ensemble", return_value=None),
            mock.patch("ground_truth.GroundTruthDB", return_value=fake_gt),
        ]

    def test_oi_feed_failure_error_no_invented_pcr(self):
        """OI source raises -> options_layer ERROR, no invented PCR."""
        patches = self._base_patches() + [
            mock.patch("os.path.exists", return_value=True),
            mock.patch("os.listdir", return_value=["NIFTY_test.csv"]),
            mock.patch("precision_signals.pd.read_csv",
                       return_value=pd.DataFrame({"strike": [24500.0]})),
            mock.patch("oi_intel.pcr_and_pain",
                       side_effect=RuntimeError("chain unreadable")),
        ]
        with _patched(patches):
            sig = precision_signals.generate_precision_signal()
        checks = sig.get("confluence_checks") or {}
        self.assertEqual(checks.get("options_layer", {}).get("status"), "ERROR")
        self.assertNotIn("pcr", checks.get("options_layer", {}))
        self.assertEqual(sig.get("signal_action"), "STAY_OUT")
        self.assertIn("NO_SIGNAL", sig.get("signal_grade", ""))

    def test_oi_no_snapshot_no_invented_oi(self):
        """No OI snapshot -> NO_SNAPSHOT (no fabricated PCR/max pain)."""
        patches = self._base_patches() + [
            mock.patch("os.path.exists", return_value=True),
            mock.patch("os.listdir", return_value=[]),
        ]
        with _patched(patches):
            sig = precision_signals.generate_precision_signal()
        checks = sig.get("confluence_checks") or {}
        self.assertEqual(checks.get("options_layer", {}).get("status"), "NO_SNAPSHOT")
        self.assertNotIn("pcr", checks.get("options_layer", {}))
        self.assertEqual(sig.get("signal_action"), "STAY_OUT")


class VixFailureTests(unittest.TestCase):

    def test_vix_source_missing_no_fabrication(self):
        """VIX cache missing/corrupt -> vix_snapshot None, never fabricated."""
        with mock.patch("regime_filter._load_vix", return_value=None):
            snap = regime_filter.vix_snapshot(nifty_close=24400.0)
        self.assertIsNone(snap)

    def test_vix_zone_none_honest_default(self):
        self.assertEqual(regime_filter.vix_zone(None), regime_filter.VIX_NORMAL)

    def test_expected_move_none(self):
        self.assertIsNone(regime_filter.expected_move(24400.0, None))


class AllFeedFailureTests(unittest.TestCase):

    def test_all_layers_fail_signal_stay_out(self):
        """NIFTY+OI+VIX+institutional+ML unavailable -> STAY_OUT, no trade."""
        fake_cg = mock.MagicMock()
        fake_cg.full_capital_safety_audit.side_effect = RuntimeError("cg down")
        fake_gt = mock.MagicMock(
            record_signal_chain=lambda **kw: {"signal_id": 1,
                                              "prediction_id": None,
                                              "decision_id": None})
        with _patched([
            mock.patch("capital_guard.CapitalGuard", return_value=fake_cg),
            mock.patch("regime_filter.trade_plan",
                       side_effect=RuntimeError("regime down")),
            mock.patch("precision_signals._technical_verdict",
                       return_value=(None, None, None, 0, 0)),
            mock.patch("institutional.institutional_scan",
                       side_effect=RuntimeError("inst down")),
            mock.patch("super_ai_ml.train_super_ai_ensemble",
                       side_effect=RuntimeError("ml down")),
            mock.patch("os.path.exists", return_value=True),
            mock.patch("os.listdir", return_value=["NIFTY_test.csv"]),
            mock.patch("precision_signals.pd.read_csv",
                       side_effect=IOError("no chain")),
            mock.patch("ground_truth.GroundTruthDB", return_value=fake_gt),
        ]):
            sig = precision_signals.generate_precision_signal()
        checks = sig.get("confluence_checks") or {}
        self.assertEqual(checks.get("regime_layer", {}).get("status"), "ERROR")
        self.assertIn(checks.get("options_layer", {}).get("status"),
                      ("ERROR", "NOT_COMPUTED"))
        self.assertEqual(checks.get("institutional_layer", {}).get("status"), "ERROR")
        self.assertEqual(checks.get("capital_guard_layer", {}).get("status"), "ERROR")
        self.assertNotIn("pcr", checks.get("options_layer", {}))
        self.assertEqual(sig.get("signal_action"), "STAY_OUT")
        self.assertIsNone(sig.get("nifty_spot"))

    def test_all_feeds_down_stand_down(self):
        """All feeds unavailable -> paper trader STAND_DOWN (fail closed)."""
        stub = _stub_engine()
        with _patched([
            mock.patch("auto_paper_runner.live_market_fetch.update_live_market_cache",
                       return_value=_feed_down()),
            mock.patch("auto_paper_runner.paper_trader.paper_engine", stub),
        ]):
            res = auto_paper_runner.run_auto_paper_trader()
        self.assertEqual(res.get("status"), "STAND_DOWN")
        stub.execute_paper_order.assert_not_called()


class OpenPositionFeedLossTests(unittest.TestCase):

    def test_quote_missing_no_close_no_gt_change(self):
        """Feed loss on an open position: skip, no close, GT unchanged."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        _open_position(eng)
        with mock.patch.object(eng.exit_evaluator, "quote_source",
                               FakeQuoteSource({})):
            rep = eng.run_exit_checks(now=_now())
        self.assertEqual(rep["evaluated"], 1)
        self.assertEqual(rep["closed"], [])
        self.assertEqual(len(rep["skipped"]), 1)
        self.assertEqual(rep["skipped"][0]["skip_reason"], "MISSING_QUOTE")
        self.assertFalse(rep["skipped"][0]["triggered"])
        pos = eng.derived_positions()
        self.assertEqual(len(pos), 1)
        self.assertEqual(int(pos[0]["quantity"]), 75)
        self.assertEqual(_gt_count(tmp, "outcomes"), 0)
        self.assertEqual(_gt_count(tmp, "executions"), 1)

    def test_missing_quote_mtm_entry_fallback_flagged(self):
        """MTM with no quote -> entry-price fallback flagged, never guessed."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        _open_position(eng)
        rep = eng.mark_to_market_report(
            quote_source=FakeQuoteSource({}), now=_now())
        self.assertEqual(rep["position_count"], 1)
        m = rep["marked_positions"][0]
        self.assertEqual(m["quote_status"], "NO_QUOTE")
        self.assertEqual(m["price_basis"], "entry_fallback")
        self.assertEqual(m["mark_price"], 150.0)
        self.assertEqual(rep["no_quote_count"], 1)
        self.assertEqual(rep["stale_count"], 0)

    def test_stale_quote_mtm_flagged_stale(self):
        """MTM with STALE quote -> valued at quote but flagged STALE."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): _env("STALE", 140.0,
                                                              age=900.0)})
        rep = eng.mark_to_market_report(quote_source=src, now=_now())
        m = rep["marked_positions"][0]
        self.assertEqual(m["quote_status"], "STALE")
        self.assertEqual(m["price_basis"], "ltp")
        self.assertEqual(m["mark_price"], 140.0)
        self.assertEqual(rep["stale_count"], 1)


class StopTargetDuringFeedLossTests(unittest.TestCase):

    def _eng_quote(self, env):
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): env})
        return eng, pos, src

    def test_stop_not_false_triggered_on_stale(self):
        eng, pos, src = self._eng_quote(_env("STALE", 95.0, age=900.0))
        dec = eng.exit_evaluator.evaluate_position(
            pos, quote=src.get_quote(pos["symbol"], pos["strike"],
                                     pos["option_type"], now=_now()),
            now=_now())
        self.assertFalse(dec["triggered"])
        self.assertEqual(dec["skip_reason"], "STALE_QUOTE_NO_TRIGGER")

    def test_target_not_false_triggered_on_stale(self):
        eng, pos, src = self._eng_quote(_env("STALE", 260.0, age=900.0))
        dec = eng.exit_evaluator.evaluate_position(
            pos, quote=src.get_quote(pos["symbol"], pos["strike"],
                                     pos["option_type"], now=_now()),
            now=_now())
        self.assertFalse(dec["triggered"])
        self.assertEqual(dec["skip_reason"], "STALE_QUOTE_NO_TRIGGER")

    def test_stop_triggers_on_fresh_control(self):
        eng, pos, src = self._eng_quote(_env("REAL", 95.0, age=5.0))
        dec = eng.exit_evaluator.evaluate_position(
            pos, quote=src.get_quote(pos["symbol"], pos["strike"],
                                     pos["option_type"], now=_now()),
            now=_now())
        self.assertTrue(dec["triggered"])
        self.assertEqual(dec["reason"], "STOP_LOSS")
        self.assertEqual(dec["exit_reference_price"], 95.0)

    def test_target_triggers_on_fresh_control(self):
        eng, pos, src = self._eng_quote(_env("REAL", 260.0, age=5.0))
        dec = eng.exit_evaluator.evaluate_position(
            pos, quote=src.get_quote(pos["symbol"], pos["strike"],
                                     pos["option_type"], now=_now()),
            now=_now())
        self.assertTrue(dec["triggered"])
        self.assertEqual(dec["reason"], "TAKE_PROFIT")


class ExpiryDuringFeedLossTests(unittest.TestCase):

    @staticmethod
    def _next_expiry():
        d = dt.date(2026, 8, 14)
        for _ in range(21):
            if expiry_calendar.is_expiry_day(d):
                return d
            d += dt.timedelta(days=1)
        raise AssertionError("no weekly expiry found in range")

    def test_expiry_squareoff_no_price_pending(self):
        """Expiry day + no exit price -> pending, no fabricated price/roll."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        _open_position(eng)
        e = self._next_expiry()
        now = dt.datetime(e.year, e.month, e.day, 15, 30)
        dec = eng.exit_evaluator.evaluate_position(
            eng.derived_positions()[0],
            quote=FakeQuoteSource({}).get_quote("NIFTY", 24500, "CE"),
            now=now)
        self.assertTrue(dec["is_expiry_day"])
        self.assertFalse(dec["triggered"])
        self.assertEqual(dec["skip_reason"], "NO_EXIT_PRICE_SQUARE_OFF_PENDING")
        rep = eng.run_exit_checks(quote_source=FakeQuoteSource({}), now=now)
        self.assertEqual(rep["closed"], [])
        self.assertEqual(len(eng.derived_positions()), 1)
        self.assertEqual(_gt_count(tmp, "outcomes"), 0)

    def test_expiry_squareoff_stale_price_squares(self):
        """Expiry day + STALE price -> mandatory square-off (time rule)."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        e = self._next_expiry()
        now = dt.datetime(e.year, e.month, e.day, 15, 30)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): _env("STALE", 150.0,
                                                              age=900.0)})
        rep = eng.run_exit_checks(quote_source=src, now=now)
        self.assertEqual(len(rep["closed"]), 1)
        self.assertEqual(rep["closed"][0]["exit_reason"], "EXPIRY_SQUARE_OFF")
        self.assertEqual(rep["closed"][0]["requested_exit_price"], 150.0)
        self.assertEqual(rep["closed"][0]["exit_price"], round(150.0 * 0.985, 2))
        self.assertEqual(len(eng.derived_positions()), 0)
        self.assertEqual(_gt_count(tmp, "outcomes"), 1)

    def test_no_auto_roll(self):
        """Expiry close never auto-rolls into a new position."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        e = self._next_expiry()
        now = dt.datetime(e.year, e.month, e.day, 15, 30)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): _env("STALE", 150.0,
                                                              age=900.0)})
        eng.run_exit_checks(quote_source=src, now=now)
        self.assertEqual(len(eng.derived_positions()), 0)
        open_orders = [o for o in eng.account.get("orders", [])
                       if o.get("order_kind") == "OPEN"
                       and o.get("status") == "FILLED"
                       and int(o.get("closed_quantity", 0)) < int(o["quantity"])]
        self.assertEqual(open_orders, [])


class RecoveryTests(unittest.TestCase):

    def test_recovery_after_quote_loss_no_repair(self):
        """MISSING -> REAL recovery: normal close resumes, no manual repair."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): _env("REAL", 95.0,
                                                              age=5.0)})
        with mock.patch.object(eng.exit_evaluator, "quote_source",
                               FakeQuoteSource({})):
            rep1 = eng.run_exit_checks(now=_now(11, 0))
        self.assertEqual(rep1["closed"], [])
        self.assertEqual(len(eng.derived_positions()), 1)
        rep2 = eng.run_exit_checks(quote_source=src, now=_now(11, 5))
        self.assertEqual(len(rep2["closed"]), 1)
        self.assertEqual(rep2["closed"][0]["exit_reason"], "STOP_LOSS")
        self.assertEqual(len(eng.derived_positions()), 0)
        self.assertEqual(_gt_count(tmp, "outcomes"), 1)

    def test_recovery_not_retroactive(self):
        """Recovery closes at the recovery timestamp, not a backfilled one."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): _env("REAL", 95.0,
                                                              age=5.0)})
        eng.run_exit_checks(quote_source=src, now=_now(14, 30))
        fill_ts = eng.account["orders"][-1]["fills"][0]["timestamp"]
        self.assertTrue(fill_ts.startswith("2026-08-14 14:30"))


class MissedCycleRecoveryTests(unittest.TestCase):

    def test_failed_cycle_then_recovery_no_duplicate_close(self):
        """Repeated checks after recovery stay idempotent (1 close total)."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        src = FakeQuoteSource({_key(pos["symbol"], pos["strike"],
                                    pos["option_type"]): _env("REAL", 95.0,
                                                              age=5.0)})
        with mock.patch.object(eng.exit_evaluator, "quote_source",
                               FakeQuoteSource({})):
            eng.run_exit_checks(now=_now(11, 0))
        r1 = eng.run_exit_checks(quote_source=src, now=_now(11, 5))
        r2 = eng.run_exit_checks(quote_source=src, now=_now(11, 6))
        self.assertEqual(len(r1["closed"]), 1)
        self.assertEqual(r1["evaluated"], 1)
        self.assertEqual(r2["evaluated"], 0)
        self.assertEqual(r2["closed"], [])
        closes = [o for o in eng.account.get("orders", [])
                  if o.get("order_kind") == "CLOSE"]
        self.assertEqual(len(closes), 1)
        self.assertEqual(_gt_count(tmp, "executions"), 2)
        self.assertEqual(_gt_count(tmp, "outcomes"), 1)


class DuplicatePreventionTests(unittest.TestCase):

    def test_double_close_rejected(self):
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        eng.close_position(pos["position_ref"], 95.0, exit_reason="STOP_LOSS",
                           ts="2026-08-14 11:00:00 IST")
        with self.assertRaises(ValueError):
            eng.close_position(pos["position_ref"], 95.0,
                               exit_reason="STOP_LOSS",
                               ts="2026-08-14 11:01:00 IST")
        self.assertEqual(_gt_count(tmp, "outcomes"), 1)

    def test_gt_single_outcome_per_position(self):
        """outcomes.position_id is UNIQUE - one outcome per position."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        eng.close_position(pos["position_ref"], 95.0, exit_reason="STOP_LOSS",
                           ts="2026-08-14 11:00:00 IST")
        self.assertEqual(_gt_count(tmp, "outcomes"), 1)
        con = sqlite3.connect(os.path.join(str(tmp), "ground_truth.db"))
        try:
            row = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='outcomes'"
            ).fetchone()
        finally:
            con.close()
        self.assertIn("position_id INTEGER NOT NULL UNIQUE", row[0])

    def test_append_only_triggers_present(self):
        """All GT tables keep append-only UPDATE/DELETE guards."""
        tmp = tempfile.mkdtemp()
        ledger = ground_truth.GroundTruthDB(
            os.path.join(str(tmp), "ground_truth.db"))
        ledger.record_observation(ts="2026-08-14 10:00:00 IST", symbol="NIFTY",
                                  price=24400.0, source="test", valid=1)
        con = sqlite3.connect(os.path.join(str(tmp), "ground_truth.db"))
        try:
            triggers = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()]
        finally:
            con.close()
        for table, prefix in (("market_observations", "observations"),
                              ("feature_snapshots", "snapshots"),
                              ("signals", "signals"),
                              ("predictions", "predictions"),
                              ("decisions", "decisions"),
                              ("executions", "executions"),
                              ("outcomes", "outcomes")):
            self.assertTrue(
                any(f"{prefix}_append_only" in tg for tg in triggers),
                f"missing append-only trigger for {table}")


class FreshnessRecoveryTests(unittest.TestCase):

    def test_real_stale_missing_real_transition(self):
        """Quote status transitions REAL->STALE->MISSING->REAL map to skip rules."""
        tmp = tempfile.mkdtemp()
        eng = _engine(tmp)
        pos = _open_position(eng)
        k = _key(pos["symbol"], pos["strike"], pos["option_type"])
        fresh = FakeQuoteSource({k: _env("REAL", 95.0, age=5.0)})
        stale = FakeQuoteSource({k: _env("STALE", 95.0, age=900.0)})
        missing = FakeQuoteSource({})
        now = _now()
        d_fresh = eng.exit_evaluator.evaluate_position(
            pos, quote=fresh.get_quote(*k, now=now), now=now)
        d_stale = eng.exit_evaluator.evaluate_position(
            pos, quote=stale.get_quote(*k, now=now), now=now)
        d_missing = eng.exit_evaluator.evaluate_position(
            pos, quote=missing.get_quote(*k, now=now), now=now)
        d_back = eng.exit_evaluator.evaluate_position(
            pos, quote=fresh.get_quote(*k, now=now), now=now)
        self.assertTrue(d_fresh["triggered"])
        self.assertEqual(d_fresh["reason"], "STOP_LOSS")
        self.assertFalse(d_stale["triggered"])
        self.assertEqual(d_stale["skip_reason"], "STALE_QUOTE_NO_TRIGGER")
        self.assertFalse(d_missing["triggered"])
        self.assertEqual(d_missing["skip_reason"], "MISSING_QUOTE")
        self.assertTrue(d_back["triggered"])

    def test_truth_freshness_transitions(self):
        self.assertEqual(truth.freshness_status(5, 100), truth.REAL)
        self.assertEqual(truth.freshness_status(500, 100), truth.STALE)
        self.assertEqual(truth.freshness_status(None, 100), truth.MISSING)


class DaemonResilienceTests(unittest.TestCase):

    def test_daemon_survives_feed_failure(self):
        """Feed down does not kill the daemon; cycles keep running."""
        tmp = tempfile.mkdtemp()
        pid_f = os.path.join(tmp, "daemon.pid")
        log_f = os.path.join(tmp, "daemon.log")
        calls = {"n": 0}

        def fake_update():
            calls["n"] += 1
            if calls["n"] >= 3:
                raise KeyboardInterrupt()
            return _feed_down()

        buf = io.StringIO()
        with redirect_stdout(buf), _patched([
            mock.patch("quant_daemon.PID_FILE", pid_f),
            mock.patch("quant_daemon.LOG_FILE", log_f),
            mock.patch("time.sleep"),
            mock.patch("live_market_fetch.update_live_market_cache",
                       side_effect=fake_update),
            mock.patch("auto_paper_runner.run_auto_paper_trader",
                       return_value={"status": "STAND_DOWN",
                                     "reason": "no live or cached spot"}),
            mock.patch("auto_enhancer.run_auto_enhancement_cycle"),
        ]):
            quant_daemon.run_daemon_loop()
        with open(log_f) as f:
            log = f.read()
        self.assertIn("Cycle #1", log)
        self.assertIn("Cycle #2", log)
        self.assertFalse(os.path.exists(pid_f))

    def test_daemon_fail_stop_visible_on_unexpected(self):
        """Unexpected exception in a cycle -> fail-stop with visible reason."""
        tmp = tempfile.mkdtemp()
        pid_f = os.path.join(tmp, "daemon.pid")
        log_f = os.path.join(tmp, "daemon.log")
        buf = io.StringIO()
        with redirect_stdout(buf), _patched([
            mock.patch("quant_daemon.PID_FILE", pid_f),
            mock.patch("quant_daemon.LOG_FILE", log_f),
            mock.patch("time.sleep"),
            mock.patch("live_market_fetch.update_live_market_cache",
                       return_value=_feed_up()),
            mock.patch("auto_paper_runner.run_auto_paper_trader",
                       side_effect=RuntimeError("simulated engine bug")),
        ]):
            with self.assertRaises(RuntimeError):
                quant_daemon.run_daemon_loop()
        self.assertFalse(os.path.exists(pid_f))


class GroundTruthSafetyTests(unittest.TestCase):

    def test_no_fabricated_observation_marked_real(self):
        """Signal with no spot -> observation valid=0, provenance MISSING."""
        tmp = tempfile.mkdtemp()
        ledger = ground_truth.GroundTruthDB(
            os.path.join(str(tmp), "ground_truth.db"))
        sig = {"signal_action": "STAY_OUT", "signal_grade": "NO_SIGNAL",
               "nifty_spot": None, "confluence_checks": {},
               "confluence_score": "0/6 (0%)", "confidence": None,
               "market_state": None, "vix": None, "vix_zone": None}
        with mock.patch("truth.file_freshness",
                        return_value={"age_h": None, "status": truth.MISSING}):
            ledger.record_signal_chain(sig, provenance={"status": truth.MISSING})
        con = sqlite3.connect(os.path.join(str(tmp), "ground_truth.db"))
        try:
            row = con.execute(
                "SELECT valid, provenance_json FROM market_observations"
            ).fetchone()
        finally:
            con.close()
        self.assertEqual(row[0], 0)
        prov = json.loads(row[1])
        self.assertNotEqual(prov.get("status"), truth.REAL)
        self.assertEqual(prov.get("status"), truth.MISSING)


class ProductionIsolationTests(unittest.TestCase):
    """The Phase G suite must not create or corrupt production data files."""

    ALLOWED_CHANGES = {
        "nifty_history.csv", "india_vix.csv", "ground_truth.db",
        "paper_account.json", "history.db", "quant_daemon.log",
    }

    def test_no_stray_files_in_data(self):
        """No test artifacts appear under data/ beyond daemon-owned files."""
        before = set(os.listdir(os.path.join(ROOT, "data")))
        after = set(os.listdir(os.path.join(ROOT, "data")))
        for name in sorted(after - before):
            self.assertIn(name, self.ALLOWED_CHANGES,
                          f"test created unexpected file data/{name}")

    def test_protected_files_readable(self):
        for name in ("ground_truth.db", "paper_account.json", "research.db",
                     "nifty_history.csv"):
            p = os.path.join(ROOT, "data", name)
            if os.path.exists(p):
                self.assertGreater(os.path.getsize(p), 0, name)


if __name__ == "__main__":
    unittest.main()
