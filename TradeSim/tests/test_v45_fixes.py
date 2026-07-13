"""v45 — critical fixes: exchange fill credit, desync recovery, persistence."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from exchange.paper_sync import recover_exchange_to_paper
from exchange.trading_mode import TradingModeManager
from simulator.engine import SimulatorEngine
import config


class TestApplyExchangeFillCredit(unittest.TestCase):
    def test_buy_uses_wallet_credit(self):
        eng = SimulatorEngine(initial_balance=10.0)
        eng.wallet_credit = 100.0
        trade = eng.apply_exchange_fill(
            side="buy",
            price=100.0,
            amount_base=0.5,
            amount_quote=50.0,
            fee=0.1,
            reason="EXCHANGE TEST",
        )
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(eng.wallet_credit, 60.0)


class TestTradingModeMirror(unittest.TestCase):
    def test_mirror_bots_requires_sync_from_paper(self):
        mgr = TradingModeManager()
        ex = MagicMock()
        ex.enabled = True
        ex.testnet = True
        ex.status.return_value = {
            "enabled": True,
            "testnet": True,
            "sync_to_paper": True,
            "sync_from_paper": False,
        }
        with patch.object(mgr, "_mode", "testnet"), patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", False):
            st = mgr.status(ex)
        self.assertFalse(st["mirror_bots"])
        self.assertTrue(st["sync_to_paper"])


class TestRecoverDesync(unittest.IsolatedAsyncioTestCase):
    async def test_recovers_via_mirror_when_fill_fails(self):
        session = MagicMock()
        session.symbol = "BTCUSDT"
        session.feed.price = 100.0
        session.demo_price = 100.0
        eng = SimulatorEngine(initial_balance=0.0)
        session.engine = eng
        session._log_trade = AsyncMock()

        exchange = MagicMock()
        exchange.enabled = True
        exchange.reconcile = AsyncMock(return_value={
            "paper_base": 0.0,
            "exchange_base": 0.01,
            "paper_quote": 0.0,
        })

        result = {"ok": True, "order": {"symbol": "BTCUSDT", "side": "BUY", "orderId": 1, "fills": []}}
        with patch("exchange.paper_sync.parse_binance_order", return_value=None):
            recovered = await recover_exchange_to_paper(session, exchange, result)
        self.assertFalse(recovered.get("ok"))


class TestMirrorUsdtNoStartBalance(unittest.IsolatedAsyncioTestCase):
    async def test_mirror_does_not_inflate_pnl(self):
        from exchange.wallet_service import mirror_usdt_to_paper
        from simulator.market_session import MarketSession

        m = config.MARKETS[0]
        s = MarketSession(m)
        start = s.engine.start_balance
        s.engine.position.quote = 100.0
        sessions = {s.symbol: s}
        exchange = MagicMock()
        exchange.enabled = True
        exchange.testnet = True
        exchange.account_balances = AsyncMock(return_value={
            "balances": [{"asset": "USDT", "free": 200.0, "locked": 0}],
        })
        with patch.object(s, "persist", new_callable=AsyncMock):
            result = await mirror_usdt_to_paper(sessions, exchange, amount=50.0)
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(s.engine.start_balance, start)


if __name__ == "__main__":
    unittest.main()
