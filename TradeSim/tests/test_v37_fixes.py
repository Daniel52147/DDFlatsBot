"""v37 — honest benchmark, week prep, auto testnet."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from simulator.portfolio_benchmark import hold_anchor_price, portfolio_benchmark


class TestPortfolioBenchmark(unittest.TestCase):
    def test_candle_anchor_when_no_trades(self):
        session = MagicMock()
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine.trades = []
        session.engine.start_price = 200.0
        session.candles.all_candles.return_value = [{"close": 90.0, "time": 1}]
        price, anchor = hold_anchor_price(session)
        self.assertEqual(anchor, "candle_anchor")
        self.assertEqual(price, 90.0)

    def test_misleading_flag_when_cash_and_high_vs_hold(self):
        sessions = {}
        for symbol, start_price, price in [
            ("BTCUSDT", 100000.0, 64000.0),
            ("ETHUSDT", 5000.0, 2400.0),
        ]:
            session = MagicMock()
            session.feed.price = price
            session.demo_price = price
            session.engine.start_balance = 5000
            session.engine.trades = []
            session.engine.start_price = start_price
            session.engine.snapshot.return_value = {
                "portfolio_value": 4990,
                "pnl_pct": -0.2,
            }
            session.candles.all_candles.return_value = [{"close": start_price, "time": 1}]
            sessions[symbol] = session
        bench = portfolio_benchmark(sessions)
        self.assertIn("vs_hold_pct", bench)
        self.assertIn("benchmark_quality", bench)

    def test_week_prep_api(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        response = client.post("/api/week-prep/start")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("live_readiness", data)


if __name__ == "__main__":
    unittest.main()
