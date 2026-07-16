"""Exchange → paper sync tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import config
from exchange.paper_sync import mirror_base_from_exchange, parse_binance_order, sync_order_to_paper, sync_trade_to_exchange
from simulator.engine import SimulatorEngine


class MockExchange:
    enabled = True
    testnet = False

    def __init__(self, exchange_base: float):
        self._exchange_base = exchange_base

    def order_limits(self) -> dict:
        return {"max_order_usd": 100.0, "max_daily_loss_pct": 5.0, "max_position_pct": 0.25}

    async def asset_balance(self, asset: str) -> float:
        if asset == "USDT":
            return 10_000.0
        return float(self._exchange_base)

    async def reconcile(self, symbol: str, paper_base: float, paper_quote: float) -> dict:
        return {
            "exchange_base": self._exchange_base,
            "paper_base": paper_base,
            "paper_quote": paper_quote,
        }


class MockSession:
    def __init__(self, quote: float = 1000.0, base: float = 0.0, price: float = 100.0):
        self.symbol = "BTCUSDT"
        self.label = "BTC"
        self.demo_price = price
        self.engine = SimulatorEngine(initial_balance=quote)
        self.engine.position.base = base
        self.feed = SimpleNamespace(price=price)
        self._log_trade = AsyncMock()
        self.persist = AsyncMock()


class TestParseBinanceOrder(unittest.TestCase):
    def test_buy_with_fills(self):
        order = {
            "side": "BUY",
            "orderId": 99,
            "fills": [
                {"price": "100.0", "qty": "0.05", "commission": "0.01", "commissionAsset": "USDT"},
                {"price": "100.0", "qty": "0.05", "commission": "0.0001", "commissionAsset": "BTC"},
            ],
        }
        fill = parse_binance_order(order, "BTCUSDT")
        assert fill is not None
        self.assertEqual(fill["side"], "buy")
        self.assertAlmostEqual(fill["amount_base"], 0.0999, places=4)
        self.assertGreater(fill["amount_quote"], 0)

    def test_sell_executed_qty_fallback(self):
        order = {
            "side": "SELL",
            "executedQty": "0.1",
            "cummulativeQuoteQty": "6500",
        }
        fill = parse_binance_order(order, "BTCUSDT")
        assert fill is not None
        self.assertEqual(fill["side"], "sell")
        self.assertEqual(fill["amount_base"], 0.1)


class TestApplyExchangeFill(unittest.TestCase):
    def test_buy_updates_paper_without_double_fee(self):
        eng = SimulatorEngine(initial_balance=1000.0)
        trade = eng.apply_exchange_fill(
            "buy", price=100.0, amount_base=0.5, amount_quote=50.0, fee=0.05,
            reason="EXCHANGE TEST",
        )
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertAlmostEqual(eng.position.quote, 950.0)
        self.assertAlmostEqual(eng.position.base, 0.5)
        self.assertIn("EXCHANGE", trade.reason)

    def test_sell_updates_paper(self):
        eng = SimulatorEngine(initial_balance=1000.0)
        eng.apply_exchange_fill("buy", 100, 1.0, 100, 0, "setup")
        trade = eng.apply_exchange_fill("sell", 110, 0.5, 55, 0.05, "EXCHANGE SELL")
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(eng.position.base, 0.5)


class TestMirrorBaseFromExchange(unittest.IsolatedAsyncioTestCase):
    async def test_mirror_buy_deducts_usdt(self):
        session = MockSession(quote=1000.0, base=0.0, price=100.0)
        exchange = MockExchange(exchange_base=1.0)
        result = await mirror_base_from_exchange(session, exchange, tolerance=0.0)
        self.assertTrue(result["ok"])
        fee = 100.0 * config.FEE_RATE
        self.assertAlmostEqual(session.engine.position.quote, 1000.0 - 100.0 - fee, places=2)
        self.assertAlmostEqual(session.engine.position.base, 1.0)
        snap = session.engine.snapshot(100.0)
        self.assertAlmostEqual(snap["portfolio_value"], 1000.0 - fee, places=1)
        session._log_trade.assert_awaited_once()

    async def test_mirror_buy_insufficient_quote(self):
        session = MockSession(quote=50.0, base=0.0, price=100.0)
        exchange = MockExchange(exchange_base=1.0)
        result = await mirror_base_from_exchange(session, exchange, tolerance=0.0)
        self.assertFalse(result["ok"])
        self.assertIn("insufficient", result["error"].lower())
        self.assertAlmostEqual(session.engine.position.base, 0.0)

    async def test_mirror_sell_adds_usdt(self):
        session = MockSession(quote=500.0, base=2.0, price=100.0)
        exchange = MockExchange(exchange_base=1.0)
        with patch.object(config, "EXCHANGE_TESTNET", False), \
             patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", False):
            result = await mirror_base_from_exchange(session, exchange, tolerance=0.0)
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(session.engine.position.base, 1.0)
        self.assertAlmostEqual(session.engine.position.quote, 600.0)

    async def test_mirror_skips_sell_when_paper_ahead_on_testnet(self):
        """Sync paper (все) must not liquidate paper when exchange has no alt coins."""
        session = MockSession(quote=500.0, base=10.0, price=1.0)
        exchange = MockExchange(exchange_base=0.0)
        exchange.testnet = True

        with patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", True), \
             patch.object(config, "EXCHANGE_TESTNET", True):
            result = await mirror_base_from_exchange(session, exchange, tolerance=0.0)
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("skipped"))
        self.assertAlmostEqual(session.engine.position.base, 10.0)


class TestSyncOrderToPaper(unittest.IsolatedAsyncioTestCase):
    async def test_sync_failure_when_insufficient_quote(self):
        session = MockSession(quote=10.0, base=0.0, price=100.0)
        exchange_result = {
            "ok": True,
            "mode": "testnet",
            "order": {
                "symbol": "BTCUSDT",
                "orderId": 1,
                "side": "BUY",
                "executedQty": "0.5",
                "cummulativeQuoteQty": "50",
            },
        }
        result = await sync_order_to_paper(session, exchange_result)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result["ok"])
        self.assertIn("rejected", result["error"].lower())


class TestPaperToExchange(unittest.IsolatedAsyncioTestCase):
    async def test_skips_exchange_origin_trades(self):
        session = MockSession()
        exchange = MockExchange(exchange_base=0.0)
        trade = session.engine.apply_exchange_fill(
            "buy", 100, 0.1, 10, 0, "EXCHANGE TESTNET: order #1",
        )
        assert trade is not None
        with patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", True):
            result = await sync_trade_to_exchange(session, trade, exchange)
        self.assertIsNone(result)

    async def test_syncs_paper_trade_when_enabled(self):
        session = MockSession()
        trade = session.engine.buy(100.0, 25.0, "DCA scheduled")
        assert trade is not None

        class RecordingExchange(MockExchange):
            async def place_market_order(self, *args, **kwargs):
                self.last_call = kwargs
                return {"ok": True, "mode": "live", "order_id": 42, "from_paper_sync": True}

        exchange = RecordingExchange(exchange_base=0.0)
        with patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", True):
            result = await sync_trade_to_exchange(session, trade, exchange)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["ok"])
        self.assertEqual(result["direction"], "paper_to_exchange")
        self.assertTrue(exchange.last_call.get("from_paper_sync"))

    async def test_skips_sell_without_exchange_base(self):
        session = MockSession(base=1.0, price=100.0)
        trade = session.engine.sell(100.0, 0.5, "TAKE-PROFIT")
        assert trade is not None

        class NoBaseExchange(MockExchange):
            async def asset_balance(self, asset: str) -> float:
                return 0.0

            async def _load_symbol_rules(self, symbol: str) -> dict:
                return {"min_notional": 10.0, "step_size": 0.00001, "min_qty": 0.0}

        exchange = NoBaseExchange(exchange_base=0.0)
        with patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", True):
            result = await sync_trade_to_exchange(session, trade, exchange)
        assert result is not None
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("skipped"))

    async def test_clips_buy_over_max_order(self):
        """Grid $80 buy must not fail when EXCHANGE_MAX_ORDER_USD=25."""
        session = MockSession(quote=1000.0, base=0.0, price=100.0)
        trade = session.engine.buy(100.0, 80.0, "GRID buy")
        assert trade is not None

        class CapExchange(MockExchange):
            def order_limits(self):
                return {"max_order_usd": 25.0, "max_daily_loss_pct": 5.0, "max_position_pct": 0.25}

            async def asset_balance(self, asset: str) -> float:
                return 1000.0 if asset == "USDT" else 0.0

            async def place_market_order(self, *args, **kwargs):
                self.last_amount = args[2] if len(args) > 2 else kwargs.get("amount_usd")
                return {"ok": True, "mode": "testnet", "order_id": 7, "from_paper_sync": True}

        exchange = CapExchange(exchange_base=0.0)
        with patch.object(config, "EXCHANGE_SYNC_FROM_PAPER", True):
            result = await sync_trade_to_exchange(session, trade, exchange)
        assert result is not None
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("clipped_to_max"))
        self.assertEqual(exchange.last_amount, 25.0)


if __name__ == "__main__":
    unittest.main()
