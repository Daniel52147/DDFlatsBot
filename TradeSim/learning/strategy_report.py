"""Per-strategy performance report — which tactics earn on which coins."""

from __future__ import annotations

from typing import Any

from learning.analytics import analyze_market_trades


def _trade_rows(engine_trades: list) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for t in engine_trades:
        if hasattr(t, "side"):
            rows.append({
                "side": t.side,
                "price": t.price,
                "amount_quote": t.amount_quote,
                "amount_base": t.amount_base,
                "fee": t.fee,
                "reason": t.reason,
                "ts": t.ts,
            })
        elif isinstance(t, dict):
            rows.append(t)
    return rows


def build_strategy_report(sessions: dict) -> dict[str, Any]:
    """Aggregate live P&L and trade stats by strategy type and market."""
    markets: list[dict[str, Any]] = []
    buckets: dict[str, dict[str, Any]] = {}

    for sym, session in sessions.items():
        price = session.feed.price or session.demo_price
        snap = session.engine.snapshot(price)
        stype = getattr(session, "strategy_type", "dca")
        trade_stats = analyze_market_trades(_trade_rows(session.engine.trades))

        row = {
            "symbol": sym,
            "label": session.label,
            "tier": getattr(session, "tier", "major"),
            "strategy_type": stype,
            "pnl_pct": snap.get("pnl_pct", 0),
            "vs_hold_pct": snap.get("vs_hold_pct", 0),
            "portfolio_value": snap.get("portfolio_value", 0),
            "trade_count": snap.get("trade_count", 0),
            "win_rate_pct": trade_stats.get("win_rate_pct", 0),
            "sell_edge_pct": trade_stats.get("sell_edge_pct", 0),
            "bot_enabled": session.bot.enabled,
        }
        markets.append(row)

        b = buckets.setdefault(stype, {
            "strategy_type": stype,
            "markets": 0,
            "beating_hold": 0,
            "pnl_sum": 0.0,
            "vs_hold_sum": 0.0,
            "trades": 0,
            "wins": 0,
            "sells": 0,
        })
        b["markets"] += 1
        b["trades"] += trade_stats.get("total", 0)
        b["wins"] += trade_stats.get("wins", 0)
        b["sells"] += trade_stats.get("sell_count", 0)
        b["pnl_sum"] += row["pnl_pct"]
        b["vs_hold_sum"] += row["vs_hold_pct"]
        if row["vs_hold_pct"] >= 0:
            b["beating_hold"] += 1

    by_strategy: list[dict[str, Any]] = []
    for stype, b in buckets.items():
        n = b["markets"] or 1
        sells = b["sells"] or 0
        by_strategy.append({
            "strategy_type": stype,
            "markets": b["markets"],
            "beating_hold": b["beating_hold"],
            "avg_pnl_pct": round(b["pnl_sum"] / n, 2),
            "avg_vs_hold_pct": round(b["vs_hold_sum"] / n, 2),
            "total_trades": b["trades"],
            "win_rate_pct": round(b["wins"] / sells * 100, 1) if sells else 0.0,
        })
    by_strategy.sort(key=lambda x: x["avg_vs_hold_pct"], reverse=True)

    markets.sort(key=lambda x: x["vs_hold_pct"], reverse=True)
    best = markets[0] if markets else None
    worst = markets[-1] if markets else None

    return {
        "by_strategy": by_strategy,
        "markets": markets,
        "leader": best,
        "laggard": worst,
        "markets_beating_hold": sum(1 for m in markets if m["vs_hold_pct"] >= 0),
        "markets_total": len(markets),
    }
