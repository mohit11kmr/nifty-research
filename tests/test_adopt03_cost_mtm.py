"""Phase B (ADOPT-03) - Paper Cost Model + Mark-to-Market tests.

Covers:
- deterministic cost model (commission allocation, adverse slippage)
- cost-aware fill records (fill_price/reference_price/slippage/fees)
- account fee & slippage tallies
- net realized P&L at close == Ground Truth outcome net (parity)
- mark-to-market report (REAL/STALE/MISSING status, BUY/SELL, equity
  invariant, read-only, no GT outcome creation)
- ResearchDBQuoteSource envelope statuses (REAL/STALE/MISSING/INVALID)
- paper_trader slippage-aware execution + cost-aware summary
- production isolation: nothing writes to the real ledger or paper account

All engine/DB writes redirect to temp fixtures. The production-isolation
test class only READS production data (ledger + account), asserting the
baseline is untouched by this feature.
Run: .venv/bin/python -m unittest tests.test_adopt03_cost_mtm -v
"""
import os
import sys
import json
import sqlite3
import tempfile
import unittest
import unittest.mock as mock
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ground_truth as gt
import cost_model
import paper_mtm
import paper_execution
import paper_trader

TS = "2026-08-13 10:00:00 IST"
CM = cost_model.CostModel()


def _make_fixture():
    tmp = tempfile.mkdtemp()
    acct = os.path.join(tmp, "paper_account.json")
    gt_db = os.path.join(tmp, "ground_truth.db")
    gt.RESEARCH_DB = os.path.join(tmp, "research.db")
    with open(acct, "w") as f:
        json.dump({
            "initial_capital": 100000.0,
            "cash_balance": 100000.0,
            "realized_pnl": 0.0,
            "total_fees": 0.0,
            "total_slippage": 0.0,
            "open_positions": [],
            "closed_trades": [],
        }, f)
    return tmp, acct, gt_db


def _open(acct, gt_db):
    return paper_execution.PaperExecutionEngine(account_file=acct, gt_db_file=gt_db)


def _buy(engine, price=140.0, qty=75, ref=None, **kw):
    sub = engine.submit_order(entry_price=price)
    engine.accept_order(sub["order_id"])
    return engine, engine.fill_order(
        sub["order_id"], qty, price=None,
        reference_price=(ref if ref is not None else price), **kw)


def _buy_exact(engine, price=140.0, qty=75, **kw):
    sub = engine.submit_order(entry_price=price)
    engine.accept_order(sub["order_id"])
    return engine, engine.fill_order(sub["order_id"], qty, price, **kw)


class TestCostModel(unittest.TestCase):
    def test_commission_full_fill(self):
        order = {"quantity": 75}
        self.assertEqual(CM.commission_for_fill(order, 75), 40.0)

    def test_commission_allocated_across_partial_fills(self):
        order = {"quantity": 150}
        f1 = CM.commission_for_fill(order, 40)
        f2 = CM.commission_for_fill(order, 110)
        self.assertEqual(round(f1 + f2, 2), 40.0)
        self.assertEqual(f1, round(40.0 * 40 / 150, 2))

    def test_slippage_adverse_direction(self):
        self.assertEqual(CM.slippage_price("BUY", 100.0), 101.5)
        self.assertEqual(CM.slippage_price("SELL", 100.0), 98.5)
        self.assertIsNone(CM.slippage_price("BUY", 0.0))
        self.assertIsNone(CM.slippage_price("BUY", None))

    def test_slippage_amount_and_pct(self):
        self.assertEqual(CM.slippage_amount("BUY", 101.5, 100.0, 75), 112.5)
        self.assertEqual(CM.slippage_pct_used(101.5, 100.0), 1.5)

    def test_total_cost(self):
        self.assertEqual(CM.total_cost(40.0, 12.5), 52.5)

    def test_deterministic(self):
        for _ in range(3):
            self.assertEqual(CM.slippage_price("BUY", 140.0), 142.1)
            self.assertEqual(CM.slippage_price("SELL", 160.0), 157.6)


