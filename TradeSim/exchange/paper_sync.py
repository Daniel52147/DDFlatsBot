"""Sync Binance testnet/live fills into paper wallet."""

from __future__ import annotations

import logging
from typing import Any

import config

logger = logging.getLogger(__name__)


def parse_binance_order(order: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """Extract economic fill from Binance order response."""
    side = (order.get("side") or "").lower()
    if side not in ("buy", "sell"):
        return None

    base_asset = symbol.replace("USDT", "")
    fills = order.get("fills") or []
    fee_usd = 0.0

    if fills:
        gross_base = sum(float(f.get("qty", 0)) for f in fills)
        gross_quote = sum(float(f.get("price", 0)) * float(f.get("qty", 0)) for f in fills)
        net_base = gross_base
        for f in fills:
            comm = float(f.get("commission", 0) or 0)
            asset = f.get("commissionAsset", "")
            price = float(f.get("price", 0))
            if asset == "USDT":
                fee_usd += comm
            elif asset == base_asset:
                fee_usd += comm * price
                net_base -= comm
        avg_price = gross_quote / gross_base if gross_base else 0.0
    else:
        gross_base = float(order.get("executedQty") or 0)
        gross_quote = float(
            order.get("cummulativeQuoteQty") or order.get("cumQuote") or 0
        )
        net_base = gross_base
        avg_price = gross_quote / gross_base if gross_base else float(order.get("price") or 0)

    if gross_base <= 0 and net_base <= 0:
        return None

    if side == "buy":
        quote_spent = gross_quote + fee_usd
        return {
            "side": "buy",
            "price": avg_price,
            "amount_base": net_base,
            "amount_quote": quote_spent,
            "fee": fee_usd,
        }

    net_quote = gross_quote - fee_usd
    return {
        "side": "sell",
        "price": avg_price,
        "amount_base": gross_base,
        "amount_quote": net_quote,
        "fee": fee_usd,
    }


async def sync_order_to_paper(session, exchange_result: dict[str, Any]) -> dict[str, Any] | None:
    """Apply executed exchange order to paper engine (no double slippage)."""
    if not exchange_result.get("ok"):
        return None
    order = exchange_result.get("order") or {}
    symbol = order.get("symbol") or getattr(session, "symbol", "")
    fill = parse_binance_order(order, symbol)
    if not fill:
        return None

    mode = exchange_result.get("mode", "live")
    order_id = order.get("orderId", "?")
    reason = f"EXCHANGE {mode.upper()}: ордер #{order_id} → paper sync"

    mark = session.feed.price or session.demo_price
    trade = session.engine.apply_exchange_fill(
        side=fill["side"],
        price=fill["price"],
        amount_base=fill["amount_base"],
        amount_quote=fill["amount_quote"],
        fee=fill["fee"],
        reason=reason,
        mark_price=mark,
    )
    if not trade:
        return {"ok": False, "error": "paper wallet rejected fill (insufficient balance?)"}

    await session._log_trade(trade)
    snap = session.engine.snapshot(mark)
    return {
        "ok": True,
        "synced": True,
        "side": trade.side,
        "price": trade.price,
        "amount_quote": trade.amount_quote,
        "amount_base": trade.amount_base,
        "fee": trade.fee,
        "reason": trade.reason,
        "portfolio_value": snap.get("portfolio_value"),
        "pnl_pct": snap.get("pnl_pct"),
    }


async def mirror_base_from_exchange(session, exchange, tolerance: float | None = None) -> dict[str, Any]:
    """Align paper base balance with exchange wallet for one symbol."""
    if not exchange.enabled:
        return {"ok": False, "error": "exchange disabled"}

    symbol = session.symbol
    price = session.feed.price or session.demo_price
    try:
        rec = await exchange.reconcile(
            symbol, session.engine.position.base, session.engine.position.quote,
        )
    except Exception as e:
        logger.warning("mirror reconcile failed for %s: %s", symbol, e)
        return {"ok": False, "error": f"exchange reconcile failed: {e}", "symbol": symbol}
    tol = tolerance if tolerance is not None else max(1e-6, abs(rec["paper_base"]) * 0.01 + 1e-4)
    diff = rec["exchange_base"] - rec["paper_base"]

    if abs(diff) <= tol:
        return {"ok": True, "synced": True, "symbol": symbol, "diff": 0, "note": "already aligned"}

    eng = session.engine
    reason = f"EXCHANGE MIRROR: align base Δ {diff:+.8f}"

    if diff > 0:
        amount_quote = diff * price
        trade = eng.apply_exchange_fill(
            side="buy",
            price=price,
            amount_base=diff,
            amount_quote=amount_quote,
            fee=0.0,
            reason=reason,
            mark_price=price,
        )
        if not trade:
            return {
                "ok": False,
                "error": "insufficient paper USDT to mirror exchange base",
                "symbol": symbol,
                "diff": round(diff, 8),
                "needed_usdt": round(amount_quote, 2),
                "paper_quote": round(eng.position.quote, 2),
            }
    else:
        remove = min(eng.position.base, abs(diff))
        if remove <= 0:
            return {
                "ok": True,
                "synced": True,
                "symbol": symbol,
                "label": session.label,
                "diff": round(diff, 8),
                "note": "no paper base to reduce",
            }
        trade = eng.apply_exchange_fill(
            side="sell",
            price=price,
            amount_base=remove,
            amount_quote=remove * price,
            fee=0.0,
            reason=reason,
            mark_price=price,
        )
        if not trade:
            return {"ok": False, "error": "paper wallet rejected mirror sell", "symbol": symbol}

    await session._log_trade(trade)
    return {
        "ok": True,
        "synced": True,
        "symbol": symbol,
        "label": session.label,
        "diff": round(diff, 8),
        "paper_base": eng.position.base,
        "exchange_base": rec["exchange_base"],
        "trade": {
            "side": trade.side,
            "price": trade.price,
            "amount_quote": trade.amount_quote,
            "amount_base": trade.amount_base,
        },
        "note": "base balance mirrored from exchange",
    }


def _is_exchange_origin_trade(trade) -> bool:
    return (getattr(trade, "reason", "") or "").startswith("EXCHANGE")


async def sync_trade_to_exchange(session, trade, exchange) -> dict[str, Any] | None:
    """Mirror a paper bot/manual trade to testnet/live (paper → exchange)."""
    if not config.EXCHANGE_SYNC_FROM_PAPER or not exchange.enabled:
        return None
    if _is_exchange_origin_trade(trade):
        return None

    price = session.feed.price or session.demo_price
    if price <= 0:
        return {"ok": False, "error": "no price for exchange sync"}

    snap = session.engine.snapshot(price)
    amount_usd = float(getattr(trade, "amount_quote", 0) or 0)
    if amount_usd <= 0:
        return None

    result = await exchange.place_market_order(
        session.symbol,
        trade.side,
        amount_usd,
        snap.get("portfolio_value", 0),
        snap.get("pnl_pct", 0),
        price=price,
        from_paper_sync=True,
    )
    if not result.get("ok"):
        logger.warning(
            "[%s] paper→exchange sync failed: %s",
            session.symbol,
            result.get("error", "unknown"),
        )
        return {
            "ok": False,
            "error": result.get("error"),
            "side": trade.side,
            "amount_usd": amount_usd,
        }

    return {
        "ok": True,
        "synced": True,
        "direction": "paper_to_exchange",
        "side": trade.side,
        "amount_usd": amount_usd,
        "order_id": result.get("order_id"),
        "mode": result.get("mode"),
    }
