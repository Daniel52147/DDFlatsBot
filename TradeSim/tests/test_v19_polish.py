"""v19 polish tests — FeedHub dedupe, switch_strategy, brain boost."""

from __future__ import annotations

import unittest

from simulator.engine import SimulatorEngine
from simulator.feed_hub import FeedHub
from simulator.strategies import create_bot, default_params
from simulator.market_session import MarketSession
import config


class _FakeFeed:
    symbol = "BTCUSDT"
    price = 100.0
    last_update = 0.0
    source = "test"

    async def _set_price(self, price, source):
        self.price = price
        self.source = source

    async def _notify(self, price, ts):
        pass


class TestFeedHubDedupe(unittest.TestCase):
    def test_register_same_feed_once(self):
        hub = FeedHub(["BTCUSDT"])
        feed = _FakeFeed()
        self.assertTrue(hub.register("BTCUSDT", feed))
        self.assertFalse(hub.register("BTCUSDT", feed))
        self.assertEqual(len(hub._feeds["BTCUSDT"]), 1)

    def test_ensure_symbol_no_duplicate_list(self):
        async def _run():
            hub = FeedHub(["BTCUSDT"])
            feed = _FakeFeed()
            await hub.ensure_symbol("BTCUSDT", feed)
            await hub.ensure_symbol("BTCUSDT", feed)
            self.assertEqual(len(hub._feeds["BTCUSDT"]), 1)
        import asyncio
        asyncio.run(_run())


class TestSwitchStrategy(unittest.TestCase):
    def test_switch_uses_default_params_not_stale_grid_keys(self):
        market = next(m for m in config.MARKETS if m["symbol"] == "BTCUSDT")
        session = MarketSession(market)
        session.switch_strategy("grid")
        grid_keys = set(default_params("grid").keys())
        bot_keys = set(session.bot.get_params().keys())
        self.assertIn("grid_spacing_pct", bot_keys)
        session.switch_strategy("momentum")
        params = session.bot.get_params()
        self.assertIn("breakout_pct", params)
        self.assertNotIn("grid_spacing_pct", params)

    def test_momentum_state_not_from_dca_base(self):
        eng = SimulatorEngine(initial_balance=500.0)
        bot = create_bot(eng, "momentum")
        bot.high_water = 120.0
        bot.in_trend = True
        state = bot.export_state()
        bot2 = create_bot(eng, "momentum")
        bot2.import_state(state)
        self.assertTrue(bot2.in_trend)
        self.assertEqual(bot2.high_water, 120.0)


class TestBrainBoostReturn(unittest.TestCase):
    def test_learning_boost_returns_symbols(self):
        from assistant.coordinator import CentralBrain
        market = config.MARKETS[0]
        session = MarketSession(market)
        session.strategy_type = "dca"
        sessions = {market["symbol"]: session}
        ctx = [{
            "symbol": market["symbol"],
            "portfolio": {"vs_hold_pct": -2.0, "pnl_pct": -1.0},
            "volatile": True,
            "volatility_pct": 12,
            "trade_stats": {"tp": 0, "buy": 5, "spike": 0},
        }]
        brain = CentralBrain()
        updated = brain.apply_learning_boost(sessions, ctx)
        self.assertIn(market["symbol"], updated)


if __name__ == "__main__":
    unittest.main()
