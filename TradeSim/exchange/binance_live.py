"""Optional live exchange layer — Binance spot with risk limits."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any
from urllib.parse import urlencode

import httpx

import config

logger = logging.getLogger(__name__)


class ExchangeRiskManager:
    """Paper/live guardrails before any real order."""

    def __init__(self):
        self.daily_loss_usd = 0.0
        self.daily_reset_ts = time.time()
        self.orders_today = 0

    def _roll_day(self):
        if time.time() - self.daily_reset_ts > 86400:
            self.daily_loss_usd = 0.0
            self.orders_today = 0
            self.daily_reset_ts = time.time()

    def check_order(
        self,
        side: str,
        amount_usd: float,
        portfolio_value: float,
        pnl_pct: float,
    ) -> tuple[bool, str]:
        self._roll_day()
        max_order = config.EXCHANGE_MAX_ORDER_USD
        if amount_usd > max_order:
            return False, f"Ордер ${amount_usd:.0f} > лимита ${max_order:.0f}"
        if portfolio_value > 0:
            pos_pct = amount_usd / portfolio_value
            if pos_pct > config.EXCHANGE_MAX_POSITION_PCT:
                return False, f"Позиция {pos_pct*100:.0f}% > лимита {config.EXCHANGE_MAX_POSITION_PCT*100:.0f}%"
        if pnl_pct <= -config.EXCHANGE_MAX_DAILY_LOSS_PCT:
            return False, f"Дневная просадка {pnl_pct:.1f}% — торговля заблокирована"
        if self.daily_loss_usd >= portfolio_value * config.EXCHANGE_MAX_DAILY_LOSS_PCT / 100:
            return False, "Дневной лимит убытка исчерпан"
        return True, "ok"

    def record_result(self, pnl_delta: float):
        self._roll_day()
        if pnl_delta < 0:
            self.daily_loss_usd += abs(pnl_delta)
        self.orders_today += 1


class BinanceLiveExchange:
    """
    Binance spot API — works in testnet or paper mode without keys.
    Set BINANCE_API_KEY + BINANCE_API_SECRET env vars for live testnet.
    """

    TESTNET = "https://testnet.binance.vision"
    LIVE = "https://api.binance.com"

    def __init__(self):
        self.api_key = os.environ.get("BINANCE_API_KEY", "")
        self.api_secret = os.environ.get("BINANCE_API_SECRET", "")
        self.testnet = config.EXCHANGE_TESTNET
        self.base_url = self.TESTNET if self.testnet else self.LIVE
        self.risk = ExchangeRiskManager()
        self.enabled = bool(self.api_key and self.api_secret and config.EXCHANGE_ENABLED)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "exchange": config.EXCHANGE_NAME,
            "testnet": self.testnet,
            "has_keys": bool(self.api_key),
            "max_order_usd": config.EXCHANGE_MAX_ORDER_USD,
            "max_daily_loss_pct": config.EXCHANGE_MAX_DAILY_LOSS_PCT,
            "max_position_pct": config.EXCHANGE_MAX_POSITION_PCT,
            "orders_today": self.risk.orders_today,
            "mode": "live-testnet" if self.enabled else "paper-only",
        }

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        sig = hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={sig}"

    async def account_balances(self) -> dict[str, Any]:
        if not self.enabled:
            return {"mode": "paper", "balances": [], "note": "Нет API ключей — paper режим"}
        params = {"timestamp": int(time.time() * 1000)}
        url = f"{self.base_url}/api/v3/account?{self._sign(params)}"
        headers = {"X-MBX-APIKEY": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
        balances = [
            {"asset": b["asset"], "free": float(b["free"]), "locked": float(b["locked"])}
            for b in data.get("balances", [])
            if float(b["free"]) + float(b["locked"]) > 0
        ]
        return {"mode": "live", "balances": balances[:20]}

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quote_amount: float,
        portfolio_value: float,
        pnl_pct: float,
    ) -> dict[str, Any]:
        ok, reason = self.risk.check_order(side, quote_amount, portfolio_value, pnl_pct)
        if not ok:
            return {"ok": False, "error": reason, "mode": "blocked"}

        if not self.enabled:
            return {
                "ok": True,
                "mode": "paper",
                "symbol": symbol,
                "side": side,
                "quote_amount": quote_amount,
                "note": "Paper симуляция — для реала задай BINANCE_API_KEY",
            }

        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quoteOrderQty": round(quote_amount, 2),
            "timestamp": int(time.time() * 1000),
        }
        url = f"{self.base_url}/api/v3/order"
        headers = {"X-MBX-APIKEY": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{url}?{self._sign(params)}", headers=headers)
            if r.status_code >= 400:
                return {"ok": False, "error": r.text, "mode": "live"}
            data = r.json()
        self.risk.record_result(0)
        return {"ok": True, "mode": "live", "order": data}
