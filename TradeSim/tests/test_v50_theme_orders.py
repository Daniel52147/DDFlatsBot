"""v50 — theme config and orders cancel API."""

from __future__ import annotations

import unittest

import config


class TestV50Config(unittest.TestCase):
    def test_version(self):
        self.assertEqual(config.APP_VERSION, 58)

    def test_limit_orders_still_enabled(self):
        self.assertTrue(config.LIMIT_ORDERS_ENABLED)

    def test_theme_default(self):
        self.assertIn(config.UI_THEME_DEFAULT, ("dark", "light"))


if __name__ == "__main__":
    unittest.main()
