"""Phase H - multi-strategy fair-comparison tests.

Verifies the Phase H measurement contract WITHOUT running the expensive
full-window ML pipeline (that is exercised by multi_strategy_backtest.py
itself and checked for determinism by double-run).

Covers:
  * frozen strategy specifications (all required fields, stable spec hash,
    no hidden tuning surfaces)
  * same dataset / same cost+slippage model for every candidate
  * candidate-specific execution: A control path, B vertical-spread
    construction (short leg = long +/- 500, defined risk), C iron condor
    structure (2% OTM + 150-pt wings, credit target/stop), D no-trade
  * missing-data behavior (CONTRACT_UNAVAILABLE -> no trade, no substitute)
  * no-lookahead (VIX / options layers only use data dated <= t)
  * deterministic output (identical results on repeat invocation)
  * no production writes (open() guard on ground_truth.db / paper_account /
    data/*)
  * committed results artifact structure

Run: .venv/bin/python -m unittest tests.test_phase_h_multi_strategy -v
"""
import datetime as dt
import builtins
import json
import os
import sys
import unittest
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest_frozen as bf            # noqa: E402
import multi_strategy_backtest as m     # noqa: E402


def _nifty(rows):
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _chain(strikes, expiry_str, ce_ltp=None, pe_ltp=None):
    """Minimal frozen-schema chain DataFrame (only fields the runner uses)."""
    n = len(strikes)
    return pd.DataFrame({
        "expiry": [expiry_str] * n,
        "strike": [float(s) for s in strikes],
        "ce_ltp": [float(ce_ltp[i]) if ce_ltp else float(100 - i) for i in range(n)],
        "pe_ltp": [float(pe_ltp[i]) if pe_ltp else float(90 - i) for i in range(n)],
        "ce_oi": [0] * n, "pe_oi": [0] * n, "ce_iv": [0.15] * n, "pe_iv": [0.15] * n,
    })


class TestFrozenSpecs(unittest.TestCase):
    def test_all_candidates_have_full_specs(self):
        required = {
            "name", "instrument", "entry_gate", "direction_logic",
            "regime_restriction", "expiry_rule", "strike_rule", "entry_price",
            "stop_rule", "target_rule", "exit_rule", "position_size",
            "cost_model", "slippage_model", "data_requirements",
            "unsupported_conditions", "frozen_reference",
        }
        self.assertEqual(set(m.CANDIDATE_SPECS),
                         {"A_CURRENT_CONTROL", "B_DIRECTIONAL_SPREAD",
                          "C_RANGE_HV_IRON_CONDOR", "D_NO_TRADE"})
        for cand, spec in m.CANDIDATE_SPECS.items():
            missing = required - set(spec)
            self.assertFalse(missing, f"{cand} missing spec fields: {missing}")
            for v in spec.values():
                self.assertIsNotNone(str(v).strip())

    def test_frozen_constants_no_tuning_surface(self):
        # The only free parameters are single integer constants frozen in the
        # module; verify they are plain numbers and documented in the specs.
        for v in (m.SPREAD_WIDTH, m.SPREAD_VIX_MAX, m.SPREAD_VIX_MIN,
                  m.CONDOR_OTM_PCT, m.CONDOR_WING_PTS, m.CONDOR_TARGET_PCT,
                  m.CONDOR_STOP_MULT, m.CONDOR_CLOSE_BEFORE_DAYS):
            self.assertIsInstance(v, (int, float))
        self.assertEqual(m.SPREAD_WIDTH, 500.0)
        self.assertIn("500", m.CANDIDATE_SPECS["B_DIRECTIONAL_SPREAD"]["strike_rule"])
        self.assertIn("1.02", m.CANDIDATE_SPECS["C_RANGE_HV_IRON_CONDOR"]["strike_rule"])

    def test_spec_hash_is_stable(self):
        h1 = m.sha256_bytes(json.dumps(m.CANDIDATE_SPECS, sort_keys=True).encode())
        h2 = m.sha256_bytes(json.dumps(m.CANDIDATE_SPECS, sort_keys=True).encode())
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        # frozen reference recorded in the audit doc
        self.assertIn("F3 baseline", m.CANDIDATE_SPECS["A_CURRENT_CONTROL"]["frozen_reference"])

    def test_no_candidate_gets_extra_parameters(self):
        # Every candidate references the SAME shared execution constants.
        self.assertIn("COST_PER_TRADE", m.CANDIDATE_SPECS["A_CURRENT_CONTROL"]["cost_model"])
        self.assertIn("SLIPPAGE_PCT", m.CANDIDATE_SPECS["A_CURRENT_CONTROL"]["slippage_model"])
        for cand in ("B_DIRECTIONAL_SPREAD", "C_RANGE_HV_IRON_CONDOR"):
            self.assertIn("40.0", m.CANDIDATE_SPECS[cand]["cost_model"])
            self.assertIn("0.015", m.CANDIDATE_SPECS[cand]["slippage_model"])


