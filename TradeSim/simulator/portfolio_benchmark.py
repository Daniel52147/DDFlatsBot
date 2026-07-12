"""Portfolio vs buy-and-hold benchmark — lifetime anchor since session start / first buy."""

from __future__ import annotations

from typing import Any

LOCKED_HOLD_ANCHORS = frozenset({
    "first_buy_anchor",
    "lifetime_anchor",
    "tick_anchor",
    "persisted",
})


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
    Lifetime buy-and-hold baseline for one market.
    Priority: first buy → session start tick → candle window → current price.
    """
    price = session.feed.price or session.demo_price
    engine = session.engine

    buy_price = first_buy_price(engine)
    if buy_price and buy_price > 0:
        return buy_price, "first_buy_anchor"

    if engine.start_price > 0:
        return float(engine.start_price), "lifetime_anchor"

    candle_price = candle_anchor_price(session)
    if candle_price and candle_price > 0:
        return candle_price, "candle_anchor"

    return float(price), "current_fallback"


def sync_session_hold_benchmark(session) -> float:
    """Set hold anchor once; never downgrade locked lifetime anchors."""
    hold_price, anchor = hold_anchor_price(session)
    eng = session.engine

    if eng.benchmark_hold_anchor in LOCKED_HOLD_ANCHORS and eng.benchmark_hold_price > 0:
        return eng.benchmark_hold_price

    if anchor in LOCKED_HOLD_ANCHORS or eng.benchmark_hold_price <= 0:
        eng.benchmark_hold_price = hold_price
        eng.benchmark_hold_anchor = anchor
    elif eng.benchmark_hold_anchor == "candle_anchor" and anchor in LOCKED_HOLD_ANCHORS:
        eng.benchmark_hold_price = hold_price
        eng.benchmark_hold_anchor = anchor

    return eng.benchmark_hold_price


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

        hold_price = session.engine.benchmark_hold_price or hold_anchor_price(session)[0]
        anchor = session.engine.benchmark_hold_anchor or hold_anchor_price(session)[1]
        anchor_counts[anchor] = anchor_counts.get(anchor, 0) + 1
        if hold_price > 0:
            hold_total += (session.engine.start_balance / hold_price) * price

    alpha = live_total - hold_total
    alpha_pct = (alpha / start_total * 100) if start_total else 0
    hold_pnl_pct = ((hold_total - start_total) / start_total * 100) if start_total else 0
    live_pnl_pct = ((live_total - start_total) / start_total * 100) if start_total else 0
    vs_hold_pct = live_pnl_pct - hold_pnl_pct

    lifetime_anchored = sum(
        anchor_counts.get(a, 0) for a in LOCKED_HOLD_ANCHORS
    )
    market_count = len(sessions)
    if lifetime_anchored >= market_count * 0.7:
        quality = "high"
    elif lifetime_anchored >= market_count * 0.4:
        quality = "medium"
    else:
        quality = "low"

    misleading = (
        (abs(vs_hold_pct) > 10 and abs(live_pnl_pct) < 3)
        or (hold_pnl_pct < -15 and abs(live_pnl_pct) < 3)
    )
    note = ""
    if misleading:
        note = "vs Hold выглядит странно — смотри P&L портфеля как главную метрику."
    elif quality == "low":
        note = "Мало данных для vs Hold — подожди первую сделку или загрузку цены."

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
        "hold_window": "с момента старта сессии / первой покупки",
    }
