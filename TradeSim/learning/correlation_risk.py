"""Portfolio correlation risk — block correlated bearish buying."""

from __future__ import annotations

from typing import Any

import config


def _close(candle: Any) -> float | None:
    if isinstance(candle, dict):
        v = candle.get("close")
    else:
        v = getattr(candle, "close", None)
    return float(v) if v is not None else None


def market_momentum(ctx: dict[str, Any], lookback: int = 5) -> float | None:
    candles = ctx.get("candles") or []
    if len(candles) < lookback:
        return None
    closes = [_close(c) for c in candles[-lookback:]]
    if not closes[0] or closes[0] <= 0:
        return None
    return (closes[-1] - closes[0]) / closes[0] * 100


def assess_correlation_risk(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Detect synchronized bearish moves across many markets.
    When too many coins fall together, new buys add correlated risk.
    """
    if not config.CORRELATION_RISK_ENABLED or len(contexts) < 3:
        return {
            "block_buys": False,
            "bearish_markets": 0,
            "bullish_markets": 0,
            "sync_pairs": 0,
            "reason": "",
        }

    threshold = config.CORRELATION_RISK_MOMENTUM_PCT
    bearish = 0
    bullish = 0
    momentums: list[tuple[str, float]] = []

    for ctx in contexts:
        mom = market_momentum(ctx)
        if mom is None:
            continue
        momentums.append((ctx.get("label", "?"), mom))
        if mom <= -threshold:
            bearish += 1
        elif mom >= threshold:
            bullish += 1

    sync_pairs = 0
    for i, (_, ma) in enumerate(momentums):
        for _, mb in momentums[i + 1:]:
            if ma < -threshold and mb < -threshold:
                sync_pairs += 1

    block = bearish >= config.CORRELATION_RISK_MIN_BEARISH
    if sync_pairs >= config.CORRELATION_RISK_MIN_SYNC_PAIRS:
        block = True

    reason = ""
    if block:
        reason = (
            f"корреляция: {bearish} рынков падают синхронно "
            f"(порог −{threshold}%, пар {sync_pairs})"
        )

    return {
        "block_buys": block,
        "bearish_markets": bearish,
        "bullish_markets": bullish,
        "sync_pairs": sync_pairs,
        "reason": reason,
    }
