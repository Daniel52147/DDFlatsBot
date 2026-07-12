"""Binance spot layer — testnet/live with risk limits and order reconciliation."""

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
    """Guardrails before any real order."""

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
                return False, (
                    f"Позиция {pos_pct * 100:.0f}% > лимита "
                    f"{config.EXCHANGE_MAX_POSITION_PCT * 100:.0f}%"
                )
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
    Binance spot — paper without keys, testnet with BINANCE_API_KEY + EXCHANGE_ENABLED=true.
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
        self._symbol_rules: dict[str, dict[str, Any]] = {}
        self._rules_ts = 0.0

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
            "note": (
                "Paper-бот и биржа раздельны — ордера только через /api/exchange/order"
                if not self.enabled
                else "Testnet активен — сверяй баланс вручную"
            ),
        }

    def _sign(self, params: dict) -> str:
        query = urlencode(params)
        sig = hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&signature={sig}"

    async def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        url = f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key} if signed else {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            url = f"{url}?{self._sign(params)}"
            params = None
        async with httpx.AsyncClient(timeout=20) as client:
            if method == "GET":
                r = await client.get(url, params=params, headers=headers)
            else:
                r = await client.post(url, headers=headers)
            r.raise_for_status()
            return r.json()

    async def _load_symbol_rules(self, symbol: str) -> dict[str, Any]:
        if time.time() - self._rules_ts < 3600 and symbol in self._symbol_rules:
            return self._symbol_rules[symbol]
        try:
            info = await self._request("GET", "/api/v3/exchangeInfo")
            for s in info.get("symbols", []):
                if s.get("symbol") != symbol:
                    continue
                rules = {"min_notional": 10.0, "step_size": 0.00001, "min_qty": 0.0}
                for f in s.get("filters", []):
                    if f["filterType"] == "LOT_SIZE":
                        rules["step_size"] = float(f["stepSize"])
                        rules["min_qty"] = float(f["minQty"])
                    elif f["filterType"] in ("NOTIONAL", "MIN_NOTIONAL"):
                        rules["min_notional"] = float(f.get("minNotional", f.get("notional", 10)))
                self._symbol_rules[symbol] = rules
            self._rules_ts = time.time()
        except Exception as e:
            logger.warning("exchangeInfo %s: %s", symbol, e)
            self._symbol_rules.setdefault(symbol, {"min_notional": 10.0, "step_size": 0.00001, "min_qty": 0.0})
        return self._symbol_rules.get(symbol, {"min_notional": 10.0, "step_size": 0.00001, "min_qty": 0.0})

    @staticmethod
    def _round_step(qty: float, step: float) -> float:
        if step <= 0:
            return qty
        precision = max(0, len(str(step).rstrip("0").split(".")[-1]) if "." in str(step) else 0)
        floored = (int(qty / step)) * step
        return round(floored, precision)

    async def account_balances(self) -> dict[str, Any]:
        if not self.enabled:
            return {"mode": "paper", "balances": [], "note": "Нет API ключей — paper режим"}
        data = await self._request("GET", "/api/v3/account", signed=True)
        balances = [
            {"asset": b["asset"], "free": float(b["free"]), "locked": float(b["locked"])}
            for b in data.get("balances", [])
            if float(b["free"]) + float(b["locked"]) > 0
        ]
        return {"mode": "live", "balances": balances[:30]}

    async def get_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        if not self.enabled:
            return {"error": "exchange disabled"}
        return await self._request(
            "GET", "/api/v3/order",
            {"symbol": symbol, "orderId": order_id},
            signed=True,
        )

    async def reconcile(self, symbol: str, paper_base: float, paper_quote: float) -> dict[str, Any]:
        """Compare paper session vs exchange wallet for one asset."""
        if not self.enabled:
            return {"mode": "paper", "synced": None, "note": "Биржа выключена"}
        base_asset = symbol.replace("USDT", "")
        acct = await self.account_balances()
        ex_base = 0.0
        ex_quote = 0.0
        for b in acct.get("balances", []):
            if b["asset"] == base_asset:
                ex_base = b["free"] + b["locked"]
            elif b["asset"] == "USDT":
                ex_quote = b["free"] + b["locked"]
        return {
            "mode": "live",
            "symbol": symbol,
            "base_asset": base_asset,
            "paper_base": round(paper_base, 8),
            "exchange_base": round(ex_base, 8),
            "paper_quote": round(paper_quote, 2),
            "exchange_usdt": round(ex_quote, 2),
            "base_diff": round(ex_base - paper_base, 8),
            "base_tol": round(max(1e-6, abs(paper_base) * 0.01 + 1e-4), 8),
            "base_synced": abs(ex_base - paper_base) <= max(1e-6, abs(paper_base) * 0.01 + 1e-4),
            "note": "USDT на бирже — общий баланс счёта; paper quote — только этот рынок",
            "synced": abs(ex_base - paper_base) <= max(1e-6, abs(paper_base) * 0.01 + 1e-4),
        }

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        amount_usd: float,
        portfolio_value: float,
        pnl_pct: float,
        price: float | None = None,
    ) -> dict[str, Any]:
        side = side.lower()
        if side not in ("buy", "sell"):
            return {"ok": False, "error": "side must be buy or sell"}

        ok, reason = self.risk.check_order(side, amount_usd, portfolio_value, pnl_pct)
        if not ok:
            return {"ok": False, "error": reason, "mode": "blocked"}

        if not self.enabled:
            return {
                "ok": False,
                "mode": "paper",
                "symbol": symbol,
                "side": side,
                "quote_amount": amount_usd,
                "note": "Paper симуляция — задай BINANCE_API_KEY + EXCHANGE_ENABLED=true",
            }

        rules = await self._load_symbol_rules(symbol)
        if amount_usd < rules["min_notional"]:
            return {
                "ok": False,
                "error": f"Минимум ${rules['min_notional']} (Binance notional)",
            }

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
        }

        if side == "buy":
            params["quoteOrderQty"] = round(amount_usd, 2)
        else:
            if not price or price <= 0:
                return {"ok": False, "error": "Нужна цена для sell"}
            qty = self._round_step(amount_usd / price, rules["step_size"])
            if qty < rules["min_qty"]:
                return {"ok": False, "error": f"Слишком мало base (min {rules['min_qty']})"}
            if qty * price < rules["min_notional"]:
                return {"ok": False, "error": f"Notional < ${rules['min_notional']}"}
            params["quantity"] = qty

        try:
            data = await self._request("POST", "/api/v3/order", params, signed=True)
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": e.response.text, "mode": "live"}

        fills_quote = sum(float(f.get("price", 0)) * float(f.get("qty", 0)) for f in data.get("fills", []))
        base_asset = symbol.replace("USDT", "")
        commission_usd = 0.0
        for f in data.get("fills", []):
            comm = float(f.get("commission", 0) or 0)
            asset = f.get("commissionAsset", "")
            if asset == "USDT":
                commission_usd += comm
            elif asset == base_asset:
                commission_usd += comm * float(f.get("price", price or 0))
        pnl_delta = -commission_usd
        if side == "sell" and fills_quote > 0:
            pnl_delta = fills_quote * 0.001 - commission_usd
        self.risk.record_result(pnl_delta)
        return {
            "ok": True,
            "mode": "live",
            "order": data,
            "order_id": data.get("orderId"),
            "status": data.get("status"),
            "fills_quote": round(fills_quote, 4),
        }
