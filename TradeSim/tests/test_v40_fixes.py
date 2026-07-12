"""v40 — security, drawdown, sync, API consistency fixes."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import config
from exchange.binance_live import ExchangeRiskManager
from exchange.live_readiness import _portfolio_drawdown_ok
from exchange.trading_mode import TradingModeManager
from learning.optimizer import StrategyOptimizer


class MockExchange:
    def __init__(self, enabled=False, testnet=True):
        self.enabled = enabled
        self.testnet = testnet


class TestV40Fixes(unittest.IsolatedAsyncioTestCase):
    async def test_portfolio_drawdown_uses_total_not_single_market(self):
        """Peak must be portfolio-level, not max of one market's start_balance."""
        s1 = MagicMock()
        s1.feed.price = 100.0
        s1.demo_price = 100.0
        s1.engine.start_balance = 600.0
        s1.engine.snapshot.return_value = {"portfolio_value": 550.0}

        s2 = MagicMock()
        s2.feed.price = 50.0
        s2.demo_price = 50.0
        s2.engine.start_balance = 600.0
        s2.engine.snapshot.return_value = {"portfolio_value": 550.0}

        sessions = {"A": s1, "B": s2}
        logger = AsyncMock()
        logger.equity_curve.return_value = [{"value": 1200.0}]

        ok, dd, peak = await _portfolio_drawdown_ok(sessions, logger, 8.0, portfolio_peak=1200.0)
        self.assertFalse(ok)
        self.assertGreater(dd, 8.0)
        self.assertGreaterEqual(peak, 1200.0)

    def test_live_force_blocked_without_env(self):
        tm = TradingModeManager()
        ex = MockExchange(enabled=True, testnet=False)
        with patch.object(config, "LIVE_ALLOW_FORCE", False):
            r = tm.set_mode(
                "live",
                exchange=ex,
                readiness={"ready_for_live": False, "score_pct": 10},
                force=True,
            )
        self.assertFalse(r["ok"])

    def test_exchange_risk_uses_portfolio_pnl(self):
        risk = ExchangeRiskManager()
        risk.note_portfolio_value(10_000)
        ok, _ = risk.check_order(
            "buy", 25, 10_000, pnl_pct=0,
            portfolio_pnl_pct=-6.0,
            max_daily_loss_pct=5.0,
        )
        self.assertFalse(ok)

    def test_optimizer_float_dca_in_paper_learn(self):
        opt = StrategyOptimizer(
            {"dca_interval_hours": 1.5, "dip_threshold_pct": 2.0, "dca_amount": 25.0,
             "dip_extra_amount": 30.0, "sma_period": 20, "take_profit_pct": 8.0,
             "take_profit_fraction": 0.2, "take_profit_cooldown_hours": 1.0,
             "dip_cooldown_minutes": 5, "spike_cooldown_minutes": 10,
             "stop_loss_pct": 12.0, "stop_loss_fraction": 0.2},
            bounds=StrategyOptimizer.bounds_for_paper_learn(False),
            volatile=False,
        )
        with patch("learning.paper_learn_mode.is_paper_learn_mode", return_value=True):
            out = opt.apply_params({"dca_interval_hours": 1.5})
        self.assertAlmostEqual(out["dca_interval_hours"], 1.5)

    def test_api_markets_mode_not_hardcoded_paper(self):
        from fastapi.testclient import TestClient
        import main

        with patch.object(type(main.trading_mode), "mode", new_callable=PropertyMock) as m:
            m.return_value = "testnet"
            client = TestClient(main.app)
            data = client.get("/api/markets").json()
            self.assertEqual(data.get("mode"), "testnet")

    async def test_mirror_sync_fails_when_no_paper_base(self):
        from exchange.paper_sync import mirror_base_from_exchange

        session = MagicMock()
        session.symbol = "BTCUSDT"
        session.label = "BTC"
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine.position.base = 0.0
        session.engine.position.quote = 1000.0

        exchange = AsyncMock()
        exchange.enabled = True
        exchange.reconcile = AsyncMock(return_value={
            "paper_base": 1.0,
            "exchange_base": 0.0,
            "paper_quote": 1000.0,
        })

        result = await mirror_base_from_exchange(session, exchange)
        self.assertFalse(result["ok"])
        self.assertFalse(result["synced"])


if __name__ == "__main__":
    unittest.main()
