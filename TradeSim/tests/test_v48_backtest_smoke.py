"""v48 — backtest metrics and smoke test harness."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import config
from learning.backtest_metrics import (
    calmar_ratio,
    compute_backtest_metrics,
    sharpe_ratio,
    sortino_ratio,
)
from learning.smoke_test import run_smoke_test
from simulator.backtest import Backtester


class TestBacktestMetrics(unittest.TestCase):
    def test_sharpe_positive_trend(self):
        returns = [0.1, 0.2, 0.15, 0.05, 0.12, 0.08]
        s = sharpe_ratio(returns, interval_minutes=60)
        self.assertIsNotNone(s)
        self.assertGreater(s, 0)

    def test_sortino(self):
        returns = [0.2, -0.1, 0.15, -0.05, 0.1]
        s = sortino_ratio(returns, interval_minutes=60)
        self.assertIsNotNone(s)

    def test_calmar(self):
        c = calmar_ratio(5.0, 2.0, period_bars=500, interval_minutes=1)
        self.assertIsNotNone(c)
        self.assertGreater(c, 0)

    def test_compute_backtest_metrics(self):
        trades = [
            SimpleNamespace(side="buy", price=100, amount_quote=50, amount_base=0.5, fee=0.05, reason="DCA"),
            SimpleNamespace(side="sell", price=105, amount_quote=52.5, amount_base=0.5, fee=0.05, reason="TP"),
        ]
        equity = [588.0, 590.0, 595.0, 600.0]
        m = compute_backtest_metrics(
            equity_curve=equity,
            executed_trades=trades,
            pnl_pct=2.0,
            interval_minutes=1,
        )
        self.assertIn("max_drawdown_pct", m)
        self.assertIn("win_rate_pct", m)


class TestBacktesterMetrics(unittest.TestCase):
    def test_run_includes_metrics(self):
        candles = []
        price = 100.0
        for i in range(120):
            o = price
            c = price * (1 + (0.001 if i % 10 < 6 else -0.0005))
            candles.append({"open": o, "high": max(o, c) * 1.001, "low": min(o, c) * 0.999, "close": c})
            price = c
        bt = Backtester(initial_balance=588.0, strategy_type="dca")
        result = bt.run(candles)
        self.assertIn("metrics", result)
        self.assertIn("metrics_summary", result)
        self.assertIn("sharpe", result["metrics"])


class TestSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_paper_mode_passes_core(self):
        session = MagicMock()
        session._candles_ready = True
        session.candles.lag_sec = MagicMock(return_value=30.0)
        session.feed.price = 100.0
        session.engine.position = MagicMock(base=0.01, quote=500)
        sessions = {m["symbol"]: session for m in config.MARKETS}

        exchange = MagicMock()
        exchange.enabled = False

        logger_db = MagicMock()
        logger_db.stability_summary = AsyncMock(return_value={
            "success_rate_pct": 100, "exchange_orders": 0, "sync_failures": 0,
        })

        mode = MagicMock()
        mode.mode = "paper"
        mode.status = MagicMock(return_value={"label": "Paper"})

        result = await run_smoke_test(
            sessions=sessions,
            exchange=exchange,
            logger_db=logger_db,
            trading_mode_mgr=mode,
            live_readiness={"score_pct": 80, "stats": {"trade_count": 50}},
            live_prep={"phase_progress": "2/5", "summary": "test"},
            telegram_enabled=False,
            feed_hub_ok=True,
        )
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["score_pct"], 80)
        self.assertIn("checks", result)

    async def test_testnet_paper_only_reconcile_passes(self):
        """Paper positions without exchange mirror should not fail smoke reconcile."""
        session = MagicMock()
        session._candles_ready = True
        session.candles.lag_sec = MagicMock(return_value=30.0)
        session.feed.price = 100000.0
        session.demo_price = 100000.0
        session.engine.position = MagicMock(base=0.01, quote=500.0)
        sessions = {"BTCUSDT": session}

        exchange = MagicMock()
        exchange.enabled = True
        exchange.testnet = False
        exchange.verify_connection = AsyncMock(return_value={"ok": True, "usdt_free": 10000})
        exchange.reconcile = AsyncMock(return_value={
            "paper_base": 0.01,
            "exchange_base": 0.0,
            "base_diff": -0.01,
            "base_synced": False,
        })

        logger_db = MagicMock()
        logger_db.stability_summary = AsyncMock(return_value={
            "success_rate_pct": 95, "exchange_orders": 5, "sync_failures": 0,
        })
        logger_db.clear_stability_events = AsyncMock(return_value=0)
        logger_db.log_stability_event = AsyncMock()

        mode = MagicMock()
        mode.mode = "testnet"
        mode.status = MagicMock(return_value={"label": "Testnet"})

        with patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", False), \
             patch.object(config, "EXCHANGE_TESTNET", False):
            result = await run_smoke_test(
                sessions=sessions,
                exchange=exchange,
                logger_db=logger_db,
                trading_mode_mgr=mode,
                live_readiness={"score_pct": 80, "stats": {"trade_count": 50}, "ready_for_live": False},
                live_prep={"phase_progress": "3/5", "summary": "test"},
                telegram_enabled=True,
                feed_hub_ok=True,
            )
        reconcile = next(c for c in result["checks"] if c["id"] == "reconcile")
        self.assertTrue(reconcile["ok"])
        self.assertIn("paper-only", reconcile["detail"])

    async def test_testnet_faucet_and_paper_ahead_not_bad(self):
        from learning.smoke_test import _quick_reconcile

        btc = MagicMock()
        btc.feed.price = 65000.0
        btc.demo_price = 65000.0
        btc.engine.position = MagicMock(base=0.03, quote=200.0)

        eth = MagicMock()
        eth.feed.price = 2000.0
        eth.demo_price = 2000.0
        eth.engine.position = MagicMock(base=0.5, quote=200.0)  # paper $1000

        sessions = {"BTCUSDT": btc, "ETHUSDT": eth}
        exchange = MagicMock()
        exchange.testnet = True

        async def _rec(sym, paper_base, paper_quote):
            if sym.startswith("BTC"):
                return {"paper_base": paper_base, "exchange_base": 1.0, "base_synced": False}
            return {"paper_base": paper_base, "exchange_base": 0.0, "base_synced": False}

        exchange.reconcile = AsyncMock(side_effect=_rec)
        with patch.object(config, "EXCHANGE_TESTNET", True):
            rows = await _quick_reconcile(sessions, exchange)
        self.assertFalse(any(r["bad"] for r in rows))
        statuses = {r["status"] for r in rows}
        self.assertIn("testnet_faucet", statuses)
        self.assertIn("paper_ahead", statuses)

    async def test_testnet_moderate_drift_not_bad(self):
        from learning.smoke_test import _quick_reconcile

        bnb = MagicMock()
        bnb.feed.price = 576.0
        bnb.demo_price = 576.0
        bnb.engine.position = MagicMock(base=0.1, quote=200.0)

        sessions = {"BNBUSDT": bnb}
        exchange = MagicMock()
        exchange.testnet = True
        exchange.reconcile = AsyncMock(return_value={
            "paper_base": 0.1, "exchange_base": 0.05, "base_synced": False,
        })
        with patch.object(config, "EXCHANGE_TESTNET", True):
            rows = await _quick_reconcile(sessions, exchange)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["bad"])
        self.assertEqual(rows[0]["status"], "testnet_drift")

    async def test_smoke_purges_legacy_sync_failures(self):
        session = MagicMock()
        session._candles_ready = True
        session.candles.lag_sec = MagicMock(return_value=30.0)
        session.feed.price = 100.0
        session.demo_price = 100.0
        session.engine.position = MagicMock(base=0.0, quote=500)
        sessions = {m["symbol"]: session for m in config.MARKETS[:1]}

        exchange = MagicMock()
        exchange.enabled = True
        exchange.testnet = True
        exchange.verify_connection = AsyncMock(return_value={"ok": True, "usdt_free": 100})
        exchange.reconcile = AsyncMock(return_value={
            "paper_base": 0.0, "exchange_base": 0.0, "base_synced": True,
        })

        logger_db = MagicMock()
        logger_db.stability_summary = AsyncMock(side_effect=[
            {"success_rate_pct": 57, "exchange_orders": 15, "sync_failures": 113},
            {"success_rate_pct": 100, "exchange_orders": 15, "sync_failures": 0},
        ])
        logger_db.clear_stability_events = AsyncMock(return_value=113)
        logger_db.log_stability_event = AsyncMock()

        mode = MagicMock()
        mode.mode = "testnet"
        mode.status = MagicMock(return_value={"label": "Testnet"})

        result = await run_smoke_test(
            sessions=sessions,
            exchange=exchange,
            logger_db=logger_db,
            trading_mode_mgr=mode,
            live_readiness={"score_pct": 90, "stats": {"trade_count": 50}, "ready_for_live": False},
            live_prep={"phase_progress": "2/5", "summary": "test"},
            telegram_enabled=False,
            feed_hub_ok=True,
        )
        logger_db.clear_stability_events.assert_awaited()
        stab = next(c for c in result["checks"] if c["id"] == "stability")
        self.assertTrue(stab["ok"])
        self.assertIn("113", stab["detail"])


if __name__ == "__main__":
    unittest.main()
