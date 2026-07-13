"""v39 — paper learn mode (more trades for faster learning)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import config
from learning.paper_learn_mode import apply_paper_learn_trading, effective_min_trades_for_tuning
from simulator.engine import SimulatorEngine
from simulator.strategy import StrategyBot


class TestPaperLearnMode(unittest.TestCase):
    def test_lowers_dca_below_two_hours(self):
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
        session.set_params_bounded = lambda params: bot.update_params(params)

        with patch("learning.paper_learn_mode.is_paper_learn_mode", return_value=True):
            info = apply_paper_learn_trading(session, reset_timers=True)
        self.assertLessEqual(info["params"]["dca_interval_hours"], config.PAPER_LEARN_DCA_MAX_HOURS)
        self.assertLessEqual(info["params"]["scalp_cooldown_seconds"], config.PAPER_LEARN_SCALP_COOLDOWN_SEC)

    def test_min_trades_lower_in_paper(self):
        with patch("learning.paper_learn_mode.is_paper_learn_mode", return_value=True):
            self.assertEqual(effective_min_trades_for_tuning(), config.PAPER_LEARN_MIN_TRADES_TUNING)

    def test_api_paper_learn(self):
        from fastapi.testclient import TestClient
        import main

        with patch.object(type(main.trading_mode), "mode", new_callable=PropertyMock) as mock_mode:
            mock_mode.return_value = "paper"
            client = TestClient(main.app)
            response = client.post("/api/strategy/paper-learn", json={"reset_timers": True})
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data.get("mode"), "paper_learn")
            btc = next(m for m in data["markets"] if m["symbol"] == "BTCUSDT")
            self.assertLessEqual(
                btc["params"]["dca_interval_hours"],
                config.PAPER_LEARN_DCA_MAX_HOURS,
            )


if __name__ == "__main__":
    unittest.main()
