"""Market regime detection — gate entries in unfavorable conditions."""

from __future__ import annotations

from typing import Any


def detect_regime(
    price: float,
    sma: float | None,
    closes: list[float] | None = None,
) -> str:
    """
    Return one of: bull, bear, range.
    bear = price below SMA and SMA falling — avoid dip/RSI buys.
    bull = price above SMA with positive short momentum.
    """
    if not price or not sma or sma <= 0:
        return "range"

    sma_diff = (price - sma) / sma * 100
    momentum = 0.0
    if closes and len(closes) >= 5:
        c0, c1 = closes[0], closes[-1]
        if c0 > 0:
            momentum = (c1 - c0) / c0 * 100

    sma_slope = 0.0
    if closes and len(closes) >= 10:
        mid = len(closes) // 2
        early = sum(closes[:mid]) / mid
        late = sum(closes[mid:]) / (len(closes) - mid)
        if early > 0:
            sma_slope = (late - early) / early * 100

    if sma_diff <= -1.5 and (momentum <= -0.3 or sma_slope <= -0.2):
        return "bear"
    if sma_diff >= 1.0 and momentum >= 0.2:
        return "bull"
    return "range"


def regime_blocks_buy(strategy_type: str, regime: str) -> bool:
    """Block counter-trend buys in bear markets for mean-reversion strategies."""
    if regime != "bear":
        return False
    return strategy_type in ("rsi", "dca", "grid")


def candle_closes(candles: list[Any]) -> list[float]:
    out: list[float] = []
    for c in candles or []:
        if isinstance(c, dict):
            v = c.get("close")
        else:
            v = getattr(c, "close", None)
        if v is not None:
            out.append(float(v))
    return out
