"""Candle gap detection and history merge — keep charts current after restart."""

from __future__ import annotations

import time
from typing import Any

INTERVAL_SEC = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}


def interval_seconds(interval: str) -> int:
    return INTERVAL_SEC.get(interval, 60)


def normalize_candles(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by time, dedupe buckets, keep last row per bucket."""
    if not candles:
        return []
    by_time: dict[int, dict[str, Any]] = {}
    for c in candles:
        t = int(c.get("time") or 0)
        if t <= 0:
            continue
        by_time[t] = {
            "time": t,
            "open": float(c["open"]),
            "high": float(c["high"]),
            "low": float(c["low"]),
            "close": float(c["close"]),
            "volume": float(c.get("volume") or 0),
        }
    return [by_time[t] for t in sorted(by_time)]


def last_bucket_time(candles: list[dict[str, Any]]) -> int | None:
    rows = normalize_candles(candles)
    if not rows:
        return None
    return int(rows[-1]["time"])


def candle_lag_sec(candles: list[dict[str, Any]], interval: str = "1m", now: float | None = None) -> float:
    """Seconds since last candle bucket open (0 = current minute)."""
    last = last_bucket_time(candles)
    if last is None:
        return 999999.0
    now_ts = now if now is not None else time.time()
    step = interval_seconds(interval)
    current_bucket = int(now_ts // step) * step
    return max(0.0, float(current_bucket - last))


def merge_candles(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined = normalize_candles([*existing, *incoming])
    return combined


def needs_backfill(
    candles: list[dict[str, Any]],
    interval: str = "1m",
    max_lag_sec: float = 120,
    now: float | None = None,
) -> bool:
    return candle_lag_sec(candles, interval, now) > max_lag_sec


def gap_start_ts(
    candles: list[dict[str, Any]],
    interval: str = "1m",
) -> int | None:
    """Binance startTime (seconds) for candles after last known bucket."""
    last = last_bucket_time(candles)
    if last is None:
        return None
    return last + interval_seconds(interval)
