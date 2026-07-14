"""v53 — trailing / micro take-profit and stale loss exits."""

from __future__ import annotations

import time
import unittest

from simulator.engine import SimulatorEngine
from simulator.strategy import StrategyBot


class TestStrategySells(unittest.TestCase):
    def setUp(self):
        self.engine = SimulatorEngine(initial_balance=1000.0)
        self.bot = StrategyBot(self.engine, params={
            "micro_take_profit_pct": 3.0,
            "micro_take_profit_fraction": 0.12,
            "micro_take_profit_cooldown_hours": 0,
            "trailing_profit_pct": 3.0,
            "trailing_profit_min_pct": 2.0,
            "trailing_profit_fraction": 0.15,
            "trailing_profit_cooldown_hours": 0,
            "take_profit_pct": 99.0,
            "take_profit_cost_pct": 99.0,
            "dca_interval_hours": 999,
            "dip_threshold_pct": 99,
            "stop_loss_pct": 99,
            "stale_loss_pct": 99,
        })

    def test_micro_take_profit_sells_partial(self):
        self.engine.buy(100.0, 200.0, reason="seed")
        trade = self.bot.maybe_trade(104.0, 100.0)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, "sell")
        self.assertIn("MICRO-TP", trade.reason)

    def test_trailing_profit_after_pullback(self):
        self.engine.buy(100.0, 200.0, reason="seed")
        self.bot.maybe_trade(106.0, 100.0)
        self.bot.profit_high_water = 106.0
        trade = self.bot.maybe_trade(102.5, 100.0)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, "sell")
        self.assertIn("TRAIL-PROFIT", trade.reason)

    def test_stale_loss_after_long_drawdown(self):
        bot = StrategyBot(self.engine, params={
            "stale_loss_pct": 5.0,
            "stale_loss_hours": 0.0001,
            "stale_loss_fraction": 0.2,
            "stop_loss_pct": 99,
            "dca_interval_hours": 999,
            "dip_threshold_pct": 99,
            "take_profit_pct": 99,
            "micro_take_profit_pct": 99,
            "trailing_profit_pct": 99,
        })
        self.engine.buy(100.0, 300.0, reason="seed")
        bot.loss_since_ts = time.time() - 7200
        trade = bot.maybe_trade(92.0, 100.0)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, "sell")
        self.assertIn("STALE-LOSS", trade.reason)


if __name__ == "__main__":
    unittest.main()
