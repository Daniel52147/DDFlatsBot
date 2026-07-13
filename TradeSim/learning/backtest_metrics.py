"""Risk-adjusted backtest metrics — Sharpe, Sortino, Calmar, drawdown, win rate."""

from __future__ import annotations

import math
from typing import Any

from learning.analytics import _max_drawdown, analyze_market_trades


def _periods_per_year(interval_minutes: int = 1) -> float:
    return (365 * 24 * 60) / max(interval_minutes, 1)


def _returns_from_equity(values: list[float]) -> list[float]:
    returns: list[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        if prev and prev > 0:
            returns.append((values[i] - prev) / prev * 100)
    return returns


def sharpe_ratio(returns: list[float], *, interval_minutes: int = 1) -> float | None:
    if len(returns) < 3:
        return None
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    if var <= 0:
        return None
    scale = math.sqrt(_periods_per_year(interval_minutes))
    return round(mean / math.sqrt(var) * scale, 2)


def sortino_ratio(returns: list[float], *, interval_minutes: int = 1) -> float | None:
    if len(returns) < 3:
        return None
    mean = sum(returns) / len(returns)
    downside = [min(0.0, r) for r in returns]
    ds_var = sum(d ** 2 for d in downside) / len(returns)
    if ds_var <= 0:
        return None if mean <= 0 else None
    scale = math.sqrt(_periods_per_year(interval_minutes))
    return round(mean / math.sqrt(ds_var) * scale, 2)


def calmar_ratio(pnl_pct: float, max_dd_pct: float, *, period_bars: int, interval_minutes: int = 1) -> float | None:
    if max_dd_pct <= 0 or period_bars <= 0:
        return None
    hours = period_bars * interval_minutes / 60
    if hours <= 0:
        return None
    annualized = pnl_pct * (365 * 24 / hours)
    return round(annualized / max_dd_pct, 2)


def compute_backtest_metrics(
    *,
    equity_curve: list[float],
    executed_trades: list[Any],
    pnl_pct: float,
    interval_minutes: int = 1,
) -> dict[str, Any]:
    """Full metric pack for a single backtest run."""
    if not equity_curve:
        equity_curve = [0.0]

    returns = _returns_from_equity(equity_curve)
    max_dd = _max_drawdown(equity_curve)
    trade_rows = [
        {
            "ts": i,
            "side": t.side,
            "price": t.price,
            "amount_quote": t.amount_quote,
            "amount_base": t.amount_base,
            "fee": t.fee,
            "reason": t.reason,
        }
        for i, t in enumerate(executed_trades)
    ]
    trade_stats = analyze_market_trades(trade_rows)

    return {
        "max_drawdown_pct": max_dd,
        "sharpe": sharpe_ratio(returns, interval_minutes=interval_minutes),
        "sortino": sortino_ratio(returns, interval_minutes=interval_minutes),
        "calmar": calmar_ratio(
            pnl_pct,
            max_dd,
            period_bars=len(equity_curve),
            interval_minutes=interval_minutes,
        ),
        "win_rate_pct": trade_stats.get("win_rate_pct", 0),
        "sell_edge_pct": trade_stats.get("sell_edge_pct", 0),
        "profit_factor": _profit_factor(executed_trades),
        "equity_points": len(equity_curve),
    }


def _profit_factor(trades: list[Any]) -> float | None:
    """Gross wins / gross losses on sells vs implied entry (simplified)."""
    wins = 0.0
    losses = 0.0
    cost = 0.0
    base = 0.0
    for t in trades:
        if t.side == "buy":
            net = float(t.amount_quote) - float(t.fee)
            base += float(t.amount_base)
            cost += net
        elif t.side == "sell" and base > 0:
            avg = cost / base
            pnl = (float(t.price) - avg) * float(t.amount_base)
            if pnl >= 0:
                wins += pnl
            else:
                losses += abs(pnl)
            frac = min(1.0, float(t.amount_base) / base)
            cost *= max(0, 1 - frac)
            base = max(0, base - float(t.amount_base))
    if losses <= 0:
        return round(wins, 2) if wins > 0 else None
    return round(wins / losses, 2)


def metrics_summary_line(metrics: dict[str, Any]) -> str:
    parts = [
        f"DD {metrics.get('max_drawdown_pct', 0):.1f}%",
    ]
    if metrics.get("sharpe") is not None:
        parts.append(f"Sharpe {metrics['sharpe']}")
    if metrics.get("sortino") is not None:
        parts.append(f"Sortino {metrics['sortino']}")
    if metrics.get("calmar") is not None:
        parts.append(f"Calmar {metrics['calmar']}")
    if metrics.get("win_rate_pct") is not None:
        parts.append(f"Win {metrics['win_rate_pct']}%")
    return " · ".join(parts)
