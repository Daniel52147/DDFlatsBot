"""FeedHub REST fallback tests."""

from __future__ import annotations

import unittest

from simulator.feed_hub import FeedHub


class MockFeed:
    def __init__(self, price: float = 65000.0):
        self.price = 0.0
        self.source = "bybit"
        self.last_update = 0.0
        self._price = price

    async def fetch_price(self) -> float:
        return self._price

    async def _set_price(self, price: float, source: str) -> float:
        self.price = price
        self.source = source
        return price

    async def _notify(self, price: float, ts: float) -> None:
        self.last_update = ts


class TestFeedHubRestFallback(unittest.IsolatedAsyncioTestCase):
    async def test_rest_poll_dispatches_prices(self):
        hub = FeedHub(["BTCUSDT"])
        feed = MockFeed(65000.0)
        hub.register("BTCUSDT", feed)
        hub._running = True

        await hub._rest_poll_all()

        self.assertAlmostEqual(feed.price, 65000.0)
        self.assertEqual(feed.source, "hub-rest-bybit")


if __name__ == "__main__":
    unittest.main()
