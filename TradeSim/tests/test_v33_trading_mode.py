"""v33 — trading mode paper/testnet/live."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from exchange.trading_mode import TradingModeManager


class MockExchange:
    def __init__(self, enabled=False, testnet=True):
        self.enabled = enabled
        self.testnet = testnet

    def status(self):
        return {
            "enabled": self.enabled,
            "testnet": self.testnet,
            "exchange": "binance",
            "max_order_usd": 100,
        }


class TestTradingMode(unittest.TestCase):
    def test_paper_always_ok(self):
        tm = TradingModeManager()
        ex = MockExchange(enabled=False)
        r = tm.set_mode("paper", exchange=ex)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "paper")
        self.assertFalse(tm.should_mirror_to_exchange())

    def test_testnet_requires_keys(self):
        tm = TradingModeManager()
        ex = MockExchange(enabled=False)
        r = tm.set_mode("testnet", exchange=ex)
        self.assertFalse(r["ok"])
        self.assertIn("API", r["error"])

    def test_testnet_with_keys(self):
        tm = TradingModeManager()
        ex = MockExchange(enabled=True, testnet=True)
        r = tm.set_mode("testnet", exchange=ex)
        self.assertTrue(r["ok"])
        self.assertEqual(r["mode"], "testnet")
        self.assertTrue(tm.should_mirror_to_exchange())

    def test_api_trading_mode(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        r = client.get("/api/trading-mode")
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["mode"], ("paper", "testnet", "live"))


if __name__ == "__main__":
    unittest.main()
