"""v49 — limit orders and agent chatroom."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import config
from assistant.chatroom import build_chatroom, build_chatroom_history
from simulator.engine import SimulatorEngine
from simulator.limit_orders import LimitOrderBook


class TestLimitOrderBook(unittest.TestCase):
    def setUp(self):
        from learning.protections import protections_engine
        from simulator.risk_gate import set_correlation_block, set_portfolio_halt
        protections_engine.clear_all()
        set_portfolio_halt(False)
        set_correlation_block(False)
        self.book = LimitOrderBook("BTCUSDT")
        self.engine = SimulatorEngine(1000.0)
        self.engine.market_symbol = "BTCUSDT"

    def test_limit_buy_fills_on_dip(self):
        order = self.book.add("buy", 50.0, 99.0, reason="test dip")
        self.assertEqual(len(self.book.orders), 1)
        fills = self.book.check_fills(100.0, self.engine)
        self.assertEqual(len(fills), 0)
        fills = self.book.check_fills(98.5, self.engine)
        self.assertEqual(len(fills), 1)
        self.assertEqual(len(self.book.orders), 0)

    def test_cancel(self):
        order = self.book.add("sell", 30.0, 105.0)
        self.assertTrue(self.book.cancel(order.id))
        self.assertEqual(len(self.book.orders), 0)


class TestAgentChatroom(unittest.TestCase):
    def test_build_chatroom_has_brain_message(self):
        cycle = {
            "ts": 1,
            "decision": "continue",
            "verdict": "Всё OK",
            "mentor": {
                "emoji": "🎓",
                "name": "Наставник",
                "summary": "Держим курс",
                "recommendation": "continue",
                "confidence": 0.8,
            },
        }
        room = build_chatroom(cycle)
        self.assertEqual(room["decision"], "continue")
        self.assertGreaterEqual(len(room["messages"]), 2)
        self.assertEqual(room["messages"][-1]["role"], "brain")

    def test_history_from_db_rows(self):
        rows = build_chatroom_history([
            {"ts": 1, "decision": "hold", "verdict": "Ждём"},
        ])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], "hold")


if __name__ == "__main__":
    unittest.main()