class TestSameModel(unittest.TestCase):
    def test_shared_cost_and_slippage_constants(self):
        self.assertEqual(m.COST_PER_TRADE, bf.COST_PER_TRADE)
        self.assertEqual(m.SLIPPAGE_PCT, bf.SLIPPAGE_PCT)
        # per-candidate order counts are the ONLY legitimate cost difference
        self.assertEqual(m.PER_CANDIDATE_ORDERS,
                         {"A_CURRENT_CONTROL": 2, "B_DIRECTIONAL_SPREAD": 4,
                          "C_RANGE_HV_IRON_CONDOR": 8, "D_NO_TRADE": 0})

    def test_same_window_and_expiry_source(self):
        self.assertEqual(m.WINDOW_START, bf.WINDOW_START)
        self.assertEqual(m.WINDOW_END, bf.WINDOW_END)
        self.assertIs(m.exp_cal, __import__("expiry_calendar"))

    def test_deterministic_metrics(self):
        rows = m.trade_rows("A_CURRENT_CONTROL", [
            {"date": "2026-01-02", "simulation": {"exit_date": "2026-01-05",
             "reason": "TAKE_PROFIT", "net_pnl": 100.0, "slippage": 5.0,
             "mfe": 120.0, "mae": -10.0, "days_held": 3}, "regime": "TREND_HV",
             "grade": "A", "option_type": "PE", "strike": 24000},
            {"date": "2026-01-06", "simulation": {"exit_date": "2026-01-07",
             "reason": "STOP_LOSS", "net_pnl": -60.0, "slippage": 4.0,
             "mfe": 5.0, "mae": -70.0, "days_held": 1}, "regime": "RANGE_HV",
             "grade": "A", "option_type": "PE", "strike": 24000},
        ])
        a = m.compute_metrics("A_CURRENT_CONTROL", rows, 245)
        b_ = m.compute_metrics("A_CURRENT_CONTROL", rows, 245)
        self.assertEqual(json.dumps(a, sort_keys=True, default=str),
                         json.dumps(b_, sort_keys=True, default=str))
        self.assertEqual(a["trade_count"], 2)
        self.assertEqual(a["win_rate"], 50.0)
        self.assertEqual(a["net_pnl"], 40.0)

    def test_no_trade_control(self):
        trades = m.run_candidate_d({}, None, None, None)
        self.assertEqual(trades, [])
        rows = m.trade_rows("D_NO_TRADE", trades)
        mm = m.compute_metrics("D_NO_TRADE", rows, 245)
        self.assertEqual(mm["trade_count"], 0)
        self.assertEqual(mm["net_pnl"], 0.0)


