import unittest

from trading_bot.core.walk_forward_validation import (
    WalkForwardPolicy,
    build_empty_evidence,
    build_evidence_from_trades,
    build_rolling_windows,
    extract_trades,
    isolation_requirements,
    promotion_checklist,
    summarize_trades,
)


class WalkForwardValidationTests(unittest.TestCase):
    def test_build_rolling_windows_uses_train_test_step_policy(self):
        policy = WalkForwardPolicy(train_days=10, test_days=5, step_days=5)

        windows = build_rolling_windows("2026-01-01", "2026-02-01", policy)

        self.assertEqual(len(windows), 4)
        self.assertEqual(windows[0].train_start, "2026-01-01")
        self.assertEqual(windows[0].train_end, "2026-01-11")
        self.assertEqual(windows[0].test_start, "2026-01-11")
        self.assertEqual(windows[0].test_end, "2026-01-16")
        self.assertEqual(windows[1].train_start, "2026-01-06")

    def test_summarize_trades_exports_required_metrics_after_costs(self):
        policy = WalkForwardPolicy(fee_bps_per_side=10, slippage_bps_per_side=5)
        trades = [
            {"profit_abs": 12, "stake_amount": 100, "profit_ratio": 0.12},
            {"profit_abs": -5, "stake_amount": 100, "profit_ratio": -0.05},
            {"profit_abs": 8, "stake_amount": 100, "profit_ratio": 0.08},
        ]

        metrics = summarize_trades(trades, starting_equity=1000, policy=policy, benchmark_return_pct=1.0)

        # 0.30 USDT cost per 100 USDT round trip, applied to each trade.
        self.assertEqual(metrics["net_pnl_after_fees_slippage"], 14.1)
        self.assertEqual(metrics["trade_count"], 3)
        self.assertEqual(metrics["max_drawdown_abs"], 5.3)
        self.assertEqual(metrics["profit_factor"], 3.660377)
        self.assertEqual(metrics["win_rate"], 66.666667)
        self.assertIn("sharpe_per_trade", metrics)
        self.assertIn("sortino_per_trade", metrics)
        self.assertEqual(metrics["benchmark_relative_return_pct"], 0.41)

    def test_summarize_trades_accepts_generators(self):
        policy = WalkForwardPolicy()
        trades = ({"profit_abs": 1, "stake_amount": 100} for _ in range(2))

        metrics = summarize_trades(trades, starting_equity=1000, policy=policy)

        self.assertEqual(metrics["trade_count"], 2)

    def test_empty_evidence_contains_policy_checklist_gate_summary_and_isolation_requirements(self):
        policy = WalkForwardPolicy(train_days=10, test_days=5, step_days=5)

        evidence = build_empty_evidence("2026-01-01", "2026-02-01", policy)

        self.assertEqual(evidence["status"], "template_no_backtest_results_loaded")
        self.assertEqual(len(evidence["windows"]), 4)
        self.assertEqual(evidence["windows"][0]["test"]["minimum_trade_count"], policy.min_test_trades)
        self.assertEqual(evidence["promotion_gate_summary"]["status"], "insufficient_walk_forward_evidence")
        self.assertTrue(any(item["item"] == "side_by_side_dry_run" for item in promotion_checklist(policy)))
        required_isolation = isolation_requirements()
        self.assertTrue({"database", "logs", "api_port", "config", "dashboard_identity"}.issubset(required_isolation))

    def test_build_evidence_from_trades_populates_window_metrics_and_gate_status(self):
        policy = WalkForwardPolicy(
            train_days=10,
            test_days=5,
            step_days=5,
            min_train_trades=1,
            min_test_trades=1,
            min_total_test_trades_for_promotion=2,
        )
        trades = [
            {"close_date": "2026-01-02", "profit_abs": 10, "stake_amount": 100},
            {"close_date": "2026-01-12", "profit_abs": 5, "stake_amount": 100},
            {"close_date": "2026-01-07", "profit_abs": 7, "stake_amount": 100},
            {"close_date": "2026-01-17", "profit_abs": 6, "stake_amount": 100},
        ]

        evidence = build_evidence_from_trades(trades, start="2026-01-01", end="2026-01-21", policy=policy)

        self.assertEqual(len(evidence["windows"]), 2)
        self.assertEqual(evidence["windows"][0]["train"]["metrics"]["trade_count"], 2)
        self.assertEqual(evidence["windows"][0]["test"]["metrics"]["trade_count"], 1)
        self.assertEqual(evidence["promotion_gate_summary"]["aggregate_test_trades"], 2)
        self.assertEqual(evidence["status"], "eligible_for_side_by_side_dry_run")

    def test_insufficient_window_trades_fail_promotion(self):
        policy = WalkForwardPolicy(
            train_days=10,
            test_days=5,
            step_days=5,
            min_train_trades=2,
            min_test_trades=2,
            min_total_test_trades_for_promotion=2,
        )
        trades = [
            {"close_date": "2026-01-02", "profit_abs": 10, "stake_amount": 100},
            {"close_date": "2026-01-12", "profit_abs": 5, "stake_amount": 100},
        ]

        evidence = build_evidence_from_trades(trades, start="2026-01-01", end="2026-01-16", policy=policy)

        self.assertEqual(evidence["status"], "insufficient_walk_forward_evidence")
        self.assertFalse(evidence["windows"][0]["train"]["passed_minimum_trades"])
        self.assertFalse(evidence["windows"][0]["test"]["passed_minimum_trades"])
        self.assertFalse(evidence["promotion_gate_summary"]["train_windows_passed_min_trades"])
        self.assertFalse(evidence["promotion_gate_summary"]["test_windows_passed_min_trades"])

    def test_aggregate_trade_count_controls_promotion_decision(self):
        policy = WalkForwardPolicy(
            train_days=10,
            test_days=5,
            step_days=5,
            min_train_trades=1,
            min_test_trades=1,
            min_total_test_trades_for_promotion=3,
        )
        trades = [
            {"close_date": "2026-01-02", "profit_abs": 10, "stake_amount": 100},
            {"close_date": "2026-01-12", "profit_abs": 5, "stake_amount": 100},
        ]

        evidence = build_evidence_from_trades(trades, start="2026-01-01", end="2026-01-16", policy=policy)

        self.assertTrue(evidence["windows"][0]["train"]["passed_minimum_trades"])
        self.assertTrue(evidence["windows"][0]["test"]["passed_minimum_trades"])
        self.assertEqual(evidence["promotion_gate_summary"]["aggregate_test_trades"], 1)
        self.assertFalse(evidence["promotion_gate_summary"]["aggregate_test_trades_passed"])
        self.assertEqual(evidence["status"], "insufficient_walk_forward_evidence")

    def test_extract_trades_handles_common_json_shapes(self):
        payload = {"strategy": {"MyStrategy": {"trades": [{"profit_abs": 1}]}}}

        self.assertEqual(extract_trades(payload), [{"profit_abs": 1}])

    def test_extract_trades_handles_custom_bot_trade_log_sells(self):
        payload = {
            "trade_log": [
                {"time": "2026-05-01T00:00:00+00:00", "action": "BUY", "pnl": 99, "usdt": 10},
                {"time": "2026-05-02T00:00:00+00:00", "action": "SELL", "pnl": 1.5, "usdt": 11},
            ]
        }

        trades = extract_trades(payload)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["net_pnl"], 1.5)
        self.assertEqual(trades[0]["close_date"], "2026-05-02T00:00:00+00:00")
        self.assertEqual(trades[0]["stake_amount"], 11)

    def test_extract_trades_handles_custom_bot_trade_log_sells(self):
        payload = {
            "trade_log": [
                {"time": "2026-05-01T00:00:00+00:00", "action": "BUY", "pnl": 99, "usdt": 10},
                {"time": "2026-05-02T00:00:00+00:00", "action": "SELL", "pnl": 1.5, "usdt": 11},
            ]
        }

        trades = extract_trades(payload)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["net_pnl"], 1.5)
        self.assertEqual(trades[0]["close_date"], "2026-05-02T00:00:00+00:00")
        self.assertEqual(trades[0]["stake_amount"], 11)


if __name__ == "__main__":
    unittest.main()
