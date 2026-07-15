"""v41 — remaining audit items: WS auth, lifetime hold, exposure guard."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import config
from exchange.trading_mode import TradingModeManager
from security import require_exposure_auth, token_valid
from simulator.engine import SimulatorEngine
from simulator.portfolio_benchmark import hold_anchor_price, sync_session_hold_benchmark


class MockExchange:
    def __init__(self, enabled=False, testnet=True):
        self.enabled = enabled
        self.testnet = testnet


class TestV41Remaining(unittest.TestCase):
    def test_lifetime_anchor_without_trades(self):
        session = MagicMock()
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine = SimulatorEngine(initial_balance=1000)
        session.engine.start_price = 150.0
        session.engine.trades = []
        session.candles.all_candles.return_value = [{"close": 98.0, "time": 1}]
        price, anchor = hold_anchor_price(session)
        self.assertEqual(anchor, "lifetime_anchor")
        self.assertEqual(price, 150.0)

    def test_locked_anchor_not_overwritten_by_candle(self):
        session = MagicMock()
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine = SimulatorEngine(initial_balance=1000)
        session.engine.benchmark_hold_price = 120.0
        session.engine.benchmark_hold_anchor = "lifetime_anchor"
        session.engine.start_price = 120.0
        session.candles.all_candles.return_value = [{"close": 90.0, "time": 1}]
        sync_session_hold_benchmark(session)
        self.assertEqual(session.engine.benchmark_hold_price, 120.0)

    def test_live_bypass_requires_allow_force(self):
        tm = TradingModeManager()
        ex = MockExchange(enabled=True, testnet=False)
        with patch.object(config, "LIVE_BYPASS_READINESS", True), patch.object(
            config, "LIVE_ALLOW_FORCE", False,
        ):
            r = tm.set_mode(
                "live", exchange=ex,
                readiness={"ready_for_live": False, "score_pct": 10},
            )
        self.assertFalse(r["ok"])

    def test_token_valid(self):
        with patch.object(config, "API_TOKEN", "secret"):
            self.assertTrue(token_valid("secret"))
            self.assertFalse(token_valid("wrong"))
            self.assertFalse(token_valid(None))

    def test_block_public_bind_without_token(self):
        with patch.object(config, "API_TOKEN", ""):
            with self.assertRaises(SystemExit):
                require_exposure_auth("0.0.0.0")

    def test_trading_mode_requires_token_when_set(self):
        from fastapi.testclient import TestClient
        import main

        with patch.object(config, "API_TOKEN", "secret"):
            client = TestClient(main.app)
            r = client.post("/api/trading-mode", json={"mode": "paper"})
            self.assertEqual(r.status_code, 401)
            r2 = client.post(
                "/api/trading-mode",
                json={"mode": "paper"},
                headers={"X-API-Token": "secret"},
            )
            self.assertEqual(r2.status_code, 200)

    def test_localhost_bypasses_write_auth(self):
        from fastapi.testclient import TestClient
        import main

        with patch.object(config, "API_TOKEN", "secret"), patch(
            "security.client_ip", return_value="127.0.0.1",
        ):
            client = TestClient(main.app)
            r = client.post("/api/smoke-test", json={})
            self.assertNotEqual(r.status_code, 401)

    def test_benchmark_persisted_in_save_session(self):
        import asyncio
        from learning.logger import LearningLogger
        import tempfile
        from pathlib import Path

        async def run():
            path = Path(tempfile.mkdtemp()) / "test.db"
            log = LearningLogger(path)
            await log.init()
            await log.save_session("BTCUSDT", {
                "quote": 1000, "base": 0, "trade_counter": 0,
                "start_balance": 1000, "start_ts": 1.0,
                "bot_params": {}, "last_dca_ts": 0, "last_take_profit_ts": 0,
                "bot_enabled": True, "trades": [],
                "benchmark_hold_price": 42000.0,
                "benchmark_hold_anchor": "lifetime_anchor",
            })
            loaded = await log.load_session("BTCUSDT")
            self.assertAlmostEqual(loaded["benchmark_hold_price"], 42000.0)
            self.assertEqual(loaded["benchmark_hold_anchor"], "lifetime_anchor")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
