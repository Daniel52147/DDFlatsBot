"""OHLCV candle builder from live ticks."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from simulator.candle_sync import candle_lag_sec, merge_candles, normalize_candles

INTERVAL_SECONDS = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "1h": 3600,
}


@dataclass
class Candle:
  time: int
  open: float
  high: float
  low: float
  close: float
  volume: float = 0.0

  def to_dict(self) -> dict[str, Any]:
    return {
      "time": self.time,
      "open": self.open,
      "high": self.high,
      "low": self.low,
      "close": self.close,
      "volume": self.volume,
    }


class CandleBuilder:
  def __init__(self, interval: str = "1m", max_candles: int = 500):
    self.interval = interval
    self.interval_sec = INTERVAL_SECONDS.get(interval, 60)
    self.max_candles = max_candles
    self.candles: list[Candle] = []
    self._current: Candle | None = None

  def _bucket_start(self, ts: float) -> int:
    return int(ts // self.interval_sec) * self.interval_sec

  def add_tick(self, price: float, ts: float | None = None) -> Candle | None:
    ts = ts or time.time()
    bucket = self._bucket_start(ts)
    closed = None

    if self._current is None:
      self._current = Candle(time=bucket, open=price, high=price, low=price, close=price)
      return None

    if bucket > self._current.time:
      closed = self._current
      self.candles.append(closed)
      if len(self.candles) > self.max_candles:
        self.candles = self.candles[-self.max_candles :]
      self._current = Candle(time=bucket, open=price, high=price, low=price, close=price)
      return closed

    c = self._current
    c.high = max(c.high, price)
    c.low = min(c.low, price)
    c.close = price
    c.volume += 1
    return None

  def load_history(self, candles: list[dict]):
    rows = normalize_candles(candles)
    self.candles = [
      Candle(
        time=c["time"],
        open=c["open"],
        high=c["high"],
        low=c["low"],
        close=c["close"],
        volume=c.get("volume", 0),
      )
      for c in rows
    ]
    if self.candles:
      last = self.candles.pop()
      self._current = Candle(
        time=last.time,
        open=last.open,
        high=last.high,
        low=last.low,
        close=last.close,
        volume=last.volume,
      )
    else:
      self._current = None

  def merge_history(self, candles: list[dict]) -> int:
    """Append/replace candles from API backfill. Returns rows merged."""
    existing = [c.to_dict() for c in self.candles]
    if self._current:
      existing.append(self._current.to_dict())
    merged = merge_candles(existing, candles)
    before = len(self.all_candles())
    self.load_history(merged)
    return max(0, len(self.all_candles()) - before)

  def lag_sec(self) -> float:
    return candle_lag_sec(self.all_candles(), self.interval)

  def last_time(self) -> int | None:
    all_c = self.all_candles()
    return int(all_c[-1]["time"]) if all_c else None

  def current_candle(self) -> dict[str, Any] | None:
    return self._current.to_dict() if self._current else None

  def all_candles(self) -> list[dict]:
    out = [c.to_dict() for c in self.candles]
    if self._current:
      out.append(self._current.to_dict())
    return out

  def sma(self, period: int) -> float | None:
    closes = [c.close for c in self.candles]
    if self._current:
      closes.append(self._current.close)
    if len(closes) < period:
      return None
    return sum(closes[-period:]) / period

  def last_n(self, n: int) -> list[Candle]:
    all_c = self.candles.copy()
    if self._current:
      all_c.append(self._current)
    return all_c[-n:]
