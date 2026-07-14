"""v56 — Live coach, sync watcher, crisis guard agents."""

from __future__ import annotations

import unittest

from assistant.crisis_guard import CrisisGuardAgent
from assistant.live_coach import LiveCoachAgent
from assistant.sync_watcher import SyncWatcherAgent


class TestNewBrainAgents(unittest.TestCase):
    def test_live_coach_warns_zero_exchange_orders(self):
        agent = LiveCoachAgent()
        rep = agent.analyze([], {"pnl_pct": 50}, meta={
            "trading_mode": "testnet",
            "live_readiness": {"score_pct": 67, "ready_for_live": False, "checks": []},
            "live_prep": {
                "phase_progress": "2/5",
                "stability": {"exchange_orders": 0, "success_rate_pct": 100},
            },
        })
        self.assertEqual(rep["agent"], "live_coach")
        self.assertIn("collect_data", rep["recommendation"])
        self.assertTrue(any("Ордеров" in x for x in rep.get("lessons", [])))

    def test_sync_watcher_critical_on_low_sync(self):
        agent = SyncWatcherAgent()
        rep = agent.analyze([], {}, meta={
            "live_prep": {"stability": {"success_rate_pct": 70, "sync_failures": 5, "exchange_orders": 2}},
            "reconcile": {"markets": [{"symbol": "BTCUSDT", "base_diff": 0.98}]},
        })
        self.assertEqual(rep["recommendation"], "reduce_aggression")
        self.assertTrue(rep.get("critical"))

    def test_crisis_guard_pause_on_halt(self):
        agent = CrisisGuardAgent()
        rep = agent.analyze([], {"pnl_pct": -5}, meta={
            "risk_gate": {"portfolio_halt": True, "correlation_block": False},
            "protections": {},
            "correlation_risk": {},
        })
        self.assertIn("portfolio_halt", rep.get("scenarios", []))
        self.assertEqual(rep["recommendation"], "pause_dip")


if __name__ == "__main__":
    unittest.main()
