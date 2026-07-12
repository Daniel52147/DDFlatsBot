"""v32 — active trading mode (more trades)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from learning.trade_mode import apply_active_trading
from simulator.engine import SimulatorEngine
from simulator.strategy import StrategyBot


class TestActiveTradeMode(unittest.TestCase):
    def test_lowers_dca_interval(self):
        engine = SimulatorEngine(initial_balance=1000)
        bot = StrategyBot(engine, params={
            "dca_interval_hours": 24,
            "dip_cooldown_minutes": 30,
            "dip_threshold_pct": 3.0,
            "dca_amount": 25,
            "dip_extra_amount": 40,
            "max_buy_pct_of_cash": 0.5,
        })
        session = MagicMock()
        session.symbol = "BTCUSDT"
        session.label = "BTC"
        session.strategy_type = "dca"
        session.bot = bot
        session.set_params_bounded = lambda p: bot.update_params(p)

        info = apply_active_trading(session)
        params = info["params"]
        self.assertLess(params["dca_interval_hours"], 8)
        self.assertLess(params["dip_cooldown_minutes"], 15)
        self.assertIn("spike_threshold_pct", params)

    def test_api_active_all(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        r = client.post("/api/strategy/active", json={"reset_timers": True})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data.get("ok"))
        self.assertGreaterEqual(data.get("count", 0), 1)


if __name__ == "__main__":
    unittest.main()
