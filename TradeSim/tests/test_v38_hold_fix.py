"""v38 — candle-based hold anchor fixes inflated vs Hold."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from simulator.engine import SimulatorEngine
from simulator.portfolio_benchmark import hold_anchor_price, portfolio_benchmark, sync_session_hold_benchmark


class TestHoldAnchorV38(unittest.TestCase):
    def test_prefers_candle_over_stale_start_price(self):
        session = MagicMock()
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine = SimulatorEngine(initial_balance=1000)
        session.engine.start_price = 200.0
        session.engine.trades.append(MagicMock(side="buy", price=95.0, ts=1.0))
        session.candles.all_candles.return_value = [{"close": 98.0, "time": 1}]
        price, anchor = hold_anchor_price(session)
        self.assertEqual(anchor, "candle_anchor")
        self.assertEqual(price, 98.0)

    def test_sync_updates_engine_snapshot(self):
        session = MagicMock()
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine = SimulatorEngine(initial_balance=1000)
        session.engine.start_price = 250.0
        session.engine.trades = []
        session.candles.all_candles.return_value = [{"close": 100.0, "time": 1}]
        sync_session_hold_benchmark(session)
        snap = session.engine.snapshot(100.0)
        self.assertAlmostEqual(snap["vs_hold_pct"], 0.0, places=1)

    def test_portfolio_hold_not_crashed_when_prices_flat(self):
        sessions = {}
        for symbol in ("BTCUSDT", "ETHUSDT"):
            session = MagicMock()
            session.feed.price = 100.0
            session.demo_price = 100.0
            session.engine = SimulatorEngine(initial_balance=5000)
            session.engine.start_price = 500.0
            session.engine.trades = []
            session.candles.all_candles.return_value = [{"close": 100.0, "time": 1}]
            sessions[symbol] = session
        bench = portfolio_benchmark(sessions)
        self.assertGreater(bench["hold_value"], 9000)
        self.assertLess(abs(bench["vs_hold_pct"]), 5)


if __name__ == "__main__":
    unittest.main()
