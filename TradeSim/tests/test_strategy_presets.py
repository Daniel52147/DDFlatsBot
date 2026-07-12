"""Strategy presets shared module tests."""

from __future__ import annotations

import unittest

from learning.strategy_presets import STRATEGY_PRESETS, apply_strategy_preset
from simulator.engine import SimulatorEngine
from simulator.strategies import create_bot


class MockSession:
    def __init__(self, strategy_type: str = "dca"):
        self.symbol = "BTCUSDT"
        self.strategy_type = strategy_type
        self.engine = SimulatorEngine(initial_balance=1000.0)
        self.bot = create_bot(self.engine, strategy_type)

    def set_params_bounded(self, updates: dict):
        merged = {**self.bot.get_params(), **updates}
        self.bot.update_params(merged)


class TestStrategyPresets(unittest.TestCase):
    def test_all_strategy_types_have_presets(self):
        for stype in ("dca", "grid", "momentum", "rsi", "scalper"):
            self.assertIn(stype, STRATEGY_PRESETS)
            self.assertIn("aggressive", STRATEGY_PRESETS[stype])

    def test_apply_aggressive_dca(self):
        session = MockSession("dca")
        base_amount = session.bot.get_params()["dca_amount"]
        self.assertTrue(apply_strategy_preset(session, "aggressive"))
        self.assertGreater(session.bot.get_params()["dca_amount"], base_amount)

    def test_unknown_preset(self):
        session = MockSession("dca")
        self.assertFalse(apply_strategy_preset(session, "unknown"))


if __name__ == "__main__":
    unittest.main()
