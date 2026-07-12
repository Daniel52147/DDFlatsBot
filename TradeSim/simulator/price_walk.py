"""Shared price-walk logic — live bot and Shadow Lab use the same paths."""

from __future__ import annotations

from typing import Any


def ohlc_prices(candle: dict[str, Any]) -> list[float]:
    """Ordered OHLC prices for one closed candle (deduped)."""
    out: list[float] = []
    for key in ("open", "low", "high", "close"):
        p = candle.get(key)
        if p is None or p <= 0:
            continue
        p = float(p)
        if not out or abs(out[-1] - p) > 1e-9:
            out.append(p)
    return out


def prices_for_tick(price: float, closed_candle: dict[str, Any] | None) -> list[float]:
    """On candle close walk OHLC; otherwise single live tick."""
    if closed_candle:
        return ohlc_prices(closed_candle)
    return [price] if price > 0 else []


def run_strategy_prices(bot, prices: list[float], sma: float | None) -> list:
    """Run maybe_trade for each price — returns executed trades in order."""
    trades = []
    for p in prices:
        t = bot.maybe_trade(p, sma)
        if t:
            trades.append(t)
    return trades
