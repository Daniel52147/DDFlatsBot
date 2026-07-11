"""TradeSim unit tests — money logic, strategy, optimizer."""

from __future__ import annotations

import copy
import time
import unittest

import config
from learning.optimizer import StrategyOptimizer
from simulator.backtest import Backtester
from simulator.engine import SimulatorEngine
from simulator.price_walk import ohlc_prices, prices_for_tick
from simulator.strategy import StrategyBot


class TestEngineFeesAndCostBasis(unittest.TestCase):
    def setUp(self):
        self.engine = SimulatorEngine(initial_balance=1000.0)

    def test_buy_applies_fee_and_slippage(self):
        trade = self.engine.buy(100.0, 100.0, reason="test")
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertGreater(trade.fee, 0)
        self.assertEqual(trade.fee, 100.0 * config.FEE_RATE)
        self.assertLessEqual(self.engine.position.quote, 900.0)
        self.assertGreater(self.engine.position.base, 0)
        fill = trade.price
        expected_base = (100.0 - trade.fee) / fill
        self.assertAlmostEqual(self.engine.position.base, expected_base, places=6)

    def test_cost_basis_tracks_quote_spent(self):
        self.engine.buy(50.0, 200.0, reason="buy1")
        self.assertAlmostEqual(self.engine.position.cost_basis, 200.0)
        self.engine.buy(50.0, 100.0, reason="buy2")
        self.assertAlmostEqual(self.engine.position.cost_basis, 300.0)

    def test_avg_entry_price(self):
        self.engine.buy(100.0, 500.0, reason="buy")
        avg = self.engine.avg_entry_price()
        self.assertIsNotNone(avg)
        self.assertAlmostEqual(avg, 500.0 / self.engine.position.base, places=4)

    def test_sell_reduces_cost_basis_proportionally(self):
        self.engine.buy(100.0, 500.0, reason="buy")
        base = self.engine.position.base
        sell_amt = base * 0.5
        sold_frac = sell_amt / (base + sell_amt)
        self.engine.sell(110.0, sell_amt, reason="sell half")
        expected = 500.0 * (1 - sold_frac)
        self.assertAlmostEqual(self.engine.position.cost_basis, expected, places=2)

    def test_export_trades_no_default_cap(self):
        for i in range(60):
            self.engine.buy(100.0 + i, 10.0, reason=f"t{i}")
        exported = self.engine.export_trades()
        self.assertEqual(len(exported), 60)
        capped = self.engine.export_trades(limit=10)
        self.assertEqual(len(capped), 10)


class TestStopLossTakeProfit(unittest.TestCase):
    def _bot_with_position(self, entry_price: float = 100.0, amount: float = 500.0):
        engine = SimulatorEngine(initial_balance=1000.0)
        engine.buy(entry_price, amount, reason="setup")
        params = {
            **config.STRATEGY,
            "stop_loss_pct": 5.0,
            "stop_loss_fraction": 0.5,
            "stop_loss_cooldown_hours": 0,
            "take_profit_pct": 5.0,
            "take_profit_cost_pct": 5.0,
            "take_profit_fraction": 0.5,
            "take_profit_cooldown_hours": 0,
            "dca_interval_hours": 999,
        }
        bot = StrategyBot(engine, params=params)
        bot.last_stop_loss_ts = 0
        bot.last_take_profit_ts = 0
        return bot, engine

    def test_stop_loss_triggers_below_avg_entry(self):
        bot, engine = self._bot_with_position(100.0, 500.0)
        trade = bot.maybe_trade(94.0, sma=100.0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(trade.side, "sell")
        self.assertIn("STOP-LOSS", trade.reason)

    def test_take_profit_on_cost_basis(self):
        bot, engine = self._bot_with_position(100.0, 500.0)
        trade = bot.maybe_trade(106.0, sma=90.0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(trade.side, "sell")
        self.assertIn("TAKE-PROFIT", trade.reason)

    def test_stop_loss_before_take_profit(self):
        bot, engine = self._bot_with_position(100.0, 500.0)
        trade = bot.maybe_trade(90.0, sma=110.0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertIn("STOP-LOSS", trade.reason)


class TestOptimizer(unittest.TestCase):
    def test_apply_params_clamped(self):
        opt = StrategyOptimizer(config.STRATEGY.copy())
        p = opt.apply_params({"dca_amount": 9999.0, "dip_threshold_pct": -5.0})
        self.assertLessEqual(p["dca_amount"], opt.BOUNDS["dca_amount"][1])
        self.assertGreaterEqual(p["dip_threshold_pct"], opt.BOUNDS["dip_threshold_pct"][0])

    def test_tune_when_losing(self):
        opt = StrategyOptimizer(copy.deepcopy(config.STRATEGY))
        new_params, reason = opt.tune(vs_hold_pct=-2.0, trade_count=5, recent_trades=[])
        self.assertIn("обучение", reason.lower())
        self.assertNotEqual(new_params["dip_threshold_pct"], config.STRATEGY["dip_threshold_pct"])


class TestPriceWalk(unittest.TestCase):
    def test_ohlc_dedupes(self):
        c = {"open": 100, "low": 99, "high": 101, "close": 100}
        prices = ohlc_prices(c)
        self.assertEqual(prices[0], 100.0)
        self.assertEqual(prices[-1], 100.0)

    def test_candle_close_uses_ohlc(self):
        candle = {"open": 10, "low": 9, "high": 11, "close": 10.5}
        walk = prices_for_tick(10.5, candle)
        self.assertEqual(len(walk), 4)
        tick_only = prices_for_tick(10.5, None)
        self.assertEqual(tick_only, [10.5])


class TestBacktest(unittest.TestCase):
    def test_backtest_runs_on_synthetic_candles(self):
        candles = []
        price = 100.0
        for i in range(80):
            o = price
            h = price * 1.002
            l = price * 0.998
            c = price * (1 + (0.001 if i % 5 == 0 else -0.0005))
            candles.append({"time": i * 60, "open": o, "high": h, "low": l, "close": c, "volume": 1})
            price = c
        bt = Backtester(initial_balance=1000.0)
        result = bt.run(candles)
        self.assertEqual(result["candles"], 80)
        self.assertIn("pnl_pct", result)


if __name__ == "__main__":
    unittest.main()
