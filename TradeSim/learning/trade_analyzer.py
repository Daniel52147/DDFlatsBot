"""Analyze trade patterns and suggest parameter adjustments."""

from __future__ import annotations

from collections import Counter
from typing import Any


def _reason_kind(reason: str) -> str:
    r = (reason or "").upper()
    if "SPIKE" in r:
        return "spike"
    if "DIP" in r:
        return "dip"
    if "DCA" in r:
        return "dca"
    if "TAKE-PROFIT" in r or "TAKE PROFIT" in r:
        return "tp"
    return "other"


def analyze_trades(
    trades: list[dict[str, Any]],
    vs_hold_pct: float,
    pnl_pct: float,
    volatility_pct: float,
    volatile: bool,
) -> dict[str, float]:
    """Return suggested parameter deltas based on what worked."""
    deltas: dict[str, float] = {}
    if not trades:
        return deltas

    kinds = Counter(_reason_kind(t.get("reason", "")) for t in trades)
    buys = sum(1 for t in trades if t.get("side") == "buy")
    sells = sum(1 for t in trades if t.get("side") == "sell")

    # Losing vs buy-and-hold — buy smarter, not just more
    if vs_hold_pct < -2:
        deltas["dip_threshold_pct"] = -0.8
        deltas["dca_amount"] = -4 if volatile else -6
        if volatile:
            deltas["spike_threshold_pct"] = -1.5
            deltas["dca_interval_hours"] = -1
    elif vs_hold_pct < 0:
        deltas["dip_threshold_pct"] = -0.4
        deltas["dca_amount"] = -3

    # Winning — lock gains, stay disciplined
    elif vs_hold_pct > 1.5:
        deltas["dip_threshold_pct"] = 0.4
        if volatile:
            deltas["take_profit_pct"] = -0.8
            deltas["take_profit_fraction"] = 0.03
        if pnl_pct > 2 and sells < max(1, buys // 4):
            deltas["take_profit_pct"] = deltas.get("take_profit_pct", 0) - 0.5

    # Pattern: many DIPs but still losing — DIPs too early
    if kinds["dip"] >= 3 and vs_hold_pct < 0 and kinds["dip"] > kinds["spike"]:
        deltas["dip_threshold_pct"] = deltas.get("dip_threshold_pct", 0) + 0.5

    # Pattern: SPIKE trades helped
    if kinds["spike"] >= 2 and vs_hold_pct >= 0:
        deltas["spike_extra_amount"] = 3 if volatile else 5

    # High volatility + losing — react faster
    if volatile and volatility_pct >= 8 and vs_hold_pct < 0:
        deltas["dip_threshold_pct"] = deltas.get("dip_threshold_pct", 0) - 0.3
        deltas["take_profit_cooldown_hours"] = -0.5

    # No take-profits while up — fix that
    if pnl_pct > 1 and sells == 0 and buys >= 3:
        deltas["take_profit_pct"] = deltas.get("take_profit_pct", 0) - 1.0

    return deltas
