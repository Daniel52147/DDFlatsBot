"""TradingView alert webhook — external signals into TradeSim."""

from __future__ import annotations

import logging
import time
from typing import Any

import config

logger = logging.getLogger(__name__)


def _normalize_symbol(raw: str) -> str:
    s = (raw or "").upper().strip().replace("/", "").replace("-", "")
    if not s:
        return ""
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    return s


def validate_webhook_secret(secret: str | None) -> bool:
    expected = config.TRADINGVIEW_WEBHOOK_SECRET
    if not expected:
        return False
    return bool(secret) and secret == expected


async def handle_tradingview_signal(
    payload: dict[str, Any],
    sessions: dict[str, Any],
    *,
    broadcast: Any = None,
) -> dict[str, Any]:
    """Execute TradingView webhook: buy, sell, pause, resume."""
    secret = payload.get("secret") or payload.get("key") or payload.get("passphrase")
    if not validate_webhook_secret(secret):
        return {"ok": False, "error": "invalid webhook secret"}

    action = (
        payload.get("action")
        or payload.get("side")
        or payload.get("alert")
        or ""
    ).lower().strip()
    symbol = _normalize_symbol(
        str(payload.get("symbol") or payload.get("ticker") or payload.get("pair") or "")
    )

    if action in ("pause", "stop", "halt"):
        if symbol and symbol in sessions:
            sessions[symbol].bot.enabled = False
            await sessions[symbol].persist()
            return {"ok": True, "action": "pause", "symbol": symbol}
        for s in sessions.values():
            s.bot.enabled = False
            await s.persist()
        return {"ok": True, "action": "pause", "symbol": "all"}

    if action in ("resume", "start", "unpause"):
        if symbol and symbol in sessions:
            sessions[symbol].bot.enabled = True
            await sessions[symbol].persist()
            from learning.protections import protections_engine
            protections_engine.clear_symbol(symbol)
            return {"ok": True, "action": "resume", "symbol": symbol}
        for s in sessions.values():
            s.bot.enabled = True
            await s.persist()
        from learning.protections import protections_engine
        protections_engine.clear_all()
        return {"ok": True, "action": "resume", "symbol": "all"}

    if not symbol or symbol not in sessions:
        known = [m["symbol"] for m in config.MARKETS]
        return {"ok": False, "error": f"unknown symbol {symbol}", "known": known[:5]}

    if action not in ("buy", "long", "sell", "short", "close"):
        return {"ok": False, "error": f"unknown action '{action}' — use buy/sell/pause/resume"}

    size = float(
        payload.get("size_usdt")
        or payload.get("amount_usd")
        or payload.get("size")
        or config.TRADINGVIEW_DEFAULT_SIZE_USD
    )
    max_size = config.TRADINGVIEW_MAX_SIZE_USD
    size = max(1.0, min(size, max_size))

    session = sessions[symbol]
    side = "buy" if action in ("buy", "long") else "sell"
    reason = f"TV: {payload.get('strategy', payload.get('alert', 'webhook'))}"[:80]

    trade = await session.manual_trade(side, size, reason=reason)
    if not trade:
        return {"ok": False, "error": "trade failed — protection block, balance or price"}

    result = {
        "ok": True,
        "action": side,
        "symbol": symbol,
        "label": session.label,
        "size_usdt": size,
        "trade": trade,
        "ts": time.time(),
    }
    if broadcast:
        await broadcast({
            "type": "tradingview_signal",
            "symbol": symbol,
            "label": session.label,
            "side": side,
            "size_usdt": size,
        })
    logger.info("TradingView %s %s $%.2f", side, symbol, size)
    return result
