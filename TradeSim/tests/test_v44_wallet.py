"""v44 — paper/exchange wallet, withdraw, bot wallet bridge."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from exchange.wallet_service import paper_withdraw, refresh_wallet_bridge
from simulator.engine import SimulatorEngine
from simulator.market_session import MarketSession
import config


class TestWalletCredit(unittest.TestCase):
    def test_buy_uses_wallet_credit(self):
        eng = SimulatorEngine(initial_balance=50.0)
        eng.wallet_credit = 100.0
        trade = eng.buy(100.0, 80.0, reason="test")
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(eng.position.quote, 0.0)
        self.assertAlmostEqual(eng.wallet_credit, 70.0)

    def test_withdraw_quote_only_from_paper(self):
        eng = SimulatorEngine(initial_balance=200.0)
        eng.wallet_credit = 50.0
        taken = eng.withdraw_quote(150.0)
        self.assertAlmostEqual(taken, 150.0)
        self.assertAlmostEqual(eng.position.quote, 50.0)
        self.assertAlmostEqual(eng.wallet_credit, 50.0)


class TestPaperWithdraw(unittest.IsolatedAsyncioTestCase):
    async def test_split_withdraw(self):
        m1 = config.MARKETS[0]
        m2 = config.MARKETS[1]
        s1 = MarketSession(m1)
        s2 = MarketSession(m2)
        s1.engine.position.quote = 100.0
        s2.engine.position.quote = 100.0
        s1.engine.start_balance = 100.0
        s2.engine.start_balance = 100.0
        sessions = {s1.symbol: s1, s2.symbol: s2}
        with patch.object(s1, "persist", new_callable=AsyncMock), \
             patch.object(s2, "persist", new_callable=AsyncMock):
            result = await paper_withdraw(sessions, 40.0, target="split")
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["withdrawn"], 40.0)


class TestWalletBridge(unittest.IsolatedAsyncioTestCase):
    async def test_bridge_allocates_spare_usdt(self):
        m = config.MARKETS[0]
        s = MarketSession(m)
        s.engine.position.quote = 100.0
        sessions = {s.symbol: s}
        exchange = MagicMock()
        exchange.enabled = True
        exchange.testnet = True
        exchange.account_balances = AsyncMock(return_value={
            "balances": [{"asset": "USDT", "free": 500.0, "locked": 0}],
        })
        mode = MagicMock()
        mode.mode = "testnet"
        result = await refresh_wallet_bridge(sessions, exchange, mode)
        self.assertTrue(result["ok"])
        self.assertGreater(s.engine.wallet_credit, 0)


class TestLiveReadinessLimits(unittest.IsolatedAsyncioTestCase):
    async def test_limits_if_live_present(self):
        from exchange.live_readiness import assess_live_readiness
        exchange = MagicMock()
        exchange.enabled = False
        exchange.testnet = True
        logger = MagicMock()
        logger.performance_summary = AsyncMock(return_value={"trade_count": 0})
        logger.equity_curve = AsyncMock(return_value=[])
        mode = MagicMock()
        mode.mode = "paper"
        mode.milestones = MagicMock(return_value={"testnet_since": 0})
        result = await assess_live_readiness(
            {},
            exchange,
            logger,
            mode,
            benchmark={"vs_hold_pct": 0, "live_pnl_pct": 0, "hold_pnl_pct": 0},
            verify={"ok": False},
        )
        self.assertIn("limits_if_live", result)
        self.assertEqual(result["limits_if_live"]["max_order_usd"], config.LIVE_MAX_ORDER_USD)


if __name__ == "__main__":
    unittest.main()
