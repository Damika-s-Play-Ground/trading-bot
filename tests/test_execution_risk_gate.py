from datetime import datetime, timedelta, timezone
import unittest

from trading_bot.core.execution_risk_gate import (
    ExecutionRiskConfig, ExecutionRiskState, REASON_BUY_DISABLED, REASON_COOLDOWN,
    REASON_DAILY_LOSS_LOCK, REASON_EMPTY_BOOK, REASON_HIGH_SLIPPAGE, REASON_MAX_EXPOSURE,
    REASON_PORTFOLIO_DRAWDOWN_LOCK, REASON_STALE_BOOK, REASON_THIN_DEPTH,
    REASON_UNVERIFIABLE_BOOK, REASON_WIDE_SPREAD, evaluate_execution_gate,
)


class ExecutionRiskGateTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 6, 12, 12, 0, tzinfo=timezone.utc)
        self.config = ExecutionRiskConfig(max_spread_pct=0.5, max_slippage_pct=0.2, min_near_touch_depth_multiple=5.0, near_touch_depth_window_pct=0.5, max_order_book_age_seconds=10.0, max_daily_loss_pct=3.0, max_portfolio_drawdown_pct=12.0, max_single_coin_exposure_pct=20.0)

    def liquid_book(self):
        return {"timestamp": self.now.timestamp(), "bids": [["99.98", "20"], ["99.95", "20"]], "asks": [["100.02", "20"], ["100.05", "20"]]}

    def test_wide_spread_denies_buy(self):
        book = {"timestamp": self.now.timestamp(), "bids": [["99", "10"]], "asks": [["101", "10"]]}
        decision = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=book, config=self.config, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertIn(REASON_WIDE_SPREAD, decision.reasons)

    def test_thin_depth_denies_buy(self):
        book = {"timestamp": self.now.timestamp(), "bids": [["100", "1"]], "asks": [["100.02", "0.1"]]}
        decision = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=book, config=self.config, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertIn(REASON_THIN_DEPTH, decision.reasons)

    def test_stale_empty_and_timestampless_books_are_machine_readable(self):
        stale_book = {"timestamp": (self.now - timedelta(seconds=30)).timestamp(), "bids": [["100", "10"]], "asks": [["100.01", "10"]]}
        timestampless_book = {"bids": [["100", "10"]], "asks": [["100.01", "10"]]}
        stale = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=stale_book, config=self.config, now=self.now)
        timestampless = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=timestampless_book, config=self.config, now=self.now)
        empty = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book={"timestamp": self.now.timestamp(), "bids": [], "asks": []}, config=self.config, now=self.now)
        self.assertEqual(stale.reason, REASON_STALE_BOOK)
        self.assertEqual(timestampless.reason, REASON_UNVERIFIABLE_BOOK)
        self.assertEqual(empty.reason, REASON_EMPTY_BOOK)

    def test_timestampless_book_can_use_trusted_fetch_timestamp(self):
        timestampless_book = {"bids": [["100", "10"]], "asks": [["100.01", "10"]]}
        decision = evaluate_execution_gate(
            action="buy",
            symbol="TEST",
            trade_notional_usdt=10,
            order_book=timestampless_book,
            config=self.config,
            now=self.now,
            trusted_fetch_timestamp=self.now,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, ())
        self.assertEqual(decision.metrics["order_book_timestamp_source"], "trusted_fetch_timestamp")

    def test_timestampless_book_with_stale_trusted_fetch_timestamp_denies_buy(self):
        timestampless_book = {"bids": [["100", "10"]], "asks": [["100.01", "10"]]}
        decision = evaluate_execution_gate(
            action="buy",
            symbol="TEST",
            trade_notional_usdt=10,
            order_book=timestampless_book,
            config=self.config,
            now=self.now,
            trusted_fetch_timestamp=self.now - timedelta(seconds=30),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, REASON_STALE_BOOK)

    def test_multi_level_slippage_denies_buy(self):
        book = {"timestamp": self.now.timestamp(), "bids": [["99.99", "50"]], "asks": [["100", "0.02"], ["102", "0.20"], ["103", "2"]]}
        decision = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=book, config=self.config, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertIn(REASON_HIGH_SLIPPAGE, decision.reasons)
        self.assertGreater(decision.metrics["avg_fill_price"], 100.0)

    def test_active_cooldown_denies_buy(self):
        state = ExecutionRiskState(cooldown_pairs=("TEST",), portfolio_total_value_usdt=1000)
        decision = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=self.liquid_book(), config=self.config, state=state, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertIn(REASON_COOLDOWN, decision.reasons)

    def test_active_loss_drawdown_and_projected_exposure_locks_deny_buy(self):
        state = ExecutionRiskState(daily_loss_pct=3.5, portfolio_drawdown_pct=12.1, portfolio_total_value_usdt=1000, coin_exposure_pct={"TEST": 19.9})
        decision = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=self.liquid_book(), config=self.config, state=state, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertIn(REASON_DAILY_LOSS_LOCK, decision.reasons)
        self.assertIn(REASON_PORTFOLIO_DRAWDOWN_LOCK, decision.reasons)
        self.assertIn(REASON_MAX_EXPOSURE, decision.reasons)
        self.assertGreaterEqual(decision.metrics["projected_coin_exposure_pct"], 20.0)

    def test_projected_exposure_uses_normalized_state_symbol(self):
        state = ExecutionRiskState(portfolio_total_value_usdt=1000, coin_exposure_pct={"TESTUSDT": 19.9})
        decision = evaluate_execution_gate(action="buy", symbol="TEST/USDT", trade_notional_usdt=10, order_book=self.liquid_book(), config=self.config, state=state, now=self.now)
        self.assertFalse(decision.allowed)
        self.assertIn(REASON_MAX_EXPOSURE, decision.reasons)
        self.assertEqual(decision.metrics["current_coin_exposure_pct"], 19.9)
        self.assertGreaterEqual(decision.metrics["projected_coin_exposure_pct"], 20.0)

    def test_exit_and_state_save_allowed_while_buy_disabled(self):
        state = ExecutionRiskState(buy_disabled=True, daily_loss_pct=99, portfolio_drawdown_pct=99, portfolio_total_value_usdt=100, coin_exposure_pct={"TEST": 99}, cooldown_pairs=("TEST",))
        buy = evaluate_execution_gate(action="buy", symbol="TEST", trade_notional_usdt=10, order_book=self.liquid_book(), config=self.config, state=state, now=self.now)
        sell = evaluate_execution_gate(action="sell", symbol="TEST", trade_notional_usdt=10, order_book=None, config=self.config, state=state, now=self.now)
        save = evaluate_execution_gate(action="state_save", symbol="TEST", trade_notional_usdt=0, order_book=None, config=self.config, state=state, now=self.now)
        self.assertFalse(buy.allowed)
        self.assertIn(REASON_BUY_DISABLED, buy.reasons)
        self.assertTrue(sell.allowed)
        self.assertTrue(save.allowed)


if __name__ == "__main__":
    unittest.main()
