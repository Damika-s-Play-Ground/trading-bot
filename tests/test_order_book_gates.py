import unittest

from trading_bot.core.order_book_gates import evaluate_entry_gate_from_book, estimate_market_buy_slippage


class OrderBookGateTests(unittest.TestCase):
    def test_estimate_market_buy_slippage_uses_multiple_levels(self):
        asks = [(100.0, 0.05), (100.2, 0.10)]
        result = estimate_market_buy_slippage(asks, 10.0)
        self.assertTrue(result["filled"])
        self.assertGreater(result["avg_price"], 100.0)
        self.assertAlmostEqual(result["filled_notional_usdt"], 10.0, places=6)

    def test_gate_rejects_wide_spread(self):
        book = {
            "bids": [["99", "5"]],
            "asks": [["101", "5"]],
        }
        gate = evaluate_entry_gate_from_book("TEST", book, 5.0, settings={"max_spread_pct": 0.5})
        self.assertFalse(gate["ok"])
        self.assertIn("wide_spread", gate["reasons"])

    def test_gate_rejects_thin_depth_and_high_slippage(self):
        book = {
            "bids": [["100", "0.05"], ["99.9", "0.05"]],
            "asks": [["100.1", "0.01"], ["101.5", "0.02"], ["103.0", "0.02"]],
        }
        gate = evaluate_entry_gate_from_book(
            "TEST",
            book,
            5.0,
            settings={
                "max_spread_pct": 1.0,
                "max_slippage_pct": 0.1,
                "min_depth_multiple": 20.0,
                "depth_window_pct": 0.4,
            },
        )
        self.assertFalse(gate["ok"])
        self.assertIn("high_slippage", gate["reasons"])
        self.assertIn("thin_depth", gate["reasons"])

    def test_gate_accepts_liquid_book(self):
        book = {
            "bids": [["100.0", "20"], ["99.9", "20"]],
            "asks": [["100.05", "20"], ["100.06", "20"]],
        }
        gate = evaluate_entry_gate_from_book("TEST", book, 5.0, settings={})
        self.assertTrue(gate["ok"])
        self.assertEqual(gate["reasons"], [])


if __name__ == "__main__":
    unittest.main()
