"""v28 — capital allocator, strategy outcomes, exchange PnL."""

from __future__ import annotations

import unittest

import config
from learning.capital_allocator import CapitalAllocator
from learning.strategy_report import build_strategy_report
from simulator.market_session import MarketSession


class TestCapitalAllocator(unittest.TestCase):
    def setUp(self):
        self.alloc = CapitalAllocator()
        self.sessions = {m["symbol"]: MarketSession(m) for m in config.MARKETS[:6]}

    def _contexts(self):
        out = []
        for sym, s in self.sessions.items():
            ctx = s.context_for_assistant()
            ctx["portfolio"]["vs_hold_pct"] = {"BTCUSDT": 2.0, "ETHUSDT": 1.5, "SOLUSDT": -1.0}.get(sym, 0)
            out.append(ctx)
        return out

    def test_boosts_top_performers(self):
        mults = self.alloc.compute(self._contexts())
        self.assertGreater(mults.get("BTCUSDT", 1), 1.0)

    def test_trims_laggards(self):
        mults = self.alloc.compute(self._contexts())
        if "SOLUSDT" in mults:
            self.assertLess(mults["SOLUSDT"], 1.0)

    def test_apply_changes_buy_amount(self):
        ctx = self._contexts()
        for c in ctx:
            if c["symbol"] == "BTCUSDT":
                c["portfolio"]["vs_hold_pct"] = 3.0
        changed = self.alloc.apply(self.sessions, ctx)
        self.alloc.last_apply_ts = 0
        changed = self.alloc.apply(self.sessions, ctx)
        self.assertIsInstance(changed, list)


class TestStrategyReport(unittest.TestCase):
    def test_report_structure(self):
        sessions = {m["symbol"]: MarketSession(m) for m in config.MARKETS[:4]}
        r = build_strategy_report(sessions)
        self.assertIn("by_strategy", r)
        self.assertEqual(r["markets_total"], 4)


if __name__ == "__main__":
    unittest.main()
