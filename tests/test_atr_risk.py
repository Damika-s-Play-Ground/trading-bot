import math
import unittest

from trading_bot.core.atr_risk import (
    atr_percent,
    calculate_atr,
    normalize_position_size,
    resolve_atr_exit_profile,
)


class AtrRiskTests(unittest.TestCase):
    def test_calculate_atr_uses_true_range(self):
        candles = [
            {"high": 105, "low": 95, "close": 100},
            {"high": 112, "low": 101, "close": 110},
            {"high": 113, "low": 107, "close": 108},
        ]
        atr = calculate_atr(candles, period=3)
        self.assertTrue(math.isclose(atr, (10.0 + 12.0 + 6.0) / 3.0, rel_tol=1e-6))

    def test_calculate_atr_keeps_prev_close_at_window_boundary(self):
        candles = [
            {"high": 101, "low": 99, "close": 100},
            {"high": 111, "low": 109, "close": 110},
            {"high": 116, "low": 114, "close": 115},
        ]
        atr = calculate_atr(candles, period=2)
        self.assertTrue(math.isclose(atr, (11.0 + 6.0) / 2.0, rel_tol=1e-6))

    def test_resolve_atr_exit_profile_prefers_atr_floor_over_tight_fixed_levels(self):
        profile = resolve_atr_exit_profile(
            price=100.0,
            atr_value=3.0,
            settings={
                "stop_atr_multiple": 2.0,
                "take_profit_atr_multiple": 3.0,
                "trailing_activation_atr_multiple": 1.5,
                "trailing_distance_atr_multiple": 1.0,
                "min_stop_loss_pct": 2.0,
                "max_stop_loss_pct": 12.0,
                "min_take_profit_pct": 4.0,
                "max_take_profit_pct": 20.0,
                "min_trailing_activation_pct": 2.0,
                "max_trailing_activation_pct": 12.0,
                "min_trailing_distance_pct": 1.0,
                "max_trailing_distance_pct": 8.0,
            },
            fixed_stop_loss_pct=-4.0,
            fixed_take_profit_pct=5.0,
            fixed_trailing_activation_pct=4.0,
            fixed_trailing_distance_pct=2.0,
        )
        self.assertAlmostEqual(profile["atr_pct"], 3.0, places=6)
        self.assertAlmostEqual(profile["stop_loss_pct"], -6.0, places=6)
        self.assertAlmostEqual(profile["take_profit_pct"], 9.0, places=6)
        self.assertAlmostEqual(profile["trailing_activation_pct"], 4.5, places=6)
        self.assertAlmostEqual(profile["trailing_distance_pct"], 3.0, places=6)

    def test_normalize_position_size_shrinks_when_atr_widens(self):
        settings = {
            "risk_per_trade_pct": 1.0,
            "stop_atr_multiple": 2.0,
            "min_stop_loss_pct": 2.0,
            "max_stop_loss_pct": 12.0,
            "min_position_multiplier": 0.5,
            "max_position_multiplier": 2.0,
        }
        calm = normalize_position_size(
            target_capital=1000.0,
            base_notional=10.0,
            atr_pct_value=1.0,
            settings=settings,
        )
        volatile = normalize_position_size(
            target_capital=1000.0,
            base_notional=10.0,
            atr_pct_value=5.0,
            settings=settings,
        )
        self.assertGreater(calm, volatile)
        self.assertAlmostEqual(calm, 20.0, places=6)
        self.assertAlmostEqual(volatile, 10.0, places=6)

    def test_atr_percent_handles_invalid_price(self):
        self.assertEqual(atr_percent(5.0, 0.0), 0.0)
        self.assertEqual(atr_percent(5.0, -1.0), 0.0)


if __name__ == "__main__":
    unittest.main()