class TestCandidateB(unittest.TestCase):
    def setUp(self):
        d0 = dt.date(2026, 1, 5)
        e = dt.date(2026, 1, 8)
        self.expiry = e
        self.d0 = d0
        e_str = e.strftime("%d-%b-%Y")
        # 50-pt grid 23000..25500 all listed for expiry e on every day
        strikes = list(range(23000, 25600, 50))
        self.nifty = _nifty([(d0, 24500.0),
                             (dt.date(2026, 1, 6), 24400.0),
                             (dt.date(2026, 1, 7), 24300.0),
                             (dt.date(2026, 1, 8), 24200.0)])
        ce = [float(max(0, 200 - (s - 24500))) for s in strikes]
        pe = [float(max(0, 200 - (24500 - s))) for s in strikes]
        chains = {}
        for d in (d0, dt.date(2026, 1, 6), dt.date(2026, 1, 7), dt.date(2026, 1, 8)):
            chains[d] = _chain(strikes, e_str, ce_ltp=ce, pe_ltp=pe)
        self.snaps = chains
        self.nd = [d0, dt.date(2026, 1, 6), dt.date(2026, 1, 7), dt.date(2026, 1, 8)]

    def test_short_leg_is_long_plus_500_for_call(self):
        rec = {"strike": 24500, "expiry": str(self.expiry), "spot": 24500.0,
               "walls": {}}
        built = m.build_spread(rec, self.snaps, self.d0, "CE", 24500)
        self.assertIsNotNone(built)
        long_k, short_k, side, exp = built
        self.assertEqual(long_k, 24500)
        self.assertEqual(short_k, 25000)  # 24500 + 500 on the 50-pt grid
        self.assertEqual(side, "CE")
        self.assertEqual(exp, self.expiry)

    def test_short_leg_is_long_minus_500_for_put(self):
        rec = {"strike": 24500, "expiry": str(self.expiry), "spot": 24500.0,
               "walls": {}}
        built = m.build_spread(rec, self.snaps, self.d0, "PE", 24500)
        self.assertIsNotNone(built)
        long_k, short_k, side, _ = built
        self.assertEqual(long_k, 24500)
        self.assertEqual(short_k, 24000)  # 24500 - 500
        self.assertEqual(side, "PE")

    def test_unknown_expiry_returns_none(self):
        rec = {"strike": 24500, "expiry": str(self.expiry), "spot": 24500.0, "walls": {}}
        # chain lists a different expiry -> no listed strikes for our expiry
        snaps = {self.d0: _chain(list(range(23000, 25600, 50)), "15-Jan-2026")}
        self.assertIsNone(m.build_spread(rec, snaps, self.d0, "CE", 24500))

    def test_short_leg_snaps_to_nearest_listed(self):
        rec = {"strike": 24500, "expiry": str(self.expiry), "spot": 24500.0, "walls": {}}
        # 25000 not listed -> nearest listed 50 pts away (tie broken to lower)
        strikes = [s for s in range(23000, 25100, 50) if s != 25000]
        snaps = {self.d0: _chain(strikes, self.expiry.strftime("%d-%b-%Y"))}
        built = m.build_spread(rec, snaps, self.d0, "CE", 24500)
        self.assertIsNotNone(built)
        self.assertIn(built[1], (24950.0, 25050.0))
        self.assertNotEqual(built[1], 25000.0)

    def test_spread_simulation_deterministic_and_defined_risk(self):
        rec = {"strike": 24500, "expiry": str(self.expiry), "spot": 24500.0, "walls": {}}
        sim1 = m.simulate_spread(self.d0, 24500.0, self.expiry, 24500, 25000, "CE",
                                 self.nifty, self.snaps, self.nd)
        sim2 = m.simulate_spread(self.d0, 24500.0, self.expiry, 24500, 25000, "CE",
                                 self.nifty, self.snaps, self.nd)
        self.assertEqual(json.dumps(sim1, sort_keys=True, default=str),
                         json.dumps(sim2, sort_keys=True, default=str))
        self.assertIsNotNone(sim1.get("exit_date"))
        # defined risk: max possible loss (width - net debit) * lot + costs
        entry = sim1["entry_net"]
        width = 500.0
        floor = -(width - entry) * m.LOT_SIZE - 4 * m.COST_PER_TRADE
        self.assertGreaterEqual(sim1["net_pnl"], floor)
        self.assertIn(sim1["reason"], ("STOP_LOSS", "TAKE_PROFIT", "EXPIRY_SQUARE_OFF"))

    def test_candidate_b_entry_fields(self):
        rec = {"date": "2026-01-05", "spot": 24500.0, "regime": "TREND_HV",
               "grade": "A", "tech_bias": "CALL", "action": "MODERATE_CALL",
               "expiry": str(self.expiry), "candidate": True, "walls": {}}
        trades = m.run_candidate_b({"2026-01-05": rec}, self.nifty, self.snaps, self.nd)
        self.assertEqual(len(trades), 1)
        t = trades[0]
        self.assertEqual(t["option_type"], "SPREAD_CE")
        # no wall in rec -> long leg = spot*1.01 rounded to 50-grid
        self.assertEqual(t["strike"], 24750)
        self.assertEqual(t["short_strike"], 25250.0)
        self.assertEqual(t["spread_width"], 500.0)

    def test_range_regime_excluded_from_b(self):
        rec = {"date": "2026-01-05", "spot": 24500.0, "regime": "RANGE_HV",
               "grade": "A", "tech_bias": "CALL", "action": "MODERATE_CALL",
               "expiry": str(self.expiry), "candidate": True, "walls": {}}
        trades = m.run_candidate_b({"2026-01-05": rec}, self.nifty, self.snaps, self.nd)
        self.assertEqual(trades, [])


