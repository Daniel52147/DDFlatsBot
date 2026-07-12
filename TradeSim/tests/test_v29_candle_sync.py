"""v29 — candle gap sync after restart."""

from __future__ import annotations

import time
import unittest

from simulator.candle_sync import (
    candle_lag_sec,
    gap_start_ts,
    merge_candles,
    needs_backfill,
    normalize_candles,
)
from simulator.candles import CandleBuilder


class TestCandleSync(unittest.TestCase):
    def test_lag_detects_old_last_candle(self):
        step = 60
        now = int(time.time())
        old_bucket = int((now - 7200) // step) * step
        candles = [{"time": old_bucket, "open": 1, "high": 1, "low": 1, "close": 1}]
        self.assertGreater(candle_lag_sec(candles, "1m"), 120)
        self.assertTrue(needs_backfill(candles, "1m", max_lag_sec=120))

    def test_merge_dedupes(self):
        a = [{"time": 100, "open": 1, "high": 2, "low": 0.5, "close": 1.5}]
        b = [{"time": 100, "open": 1, "high": 3, "low": 0.5, "close": 2.0}, {"time": 160, "open": 2, "high": 2.5, "low": 1.8, "close": 2.2}]
        merged = merge_candles(a, b)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["close"], 2.0)

    def test_gap_start(self):
        candles = [{"time": 1000, "open": 1, "high": 1, "low": 1, "close": 1}]
        self.assertEqual(gap_start_ts(candles, "1m"), 1060)

    def test_candle_builder_lag(self):
        cb = CandleBuilder(interval="1m")
        now = int(time.time())
        old = now - 3600
        rows = []
        for i in range(10):
            t = int((old + i * 60) // 60) * 60
            rows.append({"time": t, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1})
        cb.load_history(rows)
        self.assertGreater(cb.lag_sec(), 60)


if __name__ == "__main__":
    unittest.main()
