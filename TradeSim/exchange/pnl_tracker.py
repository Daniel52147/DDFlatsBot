"""Testnet/exchange portfolio valuation vs paper."""

from __future__ import annotations

from typing import Any

import config


async def snapshot_exchange_portfolio(
    sessions: dict,
    live_exchange,
) -> dict[str, Any]:
    """Value exchange wallet using live session prices."""
    if not live_exchange or not live_exchange.enabled:
        paper = _paper_total(sessions)
        return {
            "enabled": False,
            "mode": "paper",
            "paper_total_usd": round(paper, 2),
            "note": "Биржа выключена — только paper",
        }

    try:
        acct = await live_exchange.account_balances()
    except Exception as e:
        return {"enabled": True, "error": str(e), "paper_total_usd": round(_paper_total(sessions), 2)}

    balances = {b["asset"]: b["free"] + b["locked"] for b in acct.get("balances", [])}
    usdt = balances.get("USDT", 0.0)
    coins_usd = 0.0
    holdings: list[dict[str, Any]] = []

    for sym, session in sessions.items():
        asset = sym.replace("USDT", "")
        base = balances.get(asset, 0.0)
        if base <= 0:
            continue
        price = session.feed.price or session.demo_price
        if price <= 0:
            continue
        val = base * price
        coins_usd += val
        paper_snap = session.engine.snapshot(price)
        holdings.append({
            "symbol": sym,
            "label": session.label,
            "base": round(base, 8),
            "price": price,
            "usd": round(val, 2),
            "paper_base": round(session.engine.position.base, 8),
            "paper_vs_hold_pct": paper_snap.get("vs_hold_pct", 0),
        })

    exchange_total = usdt + coins_usd
    paper_total = _paper_total(sessions)
    bench = _paper_benchmark(sessions)
    start = sum(s.engine.start_balance for s in sessions.values())

    return {
        "enabled": True,
        "mode": "testnet" if live_exchange.testnet else "live",
        "exchange_total_usd": round(exchange_total, 2),
        "paper_total_usd": round(paper_total, 2),
        "delta_usd": round(exchange_total - paper_total, 2),
        "usdt_free": round(usdt, 2),
        "coins_usd": round(coins_usd, 2),
        "paper_pnl_pct": round((paper_total - start) / start * 100, 2) if start else 0,
        "paper_vs_hold_pct": bench.get("vs_hold_pct", 0),
        "hold_value_usd": bench.get("hold_value", 0),
        "orders_today": live_exchange.risk.orders_today,
        "daily_loss_usd": round(live_exchange.risk.daily_loss_usd, 2),
        "holdings": sorted(holdings, key=lambda x: -x["usd"])[:12],
        "sync_from_paper": config.EXCHANGE_SYNC_FROM_PAPER,
        "sync_to_paper": config.EXCHANGE_SYNC_TO_PAPER,
    }


def _paper_total(sessions: dict) -> float:
    return sum(
        s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"]
        for s in sessions.values()
    )


def _paper_benchmark(sessions: dict) -> dict[str, float]:
    live_total = 0.0
    hold_total = 0.0
    start_total = 0.0
    for s in sessions.values():
        price = s.feed.price or s.demo_price
        snap = s.engine.snapshot(price)
        live_total += snap["portfolio_value"]
        start_total += s.engine.start_balance
        sp = s.engine.start_price or price
        if sp > 0:
            hold_total += (s.engine.start_balance / sp) * price
    live_pnl = ((live_total - start_total) / start_total * 100) if start_total else 0
    hold_pnl = ((hold_total - start_total) / start_total * 100) if start_total else 0
    return {
        "live_value": round(live_total, 2),
        "hold_value": round(hold_total, 2),
        "vs_hold_pct": round(live_pnl - hold_pnl, 2),
    }
