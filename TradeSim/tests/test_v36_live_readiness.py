"""v36 — live readiness gate and stricter live limits."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from exchange.live_readiness import assess_live_readiness
from exchange.trading_mode import TradingModeManager


class MockExchange:
    def __init__(self, enabled=False, testnet=True):
        self.enabled = enabled
        self.testnet = testnet

    def status(self):
        return {"enabled": self.enabled, "testnet": self.testnet}


class TestLiveReadiness(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_shape(self):
        sessions = {}
        ex = MockExchange(enabled=True, testnet=True)
        tm = MagicMock()
        tm.mode = "paper"
        tm.milestones.return_value = {}
        logger = AsyncMock()
        logger.performance_summary.return_value = {"trade_count": 5}
        bench = {"vs_hold_pct": 1.0, "live_pnl_pct": 0.5, "hold_pnl_pct": -0.5}
        r = await assess_live_readiness(
            sessions, ex, logger, tm,
            benchmark=bench,
            verify={"ok": True, "usdt_free": 1000},
        )
        self.assertIn("score_pct", r)
        self.assertIn("checks", r)
        self.assertFalse(r["ready_for_live"])
        ids = {c["id"] for c in r["checks"]}
        self.assertIn("testnet_env", ids)
        live_chk = next(c for c in r["checks"] if c["id"] == "live_env")
        self.assertFalse(live_chk["required"])

    def test_live_blocked_without_readiness(self):
        tm = TradingModeManager()
        ex = MockExchange(enabled=True, testnet=False)
        r = tm.set_mode("live", exchange=ex, readiness={"ready_for_live": False, "score_pct": 40})
        self.assertFalse(r["ok"])
        self.assertIn("заблокирован", r["error"].lower())

    def test_api_live_readiness(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        r = client.get("/api/live-readiness")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("week_plan", data)


if __name__ == "__main__":
    unittest.main()
