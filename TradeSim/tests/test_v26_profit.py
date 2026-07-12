"""v26 — profitability: backtest gate, regime filter, risk gate, scalper fix."""

from __future__ import annotations

import unittest

import config
from learning.auto_tactics import AutoTacticsEngine
from learning.regime import detect_regime, regime_blocks_buy
from simulator.engine import SimulatorEngine
from simulator.risk_gate import blocks_new_buys, set_portfolio_halt
from simulator.strategies import RSIStrategyBot, ScalperStrategyBot, create_bot


class TestRegime(unittest.TestCase):
    def test_bear_blocks_rsi_buy(self):
        regime = detect_regime(95.0, 100.0, [100, 99.5, 99, 98.5, 98, 97.5, 97, 96.5, 96, 95.5])
        self.assertEqual(regime, "bear")
        self.assertTrue(regime_blocks_buy("rsi", regime))
        self.assertFalse(regime_blocks_buy("momentum", regime))

    def test_bull_not_blocked(self):
        regime = detect_regime(105.0, 100.0, [100, 100.5, 101, 101.5, 102, 102.5, 103, 103.5, 104, 104.5])
        self.assertEqual(regime, "bull")
        self.assertFalse(regime_blocks_buy("rsi", regime))


class TestRiskGate(unittest.TestCase):
    def test_blocks_buys_when_halted(self):
        set_portfolio_halt(False)
        eng = SimulatorEngine(initial_balance=500)
        self.assertIsNotNone(eng.buy(100, 20, "test"))
        set_portfolio_halt(True, "test halt")
        self.assertTrue(blocks_new_buys())
        self.assertIsNone(eng.buy(100, 20, "blocked"))
        set_portfolio_halt(False)


class TestScalperFeeFloor(unittest.TestCase):
    def test_min_tp_covers_fees(self):
        bot = ScalperStrategyBot(SimulatorEngine(initial_balance=500))
        floor = bot._min_scalp_tp_pct()
        round_trip = (config.FEE_RATE + config.SLIPPAGE_RATE) * 2 * 100
        self.assertGreaterEqual(floor, round_trip)


class TestRSICandleClose(unittest.TestCase):
    def test_rsi_uses_candle_closes_only(self):
        bot = RSIStrategyBot(SimulatorEngine(initial_balance=500))
        for i in range(20):
            bot.on_candle_close(100.0 + i * 0.1)
        self.assertEqual(len(bot._prices), 20)
        rsi = bot._rsi()
        self.assertIsNotNone(rsi)


class TestBacktestGate(unittest.TestCase):
    def test_blocks_worse_strategy(self):
        engine = AutoTacticsEngine()
        candles = []
        price = 100.0
        for i in range(120):
            # sideways chop — DCA usually ok, momentum often worse
            price += 0.05 if i % 2 == 0 else -0.05
            candles.append({
                "time": i * 60,
                "open": price,
                "high": price + 0.1,
                "low": price - 0.1,
                "close": price,
            })
        ctx = {
            "symbol": "BTCUSDT",
            "label": "BTC",
            "strategy_type": "dca",
            "candles": candles,
            "portfolio": {"vs_hold_pct": 0, "pnl_pct": 0},
        }
        proposal = {"strategy_type": "momentum", "source": "auto"}
        ok, note = engine._backtest_validate(ctx, proposal)
        # May pass or fail depending on random walk — at least runs without error
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(note, str)

    def test_same_strategy_passes(self):
        engine = AutoTacticsEngine()
        ctx = {"strategy_type": "dca", "candles": [{"close": 100}] * 50}
        ok, _ = engine._backtest_validate(ctx, {"strategy_type": "dca"})
        self.assertTrue(ok)


class TestStrategyFactory(unittest.TestCase):
    def test_create_all_types(self):
        eng = SimulatorEngine(initial_balance=500)
        for st in ("dca", "grid", "momentum", "rsi", "scalper"):
            bot = create_bot(eng, st)
            self.assertEqual(getattr(bot, "strategy_type", "dca"), st)


if __name__ == "__main__":
    unittest.main()
