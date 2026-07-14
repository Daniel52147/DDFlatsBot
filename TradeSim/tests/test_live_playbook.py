"""Live contingency playbook API."""

from __future__ import annotations

import unittest

from learning.live_playbook import LIVE_PLAYBOOK, build_live_playbook
import config


class TestLivePlaybook(unittest.TestCase):
    def test_all_scenarios_have_plans(self):
        for item in LIVE_PLAYBOOK:
            self.assertIn("plan_a", item)
            self.assertIn("plan_b", item)
            self.assertTrue(item["plan_a"])
            self.assertTrue(item["plan_b"])
            self.assertIn(item["category"], (
                "market", "portfolio", "exchange", "sync", "infra",
                "protections", "user", "monitoring", "escalation", "orders",
            ))

    def test_build_structure(self):
        data = build_live_playbook(risk_status={"portfolio_halt": True, "protections": {}})
        self.assertEqual(data["version"], config.APP_VERSION)
        self.assertGreaterEqual(len(data["categories"]), 8)
        total = sum(c["count"] for c in data["categories"])
        self.assertEqual(total, len(LIVE_PLAYBOOK))
        self.assertIn("max_drawdown", data["active_hints"])

    def test_market_crises_focus(self):
        data = build_live_playbook()
        self.assertGreaterEqual(len(data["market_crises"]), 15)
        self.assertEqual(data["focus"], "market_crises")
        for s in data["market_crises"]:
            self.assertEqual(s["category"], "market")


if __name__ == "__main__":
    unittest.main()
