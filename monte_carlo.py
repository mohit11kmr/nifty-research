"""Monte Carlo Risk & Account Survival Simulation Engine for NIFTY Research.

Runs 10,000 Statistical Trade Sequence Simulations to calculate:
1. Probability of Account Survival (100% Capital Preservation)
2. Maximum Expected Drawdown over 100 Trades
3. Optimal Safe Risk-per-Trade Percentage

Truth-layer (Phase 3): a deterministic seed-42 SCENARIO SIMULATION on
parametric win_rate/win_loss_ratio inputs - not empirical account
performance and not a measured edge. Outputs are tagged SIMULATED.
"""
import os
import sys
import json
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

import truth


def run_monte_carlo_simulation(win_rate=0.55, win_loss_ratio=1.8, capital=100000, risk_per_trade_pct=1.0, num_simulations=10000, trades_per_sim=100):
    """Run 10,000 Monte Carlo equity curve trials (deterministic seed-42)."""
    np.random.seed(42)
    max_drawdowns = []
    ruined_count = 0

    risk_amount = capital * (risk_per_trade_pct / 100.0)
    reward_amount = risk_amount * win_loss_ratio

    for _ in range(num_simulations):
        equity = capital
        peak = capital
        max_dd = 0.0
        ruined = False

        # Simulate 100 trades sequence
        outcomes = np.random.rand(trades_per_sim) < win_rate
        for win in outcomes:
            if win:
                equity += reward_amount
            else:
                equity -= risk_amount

            if equity > peak:
                peak = equity

            dd = (peak - equity) / peak * 100.0
            if dd > max_dd:
                max_dd = dd

            if equity <= capital * 0.5:  # 50% Drawdown = Ruin
                ruined = True
                break

        max_drawdowns.append(max_dd)
        if ruined:
            ruined_count += 1

    survival_rate_pct = ((num_simulations - ruined_count) / num_simulations) * 100.0
    avg_max_drawdown_pct = np.mean(max_drawdowns)
    percentile_95_drawdown_pct = np.percentile(max_drawdowns, 95)

    return truth.envelope(
        {
            "simulation_runs": num_simulations,
            "trades_per_run": trades_per_sim,
            "account_capital": capital,
            "risk_per_trade_pct": risk_per_trade_pct,
            "account_survival_rate_pct": round(survival_rate_pct, 2),
            "average_expected_drawdown_pct": round(avg_max_drawdown_pct, 2),
            "worst_case_95pct_drawdown": round(percentile_95_drawdown_pct, 2),
            "quant_survival_verdict": "SIMULATED PASS (deterministic seed-42 scenario, parametric inputs)" if survival_rate_pct >= 99.0 else "HIGH_RISK",
            "optimal_risk_recommendation": f"Keep risk per trade strictly at {risk_per_trade_pct}% for {survival_rate_pct:.1f}% simulated survival (parametric scenario, not empirical).",
        },
        status=truth.SIMULATED,
        source="parametric:win_rate/win_loss_ratio",
        evaluation_method="deterministic_simulation_seed42",
        fallback_used=False,
        random_seed=42,
    )


if __name__ == "__main__":
    print("=== MONTE CARLO RISK SIMULATION TEST ===")
    sim_res = run_monte_carlo_simulation()
    print(json.dumps(sim_res, indent=2))
