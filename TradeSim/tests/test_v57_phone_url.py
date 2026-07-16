"""Phone / LAN dashboard URL."""

from __future__ import annotations

import unittest

from simulator.network_util import dashboard_url, detect_lan_ipv4


class TestNetworkUtil(unittest.TestCase):
    def test_dashboard_prefers_lan_over_localhost(self):
        url = dashboard_url(public_url="", port=8765, prefer_lan=True)
        self.assertTrue(url.startswith("http://"))
        self.assertNotIn("127.0.0.1", url) or detect_lan_ipv4() is None

    def test_explicit_public_url(self):
        self.assertEqual(
            dashboard_url(public_url="http://192.168.1.50:8765", port=8765),
            "http://192.168.1.50:8765",
        )


if __name__ == "__main__":
    unittest.main()
