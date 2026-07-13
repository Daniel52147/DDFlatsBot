"""v47 — Telegram, TradingView webhooks, protections."""

from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import config
from integrations.tradingview_webhook import handle_tradingview_signal, validate_webhook_secret
from learning.protections import ProtectionsEngine
from simulator.engine import SimulatorEngine
from simulator.market_session import MarketSession
from simulator.risk_gate import blocks_new_buys, set_correlation_block, set_portfolio_halt


class TestProtections(unittest.TestCase):
    def setUp(self):
        self.engine = ProtectionsEngine()
        self.engine.clear_all()
        self.engine._recent_trades.clear()
        self.engine._actions.clear()

    def _trade(self, symbol: str, side: str, reason: str):
        return SimpleNamespace(
            ts=time.time(),
            side=side,
            reason=reason,
            price=100.0,
            amount_quote=10.0,
        )

    def test_stoploss_guard_pauses_symbol(self):
        with patch.object(config, "PROTECTIONS_ENABLED", True), patch.object(
            config, "PROTECTION_STOPLOSS_COUNT", 3
        ):
            for _ in range(3):
                self.engine.on_trade("BTCUSDT", self._trade("BTCUSDT", "sell", "STOP-LOSS: −5%"))
            blocked, reason = self.engine.blocks_buy("BTCUSDT")
            self.assertTrue(blocked)
            self.assertIn("пауза", reason.lower())

    def test_cooldown_blocks_global_buys(self):
        with patch.object(config, "PROTECTIONS_ENABLED", True), patch.object(
            config, "PROTECTION_COOLDOWN_LOSSES", 3
        ):
            for _ in range(3):
                self.engine.on_trade("ETHUSDT", self._trade("ETHUSDT", "sell", "STOP-LOSS: −2%"))
            blocked, _ = self.engine.blocks_buy("SOLUSDT")
            self.assertTrue(blocked)

    def test_clear_symbol(self):
        self.engine._symbol_pause_until["BTCUSDT"] = time.time() + 3600
        self.engine.clear_symbol("BTCUSDT")
        blocked, _ = self.engine.blocks_buy("BTCUSDT")
        self.assertFalse(blocked)


class TestRiskGateProtections(unittest.TestCase):
    def tearDown(self):
        set_portfolio_halt(False)
        set_correlation_block(False)
        from learning.protections import protections_engine
        protections_engine.clear_all()

    def test_blocks_with_protection(self):
        from learning.protections import protections_engine
        protections_engine._global_cooldown_until = time.time() + 600
        self.assertTrue(blocks_new_buys("BTCUSDT"))


class TestTradingViewWebhook(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_secret(self):
        with patch.object(config, "TRADINGVIEW_WEBHOOK_SECRET", "secret123"):
            result = await handle_tradingview_signal(
                {"secret": "wrong", "symbol": "BTC", "action": "buy"},
                {},
            )
            self.assertFalse(result["ok"])

    async def test_buy_signal(self):
        m = config.MARKETS[0]
        session = MarketSession(m)
        session.feed.price = m["demo_price"]
        session.manual_trade = AsyncMock(return_value={"side": "buy", "price": 100})
        sessions = {m["symbol"]: session}
        with patch.object(config, "TRADINGVIEW_WEBHOOK_SECRET", "tv-secret"):
            result = await handle_tradingview_signal(
                {"secret": "tv-secret", "symbol": "BTC", "action": "buy", "size_usdt": 10},
                sessions,
            )
            self.assertTrue(result["ok"])
            session.manual_trade.assert_awaited_once()

    async def test_pause_all(self):
        m = config.MARKETS[0]
        session = MarketSession(m)
        session.persist = AsyncMock()
        sessions = {m["symbol"]: session}
        with patch.object(config, "TRADINGVIEW_WEBHOOK_SECRET", "tv-secret"):
            result = await handle_tradingview_signal(
                {"secret": "tv-secret", "action": "pause"},
                sessions,
            )
            self.assertTrue(result["ok"])
            self.assertFalse(session.bot.enabled)


class TestEngineSymbol(unittest.TestCase):
    def test_buy_respects_market_symbol(self):
        from learning.protections import protections_engine
        protections_engine.clear_all()
        protections_engine._symbol_pause_until["BTCUSDT"] = time.time() + 600
        eng = SimulatorEngine(1000)
        eng.market_symbol = "BTCUSDT"
        trade = eng.buy(100.0, 10.0, "test")
        self.assertIsNone(trade)


class TestWebhookSecret(unittest.TestCase):
    def test_validate(self):
        with patch.object(config, "TRADINGVIEW_WEBHOOK_SECRET", "abc"):
            self.assertTrue(validate_webhook_secret("abc"))
            self.assertFalse(validate_webhook_secret("xyz"))


if __name__ == "__main__":
    unittest.main()
