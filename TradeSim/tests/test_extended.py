"""Extended tests — analytics, security, cost basis."""

from __future__ import annotations

import copy
import unittest

import config
from learning.analytics import analyze_market_trades
from security import RateLimiter, auth_required
from simulator.engine import SimulatorEngine
from tests.test_core import TestEngineFeesAndCostBasis


class TestCostBasisEconomic(unittest.TestCase):
    def test_cost_basis_is_net_not_gross(self):
        engine = SimulatorEngine(initial_balance=1000.0)
        engine.buy(100.0, 200.0, reason="buy")
        fee = 200.0 * config.FEE_RATE
        self.assertAlmostEqual(engine.position.cost_basis, 200.0 - fee, places=4)

    def test_avg_entry_matches_economic_price(self):
        engine = SimulatorEngine(initial_balance=1000.0)
        engine.buy(100.0, 500.0, reason="buy")
        avg = engine.avg_entry_price()
        self.assertIsNotNone(avg)
        expected = engine.position.cost_basis / engine.position.base
        self.assertAlmostEqual(avg, expected, places=6)

    def test_sell_half_reduces_basis_by_half(self):
        engine = SimulatorEngine(initial_balance=1000.0)
        engine.buy(100.0, 500.0, reason="buy")
        base = engine.position.base
        basis_before = engine.position.cost_basis
        engine.sell(110.0, base * 0.5, reason="sell half")
        self.assertAlmostEqual(engine.position.cost_basis, basis_before * 0.5, places=2)


class TestAnalyticsWinRate(unittest.TestCase):
    def test_win_rate_counts_profitable_sells(self):
        trades = [
            {"ts": 1, "side": "buy", "price": 100, "amount_quote": 100, "amount_base": 1, "fee": 0.1},
            {"ts": 2, "side": "sell", "price": 110, "amount_quote": 110, "amount_base": 0.5, "fee": 0.1},
            {"ts": 3, "side": "sell", "price": 90, "amount_quote": 90, "amount_base": 0.5, "fee": 0.1},
        ]
        stats = analyze_market_trades(trades)
        self.assertEqual(stats["sell_count"], 2)
        self.assertEqual(stats["wins"], 1)
        self.assertEqual(stats["win_rate_pct"], 50.0)


class TestSecurity(unittest.TestCase):
    def test_rate_limiter_blocks_burst(self):
        rl = RateLimiter()
        path = "/api/backtest"
        key = "127.0.0.1:" + path
        limit, _ = __import__("security").RATE_LIMITS[path]
        for _ in range(limit):
            self.assertTrue(rl.allow(key, path))
        self.assertFalse(rl.allow(key, path))

    def test_auth_required_without_token(self):
        orig = __import__("security").API_TOKEN
        try:
            __import__("security").API_TOKEN = ""
            self.assertFalse(auth_required())
        finally:
            __import__("security").API_TOKEN = orig


if __name__ == "__main__":
    unittest.main()