class TestCostAwareFills(unittest.TestCase):
    def test_fill_records_cost_fields(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        e, res = _buy(e)
        fill = res["fill"]
        for key in ("fill_id", "order_id", "quantity", "fill_price", "price",
                    "reference_price", "requested_price", "slippage_amount",
                    "slippage_pct", "commission", "fees", "transaction_cost",
                    "total_cost", "timestamp", "execution_mode"):
            self.assertIn(key, fill)
        self.assertEqual(fill["fill_price"], 142.1)      # 140 * 1.015
        self.assertEqual(fill["price"], 142.1)           # back-compat alias
        self.assertEqual(fill["reference_price"], 140.0)
        self.assertEqual(fill["slippage_amount"], 157.5)  # 2.1 * 75
        self.assertEqual(fill["slippage_pct"], 1.5)
        self.assertEqual(fill["commission"], 40.0)
        self.assertEqual(fill["fees"], 40.0)

    def test_explicit_price_bypasses_slippage(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        e, res = _buy_exact(e, price=140.0)
        fill = res["fill"]
        self.assertEqual(fill["fill_price"], 140.0)
        self.assertEqual(fill["slippage_amount"], 0.0)
        self.assertEqual(fill["slippage_pct"], 0.0)

    def test_commission_override_wins(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        e, res = _buy(e, commission=10.0)
        self.assertEqual(res["fill"]["commission"], 10.0)

    def test_fill_without_any_price_raises(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        sub = e.submit_order(requested_price=0.0)   # no usable reference
        e.accept_order(sub["order_id"])
        with self.assertRaises(ValueError):
            e.fill_order(sub["order_id"], 75)

    def test_account_tallies_fees_and_slippage(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        e, res = _buy(e)
        self.assertEqual(e.account["total_fees"], 40.0)
        self.assertEqual(e.account["total_slippage"], 157.5)
        self.assertEqual(round(e.account["cash_balance"], 2),
                         round(100000.0 - 142.1 * 75, 2))


class TestRealizedNetParity(unittest.TestCase):
    def _open_and_fill(self, gt_db, acct, slip=True):
        e = _open(acct, gt_db)
        sub = e.submit_order(entry_price=140.0, sl_price=90.0, target_price=240.0)
        e.accept_order(sub["order_id"])
        if slip:
            e.fill_order(sub["order_id"], 75, price=None, reference_price=140.0)
        else:
            e.fill_order(sub["order_id"], 75, 140.0)
        ref = e._find_order(sub["order_id"])["position_ref"]
        return e, ref

    def test_net_realized_equals_gt_outcome_net(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._open_and_fill(gt_db, acct)
        res = e.close_position(ref, 160.0, ts="2026-08-13 15:00:00 IST")
        # entry fill 142.1 (slip), exit fill 157.6 (slip); fees = 40 + 40
        gross = round((157.6 - 142.1) * 75, 2)          # 1162.5
        self.assertEqual(res["realized_gross"], gross)
        self.assertEqual(res["fees"], 80.0)
        self.assertEqual(res["realized_net"], round(gross - 80.0, 2))
        self.assertEqual(e.account["realized_pnl"], res["realized_net"])
        db = gt.GroundTruthDB(gt_db)
        out = db._cur().execute(
            "SELECT net_pnl, fees, slippage FROM outcomes").fetchone()
        self.assertEqual(round(out[0], 2), res["realized_net"])
        self.assertEqual(round(out[1], 2), 80.0)
        self.assertEqual(out[2], 0.0)

    def test_explicit_entry_still_nets_exactly_with_slipped_exit(self):
        _, acct, gt_db = _make_fixture()
        e, ref = self._open_and_fill(gt_db, acct, slip=False)
        res = e.close_position(ref, 160.0, ts="2026-08-13 15:00:00 IST")
        # entry explicit 140; exit fill slipped 160*0.985=157.6 -> gross 1320
        self.assertEqual(res["realized_gross"], 1320.0)
        self.assertEqual(res["realized_net"], 1240.0)
        db = gt.GroundTruthDB(gt_db)
        out = db._cur().execute(
            "SELECT net_pnl FROM outcomes").fetchone()[0]
        self.assertEqual(round(out, 2), 1240.0)


class TestDerivedPositionsCostBasis(unittest.TestCase):
    def test_entry_fees_and_slippage_reported(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        sub = e.submit_order(entry_price=140.0)
        e.accept_order(sub["order_id"])
        e.fill_order(sub["order_id"], 40, price=None, reference_price=140.0)
        e.fill_order(sub["order_id"], 35, price=None, reference_price=140.0)
        pos = e.derived_positions()[0]
        self.assertEqual(pos["entry_price"], 142.1)
        self.assertEqual(pos["entry_fees"], 40.0)   # allocated, total once
        self.assertEqual(pos["entry_slippage"], 157.5)


class TestMarkToMarketReport(unittest.TestCase):
    def _engine_with_open(self, gt_db, acct, side="BUY", entry=140.0, mark=150.0,
                           qty=75, status="REAL"):
        e = _open(acct, gt_db)
        sub = e.submit_order(entry_price=entry)
        e.accept_order(sub["order_id"])
        e.fill_order(sub["order_id"], qty, price=None, reference_price=entry)
        ref = e._find_order(sub["order_id"])["position_ref"]
        key = ("NIFTY", 24500.0, "CE")
        quotes = {key: {
            "status": status, "price": mark, "price_basis": "ltp",
            "quote_timestamp": "2026-08-13 15:29:00.000",
            "quote_age_s": 5.0, "expiry": "18-Aug-2026",
        }}
        source = paper_mtm.FakeQuoteSource(quotes)
        return e, ref, source

    def test_real_mark_unrealized_and_equity(self):
        _, acct, gt_db = _make_fixture()
        e, ref, source = self._engine_with_open(gt_db, acct, entry=140.0, mark=150.0)
        rep = e.mark_to_market_report(quote_source=source)
        self.assertEqual(rep["position_count"], 1)
        m = rep["marked_positions"][0]
        self.assertEqual(m["quote_status"], "REAL")
        self.assertEqual(m["mark_price"], 150.0)
        # slipped entry 142.1, fees 40: unrealized = (150 - 142.1)*75 - 40
        self.assertEqual(m["unrealized_pnl"], round((150 - 142.1) * 75 - 40, 2))
        self.assertEqual(rep["unrealized_pnl"], m["unrealized_pnl"])
        # equity = cash (after slip entry) + mark value
        cash = round(100000.0 - 142.1 * 75, 2)
        self.assertEqual(rep["cash_balance"], cash)
        self.assertEqual(rep["equity"], round(cash + 150.0 * 75, 2))

    def test_stale_quote_flagged_but_used(self):
        _, acct, gt_db = _make_fixture()
        e, ref, source = self._engine_with_open(gt_db, acct, mark=150.0, status="STALE")
        rep = e.mark_to_market_report(quote_source=source)
        self.assertEqual(rep["marked_positions"][0]["quote_status"], "STALE")
        self.assertEqual(rep["marked_positions"][0]["mark_price"], 150.0)
        self.assertEqual(rep["stale_count"], 1)

    def test_missing_quote_falls_back_to_entry_no_fabrication(self):
        _, acct, gt_db = _make_fixture()
        e, ref, source = self._engine_with_open(gt_db, acct, mark=150.0)
        # drop the quote -> MISSING
        source.quotes = {}
        rep = e.mark_to_market_report(quote_source=source)
        m = rep["marked_positions"][0]
        self.assertEqual(m["quote_status"], "NO_QUOTE")
        self.assertEqual(m["price_basis"], "entry_fallback")
        self.assertEqual(m["mark_price"], 142.1)
        self.assertEqual(rep["no_quote_count"], 1)

    def test_sell_position_mark(self):
        _, acct, gt_db = _make_fixture()
        e = _open(acct, gt_db)
        sub = e.submit_order(entry_price=140.0, side="SELL")
        e.accept_order(sub["order_id"])
        e.fill_order(sub["order_id"], 75, price=None, reference_price=140.0)
        # SELL entry fill slipped: 140*0.985 = 137.9
        entry = 137.9
        key = ("NIFTY", 24500.0, "CE")
        source = paper_mtm.FakeQuoteSource({key: {"status": "REAL", "price": 130.0,
                                                  "price_basis": "ltp",
                                                  "quote_age_s": 5.0}})
        rep = e.mark_to_market_report(quote_source=source)
        m = rep["marked_positions"][0]
        # short: P&L = (entry - mark)*qty - fees = (137.9-130)*75 - 40
        self.assertEqual(m["unrealized_pnl"], round((entry - 130.0) * 75 - 40, 2))
        # equity = cash + (-mark)*qty
        cash = round(100000.0 + entry * 75, 2)
        self.assertEqual(rep["equity"], round(cash - 130.0 * 75, 2))

    def test_mtm_is_read_only(self):
        _, acct, gt_db = _make_fixture()
        e, ref, source = self._engine_with_open(gt_db, acct, mark=150.0)
        before = json.dumps(e.account, sort_keys=True, default=str)
        rep = e.mark_to_market_report(quote_source=source)
        self.assertEqual(json.dumps(e.account, sort_keys=True, default=str), before)
        db = gt.GroundTruthDB(gt_db)
        self.assertEqual(db.counts()["executions"], 1)  # only the entry fill
        self.assertEqual(db.counts()["outcomes"], 0)    # MTM created no outcome
        self.assertEqual(db.counts()["positions"], 1)   # still OPEN, not closed


class TestQuoteSourceEnvelope(unittest.TestCase):
    def _db(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "research.db")
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE ticks (recv_ts TEXT, symbol TEXT, expiry TEXT, strike REAL,"
            " side TEXT, ltp REAL, bid REAL, ask REAL)")
        now = dt.datetime.now()
        fresh = now.strftime("%Y-%m-%dT%H:%M:%S.%f")
        old = (now - dt.timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        fut = (now + dt.timedelta(seconds=600)).strftime("%Y-%m-%dT%H:%M:%S.%f")
        conn.executemany(
            "INSERT INTO ticks VALUES (?,?,?,?,?,?,?,?)",
            [
                (old, "NIFTY", "18-Aug-2026", 24500.0, "CE", 150.0, 149.0, 151.0),
                (fut, "NIFTY", "18-Aug-2026", 24501.0, "CE", 150.0, 149.0, 151.0),
                (fresh, "NIFTY", "18-Aug-2026", 24600.0, "PE", 50.0, 49.0, 51.0),
                (fresh, "NIFTY", "18-Aug-2026", 24700.0, "PE", None, 49.0, 51.0),
            ])
        conn.commit()
        conn.close()
        return path

    def test_real_latest_tick(self):
        src = paper_mtm.ResearchDBQuoteSource(self._db(), freshness_s=120)
        q = src.get_quote("NIFTY", 24600.0, "PE")
        self.assertEqual(q["status"], "REAL")
        self.assertEqual(q["price"], 50.0)
        self.assertEqual(q["price_basis"], "ltp")
        self.assertLessEqual(q["quote_age_s"], 120.0)

    def test_stale(self):
        src = paper_mtm.ResearchDBQuoteSource(self._db(), freshness_s=120)
        q = src.get_quote("NIFTY", 24500.0, "CE")
        self.assertEqual(q["status"], "STALE")
        self.assertEqual(q["price"], 150.0)
        self.assertGreater(q["quote_age_s"], 120.0)

    def test_missing(self):
        src = paper_mtm.ResearchDBQuoteSource(self._db(), freshness_s=120)
        q = src.get_quote("NIFTY", 99999.0, "CE")
        self.assertEqual(q["status"], "MISSING")
        self.assertIsNone(q["price"])

    def test_future_timestamp_invalid(self):
        src = paper_mtm.ResearchDBQuoteSource(self._db(), freshness_s=120)
        q = src.get_quote("NIFTY", 24501.0, "CE")
        self.assertEqual(q["status"], "MISSING")
        self.assertIn("future", q["reason"])

    def test_no_ltp_uses_bid_ask_mid(self):
        src = paper_mtm.ResearchDBQuoteSource(self._db(), freshness_s=120)
        q = src.get_quote("NIFTY", 24700.0, "PE")
        self.assertEqual(q["status"], "REAL")
        self.assertEqual(q["price"], 50.0)
        self.assertEqual(q["price_basis"], "bid_ask_mid")

    def test_missing_db_file(self):
        src = paper_mtm.ResearchDBQuoteSource("/no/such/file.db")
        q = src.get_quote("NIFTY", 24500.0, "CE")
        self.assertEqual(q["status"], "MISSING")


class TestPaperTraderCostAware(unittest.TestCase):
    def _make_trader(self, acct):
        paper_trader.ACCOUNT_FILE = acct
        return paper_trader.PaperTrader()

    def test_execute_applies_slippage_and_records_fill(self):
        _, acct, gt_db = _make_fixture()
        class _E(paper_execution.PaperExecutionEngine):
            def __init__(self, account_file=None, gt_db_file=None, ledger=None):
                super().__init__(account_file=account_file, gt_db_file=gt_db, ledger=ledger)
        pt = self._make_trader(acct)
        with unittest.mock.patch.object(paper_execution, "PaperExecutionEngine", _E):
            res = pt.execute_paper_order(strike=24450, entry_price=140.0)
        self.assertEqual(res["status"], "EXECUTED")
        pos = res["position"]
        self.assertEqual(pos["entry_price"], 142.1)
        self.assertEqual(pos["requested_price"], 140.0)
        self.assertEqual(pos["slippage_amount"], 157.5)
        self.assertEqual(pos["commission"], 40.0)

    def test_summary_is_cost_aware(self):
        _, acct, gt_db = _make_fixture()
        class _E(paper_execution.PaperExecutionEngine):
            def __init__(self, account_file=None, gt_db_file=None, ledger=None):
                super().__init__(account_file=account_file, gt_db_file=gt_db, ledger=ledger)
        pt = self._make_trader(acct)
        with unittest.mock.patch.object(paper_execution, "PaperExecutionEngine", _E):
            pt.execute_paper_order(strike=24450, entry_price=140.0)
            summary = pt.get_paper_account_summary()
        self.assertEqual(summary["total_fees"], 40.0)
        self.assertEqual(summary["total_slippage"], 157.5)
        self.assertEqual(summary["mtm_position_count"], 1)
        self.assertIn("unrealized_pnl", summary)
        self.assertIn("equity_marked", summary)


class TestProductionIsolation(unittest.TestCase):
    """Read-only: this feature must never touch the real ledger/account."""

    def test_production_ledger_untouched_and_baseline_intact(self):
        e = paper_execution.PaperExecutionEngine()
        db = gt.GroundTruthDB()
        counts = db.counts()
        self.assertEqual(counts["executions"], 0)
        self.assertEqual(counts["positions"], 0)
        self.assertEqual(counts["outcomes"], 0)
        rep = e.reconciliation_report()
        self.assertEqual(rep["match_status"], "MATCH")
        self.assertEqual(rep["counts"]["legacy_positions"], 10)
        self.assertEqual(rep["counts"]["gt_executions"], 0)
        self.assertEqual(rep["counts"]["errors"], 0)

    def test_production_account_mtm_is_read_only(self):
        e = paper_execution.PaperExecutionEngine()
        before = json.dumps(e.account, sort_keys=True, default=str)
        mtm = e.mark_to_market_report()
        self.assertEqual(json.dumps(e.account, sort_keys=True, default=str), before)
        # report exists and is internally consistent
        self.assertEqual(mtm["position_count"], 0)
        self.assertEqual(mtm["equity"], round(e.account["cash_balance"], 2))
        self.assertEqual(e.account["cash_balance"], 3381.25)
        self.assertEqual(e.account["realized_pnl"], 0.0)
        self.assertEqual(e.account.get("total_fees", 0.0), 0.0)


if __name__ == "__main__":
    unittest.main()
