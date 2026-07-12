"""Portfolio vs buy-and-hold benchmark — honest, comparable across markets."""

from __future__ import annotations

from typing import Any


def hold_anchor_price(session) -> tuple[float, str]:
    """
    Price used for buy-and-hold baseline on one market.
    Prefer candle history over stale first-tick start_price when bot barely traded.
    """
    price = session.feed.price or session.demo_price
    engine = session.engine
    trade_count = len(engine.trades)

    candles = session.candles.all_candles()
    if trade_count == 0 and candles:
        return float(candles[0]["close"]), "candle_anchor"

    if engine.start_price > 0 and trade_count > 0:
        return float(engine.start_price), "trade_anchor"

    if engine.start_price > 0:
        return float(engine.start_price), "tick_anchor"

    if candles:
        return float(candles[0]["close"]), "candle_anchor"

    return float(price), "current_fallback"


def portfolio_benchmark(sessions: dict) -> dict[str, Any]:
    live_total = 0.0
    hold_total = 0.0
    start_total = 0.0
    anchor_counts: dict[str, int] = {}

    for session in sessions.values():
        price = session.feed.price or session.demo_price
        snap = session.engine.snapshot(price)
        live_total += snap["portfolio_value"]
        start_total += session.engine.start_balance

        hold_price, anchor = hold_anchor_price(session)
        anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
        if hold_price > 0:
            hold_total += (session.engine.start_balance / hold_price) * price

    alpha = live_total - hold_total
    alpha_pct = (alpha / start_total * 100) if start_total else 0
    hold_pnl_pct = ((hold_total - start_total) / start_total * 100) if start_total else 0
    live_pnl_pct = ((live_total - start_total) / start_total * 100) if start_total else 0
    vs_hold_pct = live_pnl_pct - hold_pnl_pct

    reliable = anchor_counts.get("trade_anchor", 0) + anchor_counts.get("candle_anchor", 0)
    market_count = len(sessions)
    if reliable >= market_count * 0.7:
        quality = "high"
    elif reliable >= market_count * 0.4:
        quality = "medium"
    else:
        quality = "low"

    misleading = abs(vs_hold_pct) > 15 and abs(live_pnl_pct) < 2
    note = ""
    if misleading:
        note = (
            "vs Hold завышен: бот в основном в кэше, hold считает покупку по старым ценам. "
            "Смотри P&L, не только vs Hold."
        )
    elif quality == "low":
        note = "Мало данных для честного vs Hold — нужны сделки или свечи."

    return {
        "live_value": round(live_total, 2),
        "hold_value": round(hold_total, 2),
        "start_value": round(start_total, 2),
        "alpha_usd": round(alpha, 2),
        "alpha_pct": round(alpha_pct, 2),
        "live_pnl_pct": round(live_pnl_pct, 2),
        "hold_pnl_pct": round(hold_pnl_pct, 2),
        "vs_hold_pct": round(vs_hold_pct, 2),
        "benchmark_quality": quality,
        "benchmark_misleading": misleading,
        "benchmark_note": note,
        "anchor_counts": anchor_counts,
    }
