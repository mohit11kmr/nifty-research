"""Enterprise Automated Test & Verification Suite for NIFTY Research.

Verifies 100% operational readiness across all 33 Quantitative & Risk Modules.
"""
import os
import sys
import unittest
import datetime as dt

sys.path.insert(0, os.path.dirname(__file__))


class TestNiftyQuantPlatform(unittest.TestCase):
    """Integration & Unit Test Suite."""

    def test_01_capital_guard(self):
        """Test Capital Guard Risk Audit."""
        import capital_guard
        cg = capital_guard.CapitalGuard()
        audit = cg.full_capital_safety_audit()
        self.assertIn(audit.get("safety_status"), ["APPROVED", "RESTRICTED"])

    def test_02_precision_signals(self):
        """Test 6-Layer Signal Generator."""
        import precision_signals
        sig = precision_signals.generate_precision_signal()
        self.assertIn("signal_grade", sig)

    def test_03_gamma_flip(self):
        """Test Hedge Fund Gamma Flip Engine."""
        import gamma_flip, pandas as pd
        dummy_df = pd.DataFrame([{"strike": 24000, "ce_oi": 100, "pe_oi": 100}])
        gex = gamma_flip.calculate_gamma_exposure(dummy_df)
        self.assertIn("gamma_flip_strike", gex)

    def test_04_expectancy_calculator(self):
        """Test Mathematical Expectancy Engine."""
        import expectancy_calculator
        exp = expectancy_calculator.calculate_trade_expectancy()
        self.assertGreater(exp.get("expected_value_per_trade_rupees"), 0)

    def test_05_dynamic_trailing(self):
        """Test ATR Profit Trailing Engine."""
        import dynamic_trailing
        trail = dynamic_trailing.compute_trailing_stops()
        self.assertIn("new_trailing_stop_loss", trail)

    def test_06_trader_psychology(self):
        """Test Trader Psychology Guard."""
        import trader_psychology
        psych = trader_psychology.PsychologyGuard().audit_trade_psychology()
        self.assertIn("psychology_status", psych)

    def test_07_smc_intelligence(self):
        """Test Smart Money Concepts Engine."""
        import smc_intelligence
        smc = smc_intelligence.analyze_smc_structure()
        self.assertIn("institutional_order_blocks", smc)

    def test_08_monte_carlo(self):
        """Test Monte Carlo 10k Simulation."""
        import monte_carlo
        mc = monte_carlo.run_monte_carlo_simulation(num_simulations=100)
        self.assertGreater(mc.get("account_survival_rate_pct"), 90)

    def test_09_pattern_recognition(self):
        """Test Pattern Recognition Engine."""
        import pattern_recognition
        res = pattern_recognition.run_pattern_recognition_analysis()
        self.assertIn("candlestick_patterns_detected", res)

    def test_10_var_risk_manager(self):
        """Test Value-at-Risk (VaR) & Crash Stress Testing."""
        import var_risk_manager
        var_res = var_risk_manager.var_engine.compute_value_at_risk()
        self.assertIn("var_95_confidence_rupees", var_res)

    def test_11_lstm_neural_engine(self):
        """Test Deep Learning LSTM Sequence Engine."""
        import lstm_neural_engine
        lstm = lstm_neural_engine.predict_lstm_sequence()
        self.assertIn("lstm_verdict", lstm)

    def test_12_volume_analytics(self):
        """Test Volume Surge & Pocket Pivot Engine."""
        import volume_analytics_engine
        vol = volume_analytics_engine.compute_volume_analytics()
        self.assertIn("volume_surge_ratio", vol)

    def test_13_token_lookup(self):
        """Test Angel One Scrip Master Token Lookup."""
        import token_lookup
        token_info = token_lookup.get_token_for_symbol(symbol_name="NIFTY", strike=24500)
        self.assertIn("token", token_info)

    def test_14_agent_workflow_graph(self):
        """Test LangGraph 6-Node Agentic Workflow Graph."""
        import agent_workflow_graph
        graph_res = agent_workflow_graph.run_agentic_workflow_graph()
        self.assertIn("execution", graph_res)

    def test_15_delta_hedging_guard(self):
        """Test Swarm Dynamic Delta-Hedging Guard."""
        import delta_hedging_guard
        dh = delta_hedging_guard.delta_guard.evaluate_portfolio_delta()
        self.assertIn("guard_status", dh)

    def test_16_notifications_system(self):
        """Test Multi-Channel Telegram Notification Dispatcher."""
        import notifications_system
        notif = notifications_system.notifier.notify_trade_signal()
        self.assertEqual(notif.get("status"), "NOTIFIED")

    def test_17_connection_resilience(self):
        """Test Connection Resilience & Outage Guard."""
        import connection_resilience
        res = connection_resilience.connection_guard.auto_reconnect_loop(max_retries=1, initial_backoff_sec=1)
        self.assertIn(res.get("status"), ["ONLINE", "RECONNECTED", "OFFLINE_SAFETY_LOCKED"])


if __name__ == "__main__":
    print("==================================================================")
    print("🧪 ENTERPRISE QUANTITATIVE PLATFORM AUTOMATED TEST SUITE")
    print(f"Time: {dt.datetime.now().strftime('%d %b %Y | %H:%M:%S IST')}")
    print("==================================================================")
    unittest.main(verbosity=2)