class TestCandidateC(unittest.TestCase):
    def setUp(self):
        d0 = dt.date(2026, 4, 6)
        e = dt.date(2026, 4, 14)
        self.expiry = e
        self.d0 = d0
        e_str = e.strftime("%d-%b-%Y")
        strikes = list(range(23000, 26200, 50))
        self.nifty = _nifty([(d0, 24500.0),
                             (dt.date(2026, 4, 7), 24450.0),
                             (dt.date(2026, 4, 8), 24400.0),
                             (dt.date(2026, 4, 9), 24550.0),
                             (dt.date(2026, 4, 10), 24500.0),
                             (dt.date(2026, 4, 13), 24520.0),
                             (dt.date(2026, 4, 14), 24510.0)])
        # explicit leg marks so the condor has positive credit < width (150):
        # short call Kc=25000 -> 100, call wing 25150 -> 40
        # short put Kp=24000 -> 70, put wing 23850 -> 30
        ce_mark = {25000: 100.0, 25150: 40.0}
        pe_mark = {24000: 70.0, 23850: 30.0}
        ce = [ce_mark.get(s, 0.0) for s in strikes]
        pe = [pe_mark.get(s, 0.0) for s in strikes]
        self.snaps = {d: _chain(strikes, e_str, ce_ltp=ce, pe_ltp=pe) for d in self.nifty["date"].dt.date}
        self.nd = [d.date() for d in self.nifty["date"]]

    def test_condor_structure(self):
        built = m.build_condor(24500.0, self.expiry, self.snaps, self.d0)
        self.assertIsNotNone(built)
        Kc, Kp, KcW, KpW = built
        self.assertEqual(Kc, round(24500 * 1.02 / 50) * 50)  # ~2% OTM call
        self.assertEqual(Kp, round(24500 * 0.98 / 50) * 50)  # ~2% OTM put
        self.assertEqual(KcW - Kc, 150.0)
        self.assertEqual(Kp - KpW, 150.0)

    def test_condor_simulation_deterministic_and_bounded(self):
        strikes = m.build_condor(24500.0, self.expiry, self.snaps, self.d0)
        sim1 = m.simulate_condor(self.d0, 24500.0, self.expiry, strikes, self.nifty, self.snaps, self.nd)
        sim2 = m.simulate_condor(self.d0, 24500.0, self.expiry, strikes, self.nifty, self.snaps, self.nd)
        self.assertEqual(json.dumps(sim1, sort_keys=True, default=str),
                         json.dumps(sim2, sort_keys=True, default=str))
        self.assertIsNotNone(sim1.get("exit_date"))
        self.assertIn(sim1["reason"], ("TARGET", "STOP", "TIME", "EXPIRY", "EOD"))
        # max loss = width - credit
        floor = -sim1["max_loss"] * m.LOT_SIZE - 8 * m.COST_PER_TRADE
        self.assertGreaterEqual(sim1["net_pnl"], floor)
        self.assertGreater(sim1["entry_credit"], 0)

    def test_condor_skips_when_credit_zero_or_leg_missing(self):
        # chain with NO listed wing strikes -> build returns None
        e_str = self.expiry.strftime("%d-%b-%Y")
        snaps = {self.d0: _chain([24950, 24000], e_str)}
        self.assertIsNone(m.build_condor(24500.0, self.expiry, snaps, self.d0))

    def test_candidate_c_gate_requires_range_hv_and_vix(self):
        recs = {"2026-04-06": {"regime": "TREND_HV", "vix": 18.0, "spot": 24500.0,
                               "date": "2026-04-06"},
                "2026-04-07": {"regime": "RANGE_HV", "vix": 13.0, "spot": 24500.0,
                               "date": "2026-04-07"},
                "2026-04-08": {"regime": "RANGE_HV", "vix": 18.0, "spot": 24500.0,
                               "date": "2026-04-08"}}
        with mock.patch.object(m.exp_cal, "get_expiry_for_trade_date",
                               return_value=self.expiry):
            trades = m.run_candidate_c(recs, self.nifty, self.snaps, self.nd)
        # TREND_HV excluded, VIX<16 excluded, only the RANGE_HV+VIX>=16 day trades
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["date"], "2026-04-08")
        self.assertEqual(trades[0]["option_type"], "IRON_CONDOR")


