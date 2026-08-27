"""Phase H1 v2 - Backtest Adapter (thin).

Allows a CompiledStrategy to run inside the EXISTING frozen backtest framework
without rewriting it. Each strategy id maps to its authoritative engine
function (the same engines Phase H used). The adapter re-runs the engine over
the frozen dataset, cross-checks every produced trade against the compiled
spec's invariants, and compares the output to the authoritative committed
Phase H results for the CONTROL EQUIVALENCE proof.
"""
import os
import json
import datetime as dt

import backtest_frozen as bf
import expiry_calendar as exp_cal
import multi_strategy_backtest as m

AUTHORITATIVE_RESULTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "results", "phaseH_multi_strategy.json")

# strategy_id -> (phase-H candidate key, engine function)
ENGINES = {
    "current_control_v1": ("A_CURRENT_CONTROL", m.run_candidate_a),
    "range_hv_iron_condor_v1": ("C_RANGE_HV_IRON_CONDOR", m.run_candidate_c),
    "directional_spread_v1": ("B_DIRECTIONAL_SPREAD", m.run_candidate_b),
}

# Per-instrument expected option_type prefix for the consistency cross-check.
OPTION_TYPE_EXPECT = {
    "current_control_v1": "PE",            # frozen defect: all-PUT
    "range_hv_iron_condor_v1": "IRON_CONDOR",
    "directional_spread_v1": "SPREAD_",
}


class BacktestAdapter:
    def __init__(self, compiled, data_root=None, reference=None):
        if compiled.strategy_id not in ENGINES:
            raise ValueError(f"no backtest engine registered for {compiled.strategy_id}")
        self.compiled = compiled
        self.data_root = data_root
        self.candidate_key, self.engine = ENGINES[compiled.strategy_id]
        self.reference = reference or AUTHORITATIVE_RESULTS

    # -- execution ------------------------------------------------------------------
    def run(self):
        """Run the compiled strategy through the frozen engine. Returns dict."""
        old_root, old_cal = bf.ROOT, exp_cal.CALENDAR_CSV
        try:
            nifty, vix, fii, ml, snaps = m.load_inputs(data_root=self.data_root)
            nifty_dates = m.nifty_dates_of(nifty)
            window = [d for d in nifty_dates if m.WINDOW_START <= d <= m.WINDOW_END]
            recs = m.day_records(window, nifty, vix, fii, ml, snaps, nifty_dates)
            trades = self.engine(recs, nifty, snaps, nifty_dates)
            rows = m.trade_rows(self.candidate_key, trades)
            metrics = m.compute_metrics(self.candidate_key, rows, len(window))
            fp = m.fingerprints(nifty, vix, fii, ml, snaps, data_root=self.data_root)
        finally:
            bf.ROOT, exp_cal.CALENDAR_CSV = old_root, old_cal
        return {
            "strategy_id": self.compiled.strategy_id,
            "candidate_key": self.candidate_key,
            "trades": rows,
            "metrics": metrics,
            "by_regime": m.group_by(rows, "regime"),
            "monthly": m.monthly_rows(rows),
            "fingerprints": fp,
            "spec_hash": self.compiled.spec_hash,
        }

    # -- spec consistency cross-check --------------------------------------------------
    def check_spec_consistency(self, run):
        """Every produced trade must satisfy the compiled spec's invariants."""
        allowed_regimes = set(self.compiled.spec["regime"]["allowed"])
        allowed_reasons = set(self.compiled.spec["exit"]["allowed_reasons"])
        orders = self.compiled.spec["execution"]["cost_model"]["orders_per_round_trip"]
        cost = self.compiled.spec["execution"]["cost_model"]["cost_per_order"]
        expect_type = OPTION_TYPE_EXPECT.get(self.compiled.strategy_id)
        expected_expiry_cache = {}

        def expected_expiry(entry_date):
            d = dt.date.fromisoformat(entry_date)
            if d not in expected_expiry_cache:
                expected_expiry_cache[d] = exp_cal.get_expiry_for_trade_date(d)
            return expected_expiry_cache[d]

        violations = []
        for t in run["trades"]:
            if t["regime"] not in allowed_regimes:
                violations.append(f"regime {t['regime']} not in spec.allowed")
            if t["reason"] not in allowed_reasons:
                violations.append(f"reason {t['reason']} not in spec.exit.allowed_reasons")
            if expect_type and not str(t["option_type"]).startswith(expect_type):
                violations.append(f"option_type {t['option_type']} != {expect_type}")
            if t["fees"] != round(orders * cost, 2):
                violations.append(f"fees {t['fees']} != {orders}*{cost}")
            if expected_expiry(t["entry_date"]) is None:
                violations.append(f"no canonical expiry for {t['entry_date']}")
        return violations

    # -- control equivalence --------------------------------------------------------------
    def equivalence(self, run):
        """Compare run trades to the authoritative committed Phase H results.

        Tolerance: exact (deterministic engines, byte-identical rows). Any
        difference is reported in detail; equivalence only when none.
        """
        ref = self._reference()
        ref_trades = ref["candidates"][self.candidate_key]["trades"]
        run_trades = run["trades"]
        diffs = []
        if len(run_trades) != len(ref_trades):
            diffs.append(f"trade count: run={len(run_trades)} reference={len(ref_trades)}")
        for i, (a, b) in enumerate(zip(run_trades, ref_trades)):
            for key in ("entry_date", "exit_date", "regime", "grade", "option_type",
                        "strike", "reason", "net_pnl", "fees", "slippage", "mfe", "mae", "days_held"):
                if a.get(key) != b.get(key):
                    diffs.append(f"trade[{i}].{key}: run={a.get(key)} ref={b.get(key)}")
            for key in ("short_strike", "spread_width"):
                if a.get(key) != b.get(key):
                    diffs.append(f"trade[{i}].{key}: run={a.get(key)} ref={b.get(key)}")
        return {"matched": not diffs, "run_hash": self._run_hash(run),
                "reference_hash": ref.get("result_hash"),
                "run_trades": len(run_trades), "reference_trades": len(ref_trades),
                "differences": diffs[:20]}

    # -- helpers ---------------------------------------------------------------------------
    def _reference(self):
        if not os.path.exists(self.reference):
            raise FileNotFoundError(f"reference results not found: {self.reference}")
        with open(self.reference) as fh:
            return json.load(fh)

    @staticmethod
    def _run_hash(run):
        canonical = json.dumps(run["trades"], sort_keys=True, default=str)
        import hashlib
        return hashlib.sha256(canonical.encode()).hexdigest()
