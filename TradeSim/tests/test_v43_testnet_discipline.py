"""v43 — testnet discipline and brain aggression respect."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import config
from learning.profit_focus import ProfitFocusEngine
from learning.testnet_mode import apply_testnet_conservative_trading
from simulator.engine import SimulatorEngine
from simulator.risk_gate import brain_reduce_aggression, set_brain_reduce_aggression
from simulator.strategy import StrategyBot


class TestTestnetDiscipline(unittest.TestCase):
    def test_conservative_raises_dca_interval(self):
        engine = SimulatorEngine(initial_balance=1000)
        bot = StrategyBot(engine, params={
            "dca_amount": 40,
            "dca_interval_hours": 1.5,
            "dip_threshold_pct": 2.0,
            "dip_extra_amount": 30.0,
            "dip_cooldown_minutes": 5,
            "max_buy_pct_of_cash": 0.5,
        })
        session = MagicMock()
        session.symbol = "BTCUSDT"
        session.label = "BTC"
        session.strategy_type = "dca"
        session.bot = bot
        session.set_params_bounded = lambda p: bot.update_params(p)
        session.sync_base_params = lambda: None

        info = apply_testnet_conservative_trading(session, reset_timers=True)
        self.assertGreaterEqual(
            info["params"]["dca_interval_hours"],
            config.TESTNET_MIN_DCA_HOURS,
        )

    def test_brain_reduce_doubles_dca_interval(self):
        set_brain_reduce_aggression(True)
        self.assertTrue(brain_reduce_aggression())
        set_brain_reduce_aggression(False)

    def test_profit_focus_pauses_on_vs_hold_alone(self):
        engine = ProfitFocusEngine()
        engine.last_run_ts = 0
        session = MagicMock()
        session.symbol = "PEPEUSDT"
        session.label = "PEPE"
        session.bot = MagicMock(enabled=True)
        session.feed = MagicMock(price=1.0)
        session.demo_price = 1.0
        session.engine.snapshot = MagicMock(return_value={
            "vs_hold_pct": -3.2,
            "pnl_pct": 0.1,
            "trade_count": 5,
        })
        with unittest.mock.patch("learning.paper_learn_mode.is_paper_learn_mode", return_value=False):
            actions = engine.review({"PEPEUSDT": session})
        self.assertTrue(any(a["action"] == "pause" for a in actions))
        self.assertFalse(session.bot.enabled)


if __name__ == "__main__":
    unittest.main()