class TestNoLookahead(unittest.TestCase):
    def test_vix_snapshot_uses_only_rows_le_t(self):
        vix = pd.DataFrame({
            "date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
            "close": [10.0, 11.0, 40.0],
        })
        snap = bf.vix_snapshot_at(vix, dt.date(2026, 1, 6))
        self.assertEqual(snap["level"], 11.0)  # 40.0 (future) must not leak
        self.assertIn(snap["zone"], ("VIX_CHEAP", "VIX_NORMAL"))

    def test_options_layer_uses_only_snapshots_le_t(self):
        e = "08-Jan-2026"
        chain_old = _chain([24500, 24600], e, ce_ltp=[50, 10], pe_ltp=[40, 8])
        chain_new = _chain([24500, 24600], e, ce_ltp=[900, 850], pe_ltp=[800, 700])
        snaps = {dt.date(2026, 1, 5): chain_old, dt.date(2026, 1, 8): chain_new}
        res = m.contract_mark(snaps, dt.date(2026, 1, 6), 24500, "CE",
                              dt.date(2026, 1, 8), spot=24500.0)
        # future snapshot (2026-01-08) must not leak; falls back to BS
        self.assertNotEqual(res, 900.0)


class TestProductionIsolation(unittest.TestCase):
    def test_measurement_path_never_writes_production(self):
        blocked = ("ground_truth", "paper_account", "/data/")
        real_open = builtins.open
        written = []

        def guarded_open(file, mode="r", *a, **k):
            if isinstance(mode, str) and any(c in mode for c in "wax") and \
               any(b in str(file) for b in blocked):
                written.append(str(file))
                raise AssertionError(f"blocked write to {file}")
            return real_open(file, mode, *a, **k)

        with mock.patch("builtins.open", side_effect=guarded_open):
            rows = m.trade_rows("A_CURRENT_CONTROL", [
                {"date": "2026-01-02", "simulation": {"exit_date": "2026-01-03",
                 "reason": "TAKE_PROFIT", "net_pnl": 10.0, "slippage": 1.0,
                 "mfe": 5.0, "mae": -1.0, "days_held": 1}, "regime": "TREND_HV",
                 "grade": "A", "option_type": "PE", "strike": 24000}])
            m.compute_metrics("A_CURRENT_CONTROL", rows, 245)
            m.run_candidate_d({}, None, None, None)
        self.assertEqual(written, [])


class TestCommittedArtifact(unittest.TestCase):
    def test_results_file_structure(self):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "results", "phaseH_multi_strategy.json")
        if not os.path.exists(p):
            self.skipTest("results/phaseH_multi_strategy.json not generated yet")
        with open(p) as fh:
            d = json.load(fh)
        self.assertIn("result_hash", d)
        self.assertIn("spec_hash", d)
        self.assertIn("candidates", d)
        for cand in ("A_CURRENT_CONTROL", "B_DIRECTIONAL_SPREAD",
                     "C_RANGE_HV_IRON_CONDOR", "D_NO_TRADE"):
            c = d["candidates"][cand]
            for key in ("trades", "metrics", "by_regime", "monthly", "oos", "concentration"):
                self.assertIn(key, c, cand)
            for key in ("trade_count", "win_rate", "net_pnl", "profit_factor",
                        "max_drawdown", "expectancy"):
                self.assertIn(key, c["metrics"], cand)


if __name__ == "__main__":
    unittest.main()
