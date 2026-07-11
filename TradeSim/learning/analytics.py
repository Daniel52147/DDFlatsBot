"""Portfolio analytics: drawdown, win rate, trade breakdown."""

from __future__ import annotations

import math
from typing import Any


def _max_drawdown(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            max_dd = max(max_dd, dd)
    return round(max_dd, 2)


def _sharpe_like(returns: list[float]) -> float | None:
    if len(returns) < 3:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if var <= 0:
        return None
    # Hourly-ish snapshots scaled to daily-ish Sharpe proxy
    return round(mean / math.sqrt(var) * math.sqrt(24 * 12), 2)


def analyze_market_trades(trades: list[dict]) -> dict[str, Any]:
    buys = [t for t in trades if t.get("side") == "buy"]
    sells = [t for t in trades if t.get("side") == "sell"]
    reasons = {"dca": 0, "dip": 0, "spike": 0, "tp": 0, "stop": 0, "manual": 0}
    for t in trades:
        r = (t.get("reason") or "").upper()
        if "STOP" in r:
            reasons["stop"] += 1
        elif "MANUAL" in r:
            reasons["manual"] += 1
        elif "SPIKE" in r:
            reasons["spike"] += 1
        elif "DIP" in r:
            reasons["dip"] += 1
        elif "DCA" in r:
            reasons["dca"] += 1
        elif "TAKE-PROFIT" in r or "TP" in r:
            reasons["tp"] += 1
    sell_pnl_est = 0.0
    if sells and buys:
        avg_buy = sum(t["price"] for t in buys) / len(buys)
        sell_pnl_est = sum((t["price"] - avg_buy) / avg_buy * 100 for t in sells) / len(sells)
    return {
        "total": len(trades),
        "buys": len(buys),
        "sells": len(sells),
        "reasons": reasons,
        "sell_edge_pct": round(sell_pnl_est, 2),
        "win_rate_pct": round(len(sells) / max(len(trades), 1) * 100, 1) if sells else 0,
    }


def build_portfolio_analytics(
    sessions_snap: list[dict[str, Any]],
    equity_curve: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate analytics from live session snapshots."""
    markets = []
    total_trades = 0
    total_sells = 0
    vs_hold_values = []
    pnl_values = []

    for snap in sessions_snap:
        label = snap["label"]
        portfolio = snap.get("portfolio", {})
        trades = snap.get("trades", [])
        trade_stats = analyze_market_trades(trades)
        total_trades += trade_stats["total"]
        total_sells += trade_stats["sells"]
        vs = portfolio.get("vs_hold_pct", 0)
        pnl = portfolio.get("pnl_pct", 0)
        vs_hold_values.append(vs)
        pnl_values.append(pnl)
        markets.append({
            "symbol": snap["symbol"],
            "label": label,
            "pnl_pct": pnl,
            "vs_hold_pct": vs,
            "portfolio_value": portfolio.get("portfolio_value", 0),
            "trade_stats": trade_stats,
            "avg_entry": snap.get("avg_entry"),
            "bot_enabled": snap.get("bot_enabled", True),
        })

    values = [p["value"] for p in (equity_curve or []) if p.get("value")]
    returns = []
    for i in range(1, len(values)):
        if values[i - 1]:
            returns.append((values[i] - values[i - 1]) / values[i - 1] * 100)

    beating = sum(1 for v in vs_hold_values if v >= 0)
    return {
        "total_trades": total_trades,
        "total_sells": total_sells,
        "markets_beating_hold": beating,
        "markets_total": len(markets),
        "max_drawdown_pct": _max_drawdown(values) if values else 0,
        "sharpe_proxy": _sharpe_like(returns),
        "avg_vs_hold_pct": round(sum(vs_hold_values) / len(vs_hold_values), 2) if vs_hold_values else 0,
        "markets": markets,
    }
