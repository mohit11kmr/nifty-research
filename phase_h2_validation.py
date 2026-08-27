"""Phase H2 - RANGE-HV Iron Condor Validation (MEASUREMENT ONLY).

Answers: is the existing frozen Range-HV candidate strong enough to deserve
more evidence? NO strategy change, NO optimization, NO tuning. Reads the frozen
Phase H snapshot and replicates the frozen engine's decision tree to produce a
day-by-day eligibility audit, then computes descriptive statistics.

The eligibility trace is a faithful mirror of multi_strategy_backtest.
run_candidate_c (same helpers, same branch order, same single-position lock);
the trade reconstruction must equal the engine output trade-for-trade.
"""
import datetime as dt
import json
import os
import random

import backtest_frozen as bf
import expiry_calendar as exp_cal
import multi_strategy_backtest as m

FROZEN_SNAPSHOT = "/tmp/opencode/phaseH_frozen_data"

VIX_MIN = 16.0
VIX_MAX = 25.0


class RangeHVValidator:
    def __init__(self, data_root=None):
        self.data_root = data_root or FROZEN_SNAPSHOT
        old_root, old_cal = bf.ROOT, exp_cal.CALENDAR_CSV
        try:
            nifty, vix, fii, ml, snaps = m.load_inputs(data_root=self.data_root)
            self.nifty, self.vix, self.fii, self.ml, self.snaps = nifty, vix, fii, ml, snaps
            self.nifty_dates = m.nifty_dates_of(nifty)
            self.window = [d for d in self.nifty_dates if m.WINDOW_START <= d <= m.WINDOW_END]
            self.recs = m.day_records(self.window, nifty, vix, fii, ml, snaps, self.nifty_dates)
        finally:
            bf.ROOT, exp_cal.CALENDAR_CSV = old_root, old_cal

    # ------------------------------------------------------------------ eligibility
    def eligibility_trace(self):
        """Day-by-day eligibility audit replicating run_candidate_c exactly.

        Each day -> {date, regime, vix, status, reason}. status is one of
        NOT_RANGE_HV / VIX_GATE_FAIL / NO_EXPIRY / STRUCTURE_FAIL /
        NO_PRICE / INVALID_CREDIT / POSITION_LOCKED / TRADE / SKIP.
        """
        rows = []
        pos = None
        for d in self.window:
            rec = self.recs.get(str(d))
            if pos is not None:
                if str(d) == pos["sim"]["exit_date"]:
                    pos = None  # trade closes on this day (recorded elsewhere)
                    rows.append(self._row(d, rec, "TRADE_CLOSE", "position closed"))
                    continue
                rows.append(self._row(d, rec, "POSITION_LOCKED",
                                      "eligible days skipped while condor open"))
                continue
            if not rec or rec.get("skip"):
                rows.append(self._row(d, rec, "SKIP", rec.get("skip") if rec else "no record"))
                continue
            if rec["regime"] != "RANGE_HV":
                rows.append(self._row(d, rec, "NOT_RANGE_HV", f"regime={rec['regime']}"))
                continue
            vix = rec.get("vix")
            if vix is None or not (VIX_MIN <= vix < VIX_MAX):
                rows.append(self._row(d, rec, "VIX_GATE_FAIL",
                                      f"vix={vix if vix is None else round(vix, 2)}"))
                continue
            expiry = exp_cal.get_expiry_for_trade_date(d)
            if expiry is None:
                rows.append(self._row(d, rec, "NO_EXPIRY", "no canonical expiry"))
                continue
            strikes = m.build_condor(rec["spot"], expiry, self.snaps, d)
            if strikes is None:
                rows.append(self._row(d, rec, "STRUCTURE_FAIL",
                                      "condor legs not listed (CONTRACT_UNAVAILABLE)"))
                continue
            legs = m.condor_legs(self.snaps, d, expiry, *strikes, rec["spot"])
            if legs is None:
                rows.append(self._row(d, rec, "NO_PRICE", "leg prices unavailable"))
                continue
            credit = (legs["Kc"] + legs["Kp"]) - (legs["KcW"] + legs["KpW"])
            if credit <= 0:
                rows.append(self._row(d, rec, "INVALID_CREDIT", f"credit={round(credit, 2)}"))
                continue
            sim = m.simulate_condor(d, rec["spot"], expiry, strikes,
                                    self.nifty, self.snaps, self.nifty_dates)
            if sim is None or not sim.get("exit_date"):
                rows.append(self._row(d, rec, "NO_EXIT", "no exit path in remaining window"))
                continue
            pos = {"sim": sim, "expiry": expiry, "strikes": strikes, "rec": rec}
            rows.append(self._row(d, rec, "TRADE", f"entry_credit={round(credit, 2)}"))
        return rows

    @staticmethod
    def _row(d, rec, status, reason):
        return {"date": str(d), "regime": rec["regime"] if rec else None,
                "vix": round(rec["vix"], 2) if rec and rec.get("vix") is not None else None,
                "status": status, "reason": reason}

    # ------------------------------------------------------------------ trades
    def engine_trades(self):
        """Run the frozen engine and return its trade rows + full trades."""
        trades = m.run_candidate_c(self.recs, self.nifty, self.snaps, self.nifty_dates)
        rows = m.trade_rows("C_RANGE_HV_IRON_CONDOR", trades)
        return trades, rows

    def reconstruct_trades(self, rows, trace):
        """Annotate each trade row with VIX at entry, strikes, credit, risk."""
        vix_at = {r["date"]: r["vix"] for r in trace if r["vix"] is not None}
        out = []
        for r in rows:
            t = dict(r)
            t["vix_at_entry"] = vix_at.get(r["entry_date"])
            strike = r.get("strike") or ""
            if "/" in strike and "-" in strike:
                left, right = strike.split("-")
                t["long_call"], t["short_call"] = (int(p) for p in left.split("/"))
                t["short_put"], t["long_put"] = (int(p) for p in right.split("/"))
                t["wing_width"] = t["long_call"] - t["short_call"]
            t["max_risk_per_share"] = (t.get("wing_width") or 0) - (r.get("entry_premium") or 0)
            out.append(t)
        return out

    # ------------------------------------------------------------------ analyses
    @staticmethod
    def profit_concentration(rows):
        nets = sorted((r["net_pnl"] for r in rows), reverse=True)
        total = sum(nets)
        if total == 0:
            return {"total": 0.0}
        return {
            "total": round(total, 2),
            "best_trade": round(max(nets), 2),
            "worst_trade": round(min(nets), 2),
            "median_trade": round(sorted(nets)[len(nets) // 2], 2),
            "mean_trade": round(sum(nets) / len(nets), 2),
            "best_pct_of_total": round(max(nets) / total * 100, 1),
            "top2_pct_of_total": round(sum(nets[:2]) / total * 100, 1),
            "top3_pct_of_total": round(sum(nets[:3]) / total * 100, 1),
        }

    @staticmethod
    def monthly_stability(rows):
        by = {}
        for r in rows:
            by.setdefault(r["entry_date"][:7], []).append(r)
        out = {}
        for month in sorted(by):
            t = by[month]
            nets = [x["net_pnl"] for x in t]
            wins = sum(1 for x in nets if x > 0)
            gross_win = sum(x for x in nets if x > 0)
            gross_loss = -sum(x for x in nets if x <= 0)
            pf = round(gross_win / gross_loss, 3) if gross_loss > 0 else None
            out[month] = {
                "trades": len(t), "wins": wins, "losses": len(t) - wins,
                "net": round(sum(nets), 2), "pf": pf,
                "average_trade": round(sum(nets) / len(t), 2),
            }
        return out

    @staticmethod
    def vix_bands(rows):
        """Pre-defined descriptive VIX bands; do NOT optimize bins."""
        bands = [(16.0, 18.0), (18.0, 20.0), (20.0, 22.0), (22.0, 25.0)]
        out = {}
        for lo, hi in bands:
            t = [r for r in rows if r.get("vix_at_entry") is not None
                 and lo <= r["vix_at_entry"] < hi]
            out[f"{lo:g}-{hi:g}"] = {
                "trades": len(t),
                "wins": sum(1 for r in t if r["net_pnl"] > 0),
                "net": round(sum(r["net_pnl"] for r in t), 2),
            } if t else None
        return out

    @staticmethod
    def dow_expiry(rows):
        def wk(dstr):
            return dt.date.fromisoformat(dstr).strftime("%A")
        out = {"entry_weekday": {}, "dow_net": {}}
        for r in rows:
            wd = wk(r["entry_date"])
            out["entry_weekday"].setdefault(wd, 0)
            out["entry_weekday"][wd] += 1
            out["dow_net"].setdefault(wd, []).append(r["net_pnl"])
        out["days_to_expiry"] = sorted({int(r.get("days_held") or 0) for r in rows})
        return out

    @staticmethod
    def exit_analysis(rows):
        out = {}
        for reason in ("TARGET", "STOP", "TIME", "EXPIRY", "EOD"):
            t = [r for r in rows if r["reason"] == reason]
            if not t:
                continue
            nets = [r["net_pnl"] for r in t]
            out[reason] = {
                "count": len(t),
                "wins": sum(1 for x in nets if x > 0),
                "average_pnl": round(sum(nets) / len(t), 2),
                "mfe": round(sum(r["mfe"] for r in t) / len(t), 2),
                "mae": round(sum(r["mae"] for r in t) / len(t), 2),
                "average_hold": round(sum(r["days_held"] for r in t) / len(t), 2),
                "net": round(sum(nets), 2),
            }
        return out

    @staticmethod
    def cost_analysis(rows):
        return {
            "gross_pnl": round(sum(r["net_pnl"] + r["fees"] + r["slippage"] for r in rows), 2),
            "fees": round(sum(r["fees"] for r in rows), 2),
            "slippage": round(sum(r["slippage"] for r in rows), 2),
            "net_pnl": round(sum(r["net_pnl"] for r in rows), 2),
            "after_cost_vs_gross_pct": None,
        }

    @staticmethod
    def oos_split(rows, split="2026-04-01"):
        dev = [r for r in rows if r["entry_date"] < split]
        oos = [r for r in rows if r["entry_date"] >= split]

        def agg(t):
            if not t:
                return {"trades": 0, "wins": 0, "losses": 0, "net": 0.0, "win_rate": None, "pf": None}
            nets = [r["net_pnl"] for r in t]
            gw = sum(x for x in nets if x > 0)
            gl = -sum(x for x in nets if x <= 0)
            return {"trades": len(t), "wins": sum(1 for x in nets if x > 0),
                    "losses": sum(1 for x in nets if x <= 0), "net": round(sum(nets), 2),
                    "win_rate": round(sum(1 for x in nets if x > 0) / len(t) * 100, 1),
                    "pf": round(gw / gl, 3) if gl > 0 else None}
        return {"development": agg(dev), "out_of_sample": agg(oos)}

    @staticmethod
    def bootstrap(rows, n_boot=10000, seed=42):
        nets = [r["net_pnl"] for r in rows]
        rng = random.Random(seed)
        sums = []
        for _ in range(n_boot):
            sample = [rng.choice(nets) for _ in nets]
            sums.append(sum(sample))
        sums.sort()
        lo = sums[int(n_boot * 0.05)]
        hi = sums[int(n_boot * 0.95)]
        wins = [x for x in nets if x > 0]
        return {
            "n": len(nets),
            "mean_sum": round(sum(sums) / n_boot, 2),
            "ci90_low": round(lo, 2),
            "ci90_high": round(hi, 2),
            "pct_negative": round(sum(1 for s in sums if s < 0) / n_boot * 100, 1),
            "win_rate_est": round(len(wins) / len(nets) * 100, 1) if nets else None,
        }

    @staticmethod
    def drawdown(rows):
        eq = []
        e = 0.0
        for r in sorted(rows, key=lambda x: x["exit_date"]):
            e += r["net_pnl"]
            eq.append(e)
        peak = -1e18
        mdd = 0.0
        for x in eq:
            peak = max(peak, x)
            mdd = min(mdd, x - peak)
        nets = [r["net_pnl"] for r in rows]
        worst_seq = 0
        cur = 0
        for x in sorted(rows, key=lambda x: x["exit_date"]):
            cur = cur + 1 if x["net_pnl"] < 0 else 0
            worst_seq = max(worst_seq, cur)
        return {
            "max_drawdown": round(mdd, 2),
            "max_single_loss": round(min(nets), 2),
            "largest_consecutive_losses": worst_seq,
            "capital_utilization": round(max(r["max_risk_per_share"] or 0 for r in rows) * 75, 2),
            "equity": [round(x, 2) for x in eq],
        }

    # ------------------------------------------------------------------ report
    def fingerprints(self):
        return m.fingerprints(self.nifty, self.vix, self.fii, self.ml, self.snaps,
                              data_root=self.data_root)

    def run_all(self):
        trace = self.eligibility_trace()
        trades, rows = self.engine_trades()
        reconstructed = self.reconstruct_trades(rows, trace)

        statuses = {}
        for r in trace:
            statuses.setdefault(r["status"], 0)
            statuses[r["status"]] += 1
        observed = sum(1 for r in trace if r["regime"] == "RANGE_HV")
        eligible = [r for r in trace if r["status"] == "TRADE"]
        eligible_days = len(eligible)
        locked = statuses.get("POSITION_LOCKED", 0)

        return {
            "window": {"start": str(m.WINDOW_START), "end": str(m.WINDOW_END),
                       "days": len(self.window)},
            "trace": trace,
            "status_counts": statuses,
            "range_hv_observed_days": observed,
            "range_hv_vix_gate_days": sum(1 for r in trace
                                          if r["regime"] == "RANGE_HV"
                                          and r["vix"] is not None
                                          and VIX_MIN <= r["vix"] < VIX_MAX),
            "eligible_days": eligible_days,
            "position_locked_days": locked,
            "trades": reconstructed,
            "trade_count": len(reconstructed),
            "profit_concentration": self.profit_concentration(reconstructed),
            "monthly": self.monthly_stability(reconstructed),
            "vix_bands": self.vix_bands(reconstructed),
            "dow_expiry": self.dow_expiry(reconstructed),
            "exit_analysis": self.exit_analysis(reconstructed),
            "cost": self.cost_analysis(reconstructed),
            "oos": self.oos_split(reconstructed),
            "bootstrap": self.bootstrap(reconstructed),
            "drawdown": self.drawdown(reconstructed),
            "fingerprints": self.fingerprints(),
        }


if __name__ == "__main__":
    v = RangeHVValidator()
    report = v.run_all()
    print(json.dumps(report, indent=1, default=str))
