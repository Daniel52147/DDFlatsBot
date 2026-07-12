"""v42 — Paper Learn scorecard benchmarks."""

from __future__ import annotations

import unittest

from learning.scorecard import build_scorecard, _grade_trades, _grade_pnl


class TestScorecard(unittest.TestCase):
    def test_grade_trades(self):
        self.assertEqual(_grade_trades(5), "bad")
        self.assertEqual(_grade_trades(50), "ok")
        self.assertEqual(_grade_trades(120), "good")

    def test_grade_pnl(self):
        self.assertEqual(_grade_pnl(-6), "bad")
        self.assertEqual(_grade_pnl(1), "ok")
        self.assertEqual(_grade_pnl(4), "good")

    def test_build_scorecard_paper_learn(self):
        sc = build_scorecard(
            total={"pnl_pct": 0.5, "vs_hold_pct": 0.2, "drawdown_pct": 4, "total_value": 10050},
            trade_count=45,
            readiness={"score_pct": 55},
            trading_mode="paper",
        )
        self.assertIn("metrics", sc)
        self.assertEqual(len(sc["metrics"]), 5)
        self.assertIn("next_steps", sc)

    def test_api_scorecard(self):
        from fastapi.testclient import TestClient
        import main

        client = TestClient(main.app)
        r = client.get("/api/scorecard")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("overall_grade", data)
        self.assertIn("benchmarks", data)


if __name__ == "__main__":
    unittest.main()
