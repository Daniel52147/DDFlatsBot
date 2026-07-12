"""Portfolio vs buy-and-hold benchmark — honest, comparable across markets."""

from __future__ import annotations

from typing import Any


def first_buy_price(engine) -> float | None:
    buys = [trade for trade in engine.trades if trade.side == "buy" and trade.price > 0]
    if not buys:
        return None
    earliest_buy = min(buys, key=lambda trade: trade.ts)
    return float(earliest_buy.price)


def candle_anchor_price(session) -> float | None:
    candles = session.candles.all_candles()
    if not candles:
        return None
    return float(candles[0]["close"])


def hold_anchor_price(session) -> tuple[float, str]:
    """
    Price used for buy-and-hold baseline on one market.
    Prefer recent candle window over stale first-tick start_price.
    """
    price = session.feed.price or session.demo_price
    engine = session.engine

    candle_price = candle_anchor_price(session)
    if candle_price and candle_price > 0:
        return candle_price, "candle_anchor"

    buy_price = first_buy_price(engine)
    if buy_price and buy_price > 0:
        return buy_price, "first_buy_anchor"

    if engine.start_price > 0:
        return float(engine.start_price), "tick_anchor"

    return float(price), "current_fallback"


def sync_session_hold_benchmark(session) -> float:
    """Push resolved anchor into engine so per-market vs Hold matches portfolio."""
    hold_price, anchor = hold_anchor_price(session)
    session.engine.benchmark_hold_price = hold_price
    session.engine.benchmark_hold_anchor = anchor
    return hold_price


def sync_all_hold_benchmarks(sessions: dict) -> None:
    for session in sessions.values():
        sync_session_hold_benchmark(session)


def portfolio_benchmark(sessions: dict) -> dict[str, Any]:
    sync_all_hold_benchmarks(sessions)

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

    candle_anchored = anchor_counts.get("candle_anchor", 0)
    market_count = len(sessions)
    if candle_anchored >= market_count * 0.7:
        quality = "high"
    elif candle_anchored >= market_count * 0.4:
        quality = "medium"
    else:
        quality = "low"

    misleading = (
        (abs(vs_hold_pct) > 10 and abs(live_pnl_pct) < 3)
        or (hold_pnl_pct < -15 and abs(live_pnl_pct) < 3)
    )
    note = ""
    if misleading:
        note = (
            "vs Hold считался по старым ценам — теперь по окну свечей (~8ч). "
            "Главная метрика: P&L портфеля."
        )
    elif quality == "low":
        note = "Мало свечей для vs Hold — подожди загрузки графика."

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
        "hold_window": "oldest loaded candle (~8h on 1m chart)",
    }
