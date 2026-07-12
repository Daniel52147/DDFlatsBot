"""v35 — profit focus engine (pause losers, boost leaders)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import config
from learning.profit_focus import ProfitFocusEngine, apply_profit_max_startup
from simulator.engine import SimulatorEngine
from simulator.strategy import StrategyBot


def _session(sym: str, label: str, vs_hold: float, pnl_pct: float, trades: int, enabled: bool = True):
    engine = SimulatorEngine(initial_balance=1000)
    for _ in range(trades):
        engine._trade_counter += 1
        engine.trades.append(MagicMock())
    bot = StrategyBot(engine, params={
        "dca_amount": 20.0,
        "dca_interval_hours": 8,
        "dip_threshold_pct": 3.0,
        "dip_extra_amount": 30.0,
        "max_buy_pct_of_cash": 0.5,
    })
    session = MagicMock()
    session.symbol = sym
    session.label = label
    session.strategy_type = "dca"
    session.demo_price = 100.0
    session.feed = MagicMock(price=100.0)
    session.bot = bot
    session.bot.enabled = enabled
    session.base_params = {"dca_amount": 20.0}
    session.set_params_bounded = lambda p: bot.update_params(p)
    snap = {
        "vs_hold_pct": vs_hold,
        "pnl_pct": pnl_pct,
        "trade_count": trades,
    }
    session.engine.snapshot = MagicMock(return_value=snap)
    return session


class TestProfitFocusEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ProfitFocusEngine()
        self.engine.last_run_ts = 0

    def test_pauses_laggard(self):
        s = _session("SOLUSDT", "SOL", vs_hold=-3.0, pnl_pct=-2.0, trades=3)
        actions = self.engine.review({"SOLUSDT": s})
        self.assertFalse(s.bot.enabled)
        self.assertTrue(any(a["action"] == "pause" for a in actions))
        self.assertIn("SOLUSDT", self.engine.paused)

    def test_resumes_on_recovery(self):
        s = _session("SOLUSDT", "SOL", vs_hold=0.5, pnl_pct=0.6, trades=3, enabled=False)
        self.engine.paused["SOLUSDT"] = "vs hold -3.0%"
        actions = self.engine.review({"SOLUSDT": s})
        self.assertTrue(s.bot.enabled)
        self.assertTrue(any(a["action"] == "resume" for a in actions))
        self.assertNotIn("SOLUSDT", self.engine.paused)

    def test_boosts_leader(self):
        good = _session("BTCUSDT", "BTC", vs_hold=2.0, pnl_pct=1.5, trades=4)
        bad = _session("ETHUSDT", "ETH", vs_hold=-0.5, pnl_pct=0.0, trades=2)
        with patch.object(config, "PROFIT_FOCUS_LEADER_MULT", 1.2):
            actions = self.engine.review({"BTCUSDT": good, "ETHUSDT": bad})
        self.assertTrue(any(a["action"] == "boost" and a["symbol"] == "BTCUSDT" for a in actions))
        self.assertGreater(good.bot.get_params()["dca_amount"], 20.0)

    def test_status_shape(self):
        s = _session("BTCUSDT", "BTC", vs_hold=1.0, pnl_pct=0.5, trades=2)
        st = self.engine.status({"BTCUSDT": s})
        self.assertIn("leaders", st)
        self.assertIn("laggards", st)
        self.assertTrue(st["enabled"])

    def test_apply_profit_max_startup(self):
        sessions = {m["symbol"]: MagicMock() for m in config.MARKETS[:3]}
        with patch.object(config, "PROFIT_MAX_ON_START", True):
            with patch("learning.trade_mode.apply_active_all") as mock_active:
                apply_profit_max_startup(sessions)
                mock_active.assert_called_once_with(sessions, reset_timers=False)

    def test_api_profit_focus(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        r = client.get("/api/profit-focus")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("enabled", data)


if __name__ == "__main__":
    unittest.main()
