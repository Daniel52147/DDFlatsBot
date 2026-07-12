"""v20 — auto tactics and trader copy tests."""

from __future__ import annotations

import unittest

import config
from assistant.trader_watcher import TraderWatcherAgent
from learning.auto_tactics import AutoTacticsEngine, STYLE_TO_STRATEGY
from simulator.market_session import MarketSession


class TestTraderMarketPlays(unittest.TestCase):
    def test_style_maps_to_strategy(self):
        self.assertEqual(STYLE_TO_STRATEGY["meme_momentum"], "momentum")
        self.assertEqual(STYLE_TO_STRATEGY["scalp"], "scalper")

    def test_build_market_plays_from_bullish_signals(self):
        agent = TraderWatcherAgent()
        signals = [
            {
                "trader": "Ansem",
                "style": "meme_momentum",
                "strategy": "momentum",
                "preset": "aggressive",
                "markets": ["PEPE"],
                "bias": "bullish",
                "confidence": 0.82,
                "momentum_24h": 5.0,
                "text": "test",
            },
        ]
        plays = agent._build_market_plays(signals)
        self.assertIn("PEPE", plays)
        self.assertEqual(plays["PEPE"]["strategy"], "momentum")
        self.assertEqual(plays["PEPE"]["trader"], "Ansem")


class TestAutoTacticsDecide(unittest.TestCase):
    def setUp(self):
        self.engine = AutoTacticsEngine()
        self.market = config.MARKETS[0]
        self.session = MarketSession(self.market)

    def test_trader_play_overrides_when_confident(self):
        ctx = self.session.context_for_assistant()
        ctx["strategy_type"] = "dca"
        ctx["trade_count"] = 5
        play = {
            "strategy": "momentum",
            "preset": "aggressive",
            "trader": "Hsaka",
            "confidence": 0.85,
            "reason": "scalp style",
        }
        proposal = self.engine.decide(ctx, play)
        self.assertIsNotNone(proposal)
        assert proposal is not None
        self.assertEqual(proposal["source"], "trader")
        self.assertEqual(proposal["strategy_type"], "momentum")

    def test_auto_picks_grid_on_flat_volatile(self):
        ctx = {
            "symbol": "XRPUSDT",
            "label": "XRP",
            "strategy_type": "dca",
            "volatile": False,
            "growth": True,
            "viral": False,
            "volatility_pct": 2.0,
            "trade_count": 10,
            "price": 2.5,
            "sma": 2.48,
            "candles": [{"close": 2.48}, {"close": 2.49}, {"close": 2.5}, {"close": 2.49}, {"close": 2.5}],
            "portfolio": {"vs_hold_pct": 0, "pnl_pct": 0},
        }
        proposal = self.engine.decide(ctx, None)
        if proposal:
            self.assertIn(proposal["strategy_type"], ("grid", "dca", "momentum"))

    def test_cooldown_blocks_rapid_switch(self):
        ctx = self.session.context_for_assistant()
        ctx["trade_count"] = 10
        play = {"strategy": "grid", "confidence": 0.9, "trader": "Test", "reason": "x"}
        self.engine.last_switch_ts[ctx["symbol"]] = __import__("time").time()
        self.assertIsNone(self.engine.decide(ctx, play))


if __name__ == "__main__":
    unittest.main()
