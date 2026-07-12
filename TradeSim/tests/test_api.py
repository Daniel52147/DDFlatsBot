"""API integration tests — FastAPI TestClient."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

import config
from main import app


class TestApiEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_ping(self):
        r = self.client.get("/api/ping")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["version"], config.APP_VERSION)
        self.assertGreaterEqual(data["markets_count"], 1)

    def test_health_json(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["version"], config.APP_VERSION)
        self.assertIn("markets_active", data)

    def test_health_html(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"TradeSim", r.content)

    def test_strategies(self):
        r = self.client.get("/api/strategies")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["strategies"]), 5)

    def test_bootstrap(self):
        r = self.client.get("/api/bootstrap")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("markets", data)
        self.assertIn("total", data)

    def test_shadow_lab(self):
        r = self.client.get("/api/shadow-lab")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("enabled", data)

    def test_benchmark(self):
        r = self.client.get("/api/benchmark")
        self.assertEqual(r.status_code, 200)
        self.assertIn("vs_hold_pct", r.json())

    def test_exchange_status(self):
        r = self.client.get("/api/exchange/status")
        self.assertEqual(r.status_code, 200)
        self.assertIn("enabled", r.json())

    def test_auto_tactics(self):
        r = self.client.get("/api/auto-tactics")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("enabled", data)
        self.assertIn("markets", data)

    def test_sync_paper_endpoint(self):
        r = self.client.post("/api/exchange/sync-paper?symbol=BTCUSDT")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("ok", data)

    def test_bootstrap_has_auto_tactics(self):
        r = self.client.get("/api/bootstrap")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("auto_tactics", data)
        self.assertIn("markets", data["auto_tactics"])


if __name__ == "__main__":
    unittest.main()
