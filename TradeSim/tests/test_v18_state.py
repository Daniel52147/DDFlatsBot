"""v18 — strategy state persistence and shadow promote keys."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import config
from learning.logger import LearningLogger
from simulator.engine import SimulatorEngine
from simulator.shadow_lab import _PROMOTE_KEYS
from simulator.strategies import create_bot


class TestStrategyStatePersistence(unittest.TestCase):
    def test_grid_state_roundtrip(self):
        eng = SimulatorEngine(initial_balance=500.0)
        bot = create_bot(eng, "grid")
        bot._last_buy_level = 3
        bot._last_sell_level = 2
        bot._prices = []  # grid doesn't have this
        state = bot.export_state()
        bot2 = create_bot(eng, "grid")
        bot2.import_state(state)
        self.assertEqual(bot2._last_buy_level, 3)
        self.assertEqual(bot2._last_sell_level, 2)

    def test_rsi_prices_persist(self):
        eng = SimulatorEngine(initial_balance=500.0)
        bot = create_bot(eng, "rsi")
        for p in [100, 101, 99, 98, 102]:
            bot.maybe_trade(p, 100.0)
        state = bot.export_state()
        bot2 = create_bot(eng, "rsi")
        bot2.import_state(state)
        self.assertEqual(len(bot2._prices), len(bot._prices))

    def test_scalper_ticks_persist(self):
        eng = SimulatorEngine(initial_balance=500.0)
        bot = create_bot(eng, "scalper")
        bot.maybe_trade(100.0, 100.0)
        bot.maybe_trade(99.5, 99.0)
        state = bot.export_state()
        self.assertGreater(state["strategy"]["ticks"], 0)
        bot2 = create_bot(eng, "scalper")
        bot2.import_state(state)
        self.assertEqual(bot2._ticks, state["strategy"]["ticks"])

    def test_logger_bot_state_column(self):
        async def _run():
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "t.db"
                log = LearningLogger(db)
                await log.init()
                await log.save_session("BTCUSDT", {
                    "quote": 500, "base": 0.01, "trade_counter": 1,
                    "start_balance": 500, "start_ts": 1.0,
                    "bot_params": {"dca_amount": 20},
                    "last_dca_ts": 0, "last_take_profit_ts": 0,
                    "bot_enabled": True, "trades": [],
                    "bot_state": {"strategy": {"last_buy_level": 5}},
                    "strategy_type": "grid",
                })
                loaded = await log.load_session("BTCUSDT")
                self.assertEqual(loaded["bot_state"]["strategy"]["last_buy_level"], 5)
        import asyncio
        asyncio.run(_run())


class TestShadowPromoteKeys(unittest.TestCase):
    def test_all_strategies_have_promote_keys(self):
        for st in ("dca", "grid", "momentum", "rsi", "scalper"):
            self.assertIn(st, _PROMOTE_KEYS)
            self.assertGreater(len(_PROMOTE_KEYS[st]), 2)


if __name__ == "__main__":
    unittest.main()
