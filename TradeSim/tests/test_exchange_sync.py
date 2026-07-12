"""Exchange → paper sync tests."""

from __future__ import annotations

import unittest

from exchange.paper_sync import parse_binance_order
from simulator.engine import SimulatorEngine


class TestParseBinanceOrder(unittest.TestCase):
    def test_buy_with_fills(self):
        order = {
            "side": "BUY",
            "orderId": 99,
            "fills": [
                {"price": "100.0", "qty": "0.05", "commission": "0.01", "commissionAsset": "USDT"},
                {"price": "100.0", "qty": "0.05", "commission": "0.0001", "commissionAsset": "BTC"},
            ],
        }
        fill = parse_binance_order(order, "BTCUSDT")
        assert fill is not None
        self.assertEqual(fill["side"], "buy")
        self.assertAlmostEqual(fill["amount_base"], 0.0999, places=4)
        self.assertGreater(fill["amount_quote"], 0)

    def test_sell_executed_qty_fallback(self):
        order = {
            "side": "SELL",
            "executedQty": "0.1",
            "cummulativeQuoteQty": "6500",
        }
        fill = parse_binance_order(order, "BTCUSDT")
        assert fill is not None
        self.assertEqual(fill["side"], "sell")
        self.assertEqual(fill["amount_base"], 0.1)


class TestApplyExchangeFill(unittest.TestCase):
    def test_buy_updates_paper_without_double_fee(self):
        eng = SimulatorEngine(initial_balance=1000.0)
        trade = eng.apply_exchange_fill(
            "buy", price=100.0, amount_base=0.5, amount_quote=50.0, fee=0.05,
            reason="EXCHANGE TEST",
        )
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertAlmostEqual(eng.position.quote, 950.0)
        self.assertAlmostEqual(eng.position.base, 0.5)
        self.assertIn("EXCHANGE", trade.reason)

    def test_sell_updates_paper(self):
        eng = SimulatorEngine(initial_balance=1000.0)
        eng.apply_exchange_fill("buy", 100, 1.0, 100, 0, "setup")
        trade = eng.apply_exchange_fill("sell", 110, 0.5, 55, 0.05, "EXCHANGE SELL")
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(eng.position.base, 0.5)


if __name__ == "__main__":
    unittest.main()
