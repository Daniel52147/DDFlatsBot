"""v27 — walk-forward shadow, strategy report, correlation risk."""

from __future__ import annotations

import unittest

import config
from learning.correlation_risk import assess_correlation_risk, market_momentum
from learning.strategy_report import build_strategy_report
from learning.walkforward import walkforward_validate
from simulator.engine import SimulatorEngine
from simulator.market_session import MarketSession
from simulator.risk_gate import blocks_new_buys, set_correlation_block, set_portfolio_halt


def _chop_candles(n: int, start: float = 100.0) -> list[dict]:
    candles = []
    price = start
    for i in range(n):
        price += 0.02 if i % 3 else -0.01
        candles.append({
            "time": i * 60,
            "open": price,
            "high": price + 0.05,
            "low": price - 0.05,
            "close": price,
        })
    return candles


class TestWalkforward(unittest.TestCase):
    def test_insufficient_candles_passes(self):
        ok, note, _ = walkforward_validate([], "dca", {}, {})
        self.assertTrue(ok)

    def test_runs_on_enough_candles(self):
        candles = _chop_candles(100)
        params = dict(config.STRATEGY)
        ok, note, metrics = walkforward_validate(candles, "dca", params, params)
        self.assertIn("test_candles", metrics)
        self.assertGreater(metrics["test_candles"], 10)
        # Identical params → zero edge → blocked (expected)
        self.assertFalse(ok)


class TestCorrelationRisk(unittest.TestCase):
    def test_blocks_many_bearish_markets(self):
        contexts = []
        for i in range(10):
            contexts.append({
                "label": f"M{i}",
                "candles": [{"close": 100 - j * 2} for j in range(6)],
            })
        r = assess_correlation_risk(contexts)
        self.assertTrue(r["block_buys"])
        self.assertGreaterEqual(r["bearish_markets"], config.CORRELATION_RISK_MIN_BEARISH)

    def test_momentum_from_dict_candles(self):
        ctx = {"candles": [{"close": 100}, {"close": 99}, {"close": 98}, {"close": 97}, {"close": 96}]}
        mom = market_momentum(ctx)
        self.assertIsNotNone(mom)
        self.assertLess(mom, 0)


class TestStrategyReport(unittest.TestCase):
    def test_build_report(self):
        sessions = {m["symbol"]: MarketSession(m) for m in config.MARKETS[:3]}
        report = build_strategy_report(sessions)
        self.assertEqual(report["markets_total"], 3)
        self.assertGreater(len(report["by_strategy"]), 0)
        self.assertIn("leader", report)


class TestRiskGateCorrelation(unittest.TestCase):
    def test_correlation_block(self):
        set_portfolio_halt(False)
        set_correlation_block(False)
        eng = SimulatorEngine(initial_balance=500)
        self.assertIsNotNone(eng.buy(100, 20, "ok"))
        set_correlation_block(True, "sync bear")
        self.assertTrue(blocks_new_buys())
        self.assertIsNone(eng.buy(100, 20, "blocked"))
        set_correlation_block(False)


if __name__ == "__main__":
    unittest.main()
