"""Binance spot layer — testnet/live with risk limits and order reconciliation."""

from __future__ import annotations

import hashlib
import hmac
import json
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
        self.day_start_value = 0.0

    def _roll_day(self):
        if time.time() - self.daily_reset_ts > 86400:
            self.daily_loss_usd = 0.0
            self.orders_today = 0
            self.day_start_value = 0.0
            self.daily_reset_ts = time.time()

    def note_portfolio_value(self, portfolio_value: float):
        """Track day-start portfolio for true daily drawdown."""
        self._roll_day()
        if portfolio_value > 0 and self.day_start_value <= 0:
            self.day_start_value = portfolio_value

    def check_order(
        self,
        side: str,
        amount_usd: float,
        portfolio_value: float,
        pnl_pct: float,
        *,
        portfolio_pnl_pct: float | None = None,
        max_order_usd: float | None = None,
        max_daily_loss_pct: float | None = None,
        max_position_pct: float | None = None,
    ) -> tuple[bool, str]:
        self._roll_day()
        self.note_portfolio_value(portfolio_value)
        max_order = max_order_usd if max_order_usd is not None else config.EXCHANGE_MAX_ORDER_USD
        daily_loss_pct = (
            max_daily_loss_pct if max_daily_loss_pct is not None else config.EXCHANGE_MAX_DAILY_LOSS_PCT
        )
        pos_pct_limit = (
            max_position_pct if max_position_pct is not None else config.EXCHANGE_MAX_POSITION_PCT
        )
        if amount_usd > max_order:
            return False, f"Ордер ${amount_usd:.0f} > лимита ${max_order:.0f}"
        if portfolio_value > 0:
            pos_pct = amount_usd / portfolio_value
            if pos_pct > pos_pct_limit:
                return False, (
                    f"Позиция {pos_pct * 100:.0f}% > лимита "
                    f"{pos_pct_limit * 100:.0f}%"
                )
        book_pnl = portfolio_pnl_pct if portfolio_pnl_pct is not None else pnl_pct
        if book_pnl <= -daily_loss_pct:
            return False, f"Просадка портфеля {book_pnl:.1f}% — торговля заблокирована"
        if self.day_start_value > 0 and portfolio_value > 0:
            daily_dd = (self.day_start_value - portfolio_value) / self.day_start_value * 100
            if daily_dd >= daily_loss_pct:
                return False, f"Дневная просадка портфеля {daily_dd:.1f}% — лимит {daily_loss_pct:.0f}%"
        if self.daily_loss_usd >= portfolio_value * daily_loss_pct / 100:
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
        self.api_key = os.environ.get("BINANCE_API_KEY", "").strip()
        self.api_secret = os.environ.get("BINANCE_API_SECRET", "").strip()
        self.testnet = config.EXCHANGE_TESTNET
        self.base_url = self.TESTNET if self.testnet else self.LIVE
        self.risk = ExchangeRiskManager()
        self.enabled = bool(self.api_key and self.api_secret and config.EXCHANGE_ENABLED)
        self._symbol_rules: dict[str, dict[str, Any]] = {}
        self._rules_ts = 0.0
        self._time_offset_ms = 0
        self._time_sync_ts = 0.0
        self._recv_window = int(os.environ.get("BINANCE_RECV_WINDOW", "60000"))
        self._balances_cache: dict[str, float] = {}
        self._balances_cache_ts = 0.0

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
            "sync_to_paper": config.EXCHANGE_SYNC_TO_PAPER,
            "sync_from_paper": config.EXCHANGE_SYNC_FROM_PAPER,
            "note": (
                "Двусторонняя sync: testnet↔paper"
                if self.enabled and config.EXCHANGE_SYNC_TO_PAPER and config.EXCHANGE_SYNC_FROM_PAPER
                else "Testnet ордера автоматически синхронизируются с paper-кошельком"
                if self.enabled and config.EXCHANGE_SYNC_TO_PAPER
                else "Задай BINANCE_API_KEY + EXCHANGE_ENABLED=true"
                if not self.enabled
                else "Синхронизация с paper выключена (EXCHANGE_SYNC_TO_PAPER=false)"
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

    async def _sync_server_time(self) -> None:
        """Align local clock with Binance — fixes -1021 / HTTP 400 timestamp errors."""
        if time.time() - self._time_sync_ts < 300:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.base_url}/api/v3/time")
                r.raise_for_status()
                server_ms = int(r.json().get("serverTime", 0))
            local_ms = int(time.time() * 1000)
            self._time_offset_ms = server_ms - local_ms
            self._time_sync_ts = time.time()
            if abs(self._time_offset_ms) > 3000:
                logger.warning("Binance time skew: %d ms — using server offset", self._time_offset_ms)
        except Exception as e:
            logger.debug("time sync skipped: %s", e)

    def _timestamp_ms(self) -> int:
        return int(time.time() * 1000) + self._time_offset_ms

    @staticmethod
    def _parse_binance_error(body: str, status: int, *, testnet: bool = True) -> str:
        """Human-readable hint from Binance JSON error body."""
        try:
            data = json.loads(body)
        except Exception:
            return f"HTTP {status} — {body[:200]}"
        code = data.get("code")
        msg = data.get("msg", "")
        hints = {
            -1021: "Время ПК не совпадает с Binance — синхронизируй часы Windows или перезапусти бота",
            -1022: "Неверная подпись — проверь BINANCE_API_SECRET без пробелов в .env",
            -2014: "Неверный формат API Key — ключ с testnet.binance.vision, не с binance.com",
            -2015: "Ключ недействителен — перевыпусти на testnet.binance.vision",
            -1102: "Параметр запроса неверен — обнови TradeSim (git pull)",
        }
        hint = hints.get(code, "")
        where = "testnet.binance.vision" if testnet else "api.binance.com"
        base = f"Binance {code}: {msg}" if code else f"HTTP {status}: {msg or body[:120]}"
        if hint:
            return f"{base} — {hint}"
        if status == 400 and not code:
            return (
                f"{base} — проверь ключи на {where}, без пробелов в .env, "
                "перевыпусти если светились в чате"
            )
        return base

    async def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = dict(params or {})
        url = f"{self.base_url}{path}"
        headers = {"X-MBX-APIKEY": self.api_key} if signed else {}
        if signed:
            await self._sync_server_time()
            params["timestamp"] = self._timestamp_ms()
            params["recvWindow"] = self._recv_window
            url = f"{url}?{self._sign(params)}"
            params = None
        async with httpx.AsyncClient(timeout=20) as client:
            if method == "GET":
                r = await client.get(url, params=params, headers=headers)
            else:
                r = await client.post(url, headers=headers)
            if r.status_code == 451:
                raise RuntimeError(
                    "Binance geo-block (HTTP 451) — с твоего IP testnet недоступен. "
                    "Запускай сервер на Windows дома, не через VPN в заблокированный регион."
                )
            if r.status_code in (401, 403):
                raise RuntimeError(
                    f"Binance отклонил ключ (HTTP {r.status_code}) — проверь API Key/Secret и "
                    f"что ключ создан на {'testnet.binance.vision' if self.testnet else 'binance.com'}"
                )
            if r.status_code >= 400:
                raise RuntimeError(self._parse_binance_error(r.text, r.status_code, testnet=self.testnet))
            return r.json()

    async def verify_connection(self) -> dict[str, Any]:
        """Ping signed API — for startup / UI diagnostics."""
        if not self.enabled:
            return {
                "ok": False,
                "enabled": False,
                "note": "Задай BINANCE_API_KEY + BINANCE_API_SECRET + EXCHANGE_ENABLED=true в .env",
            }
        try:
            acct = await self.account_balances()
            usdt = next((b for b in acct.get("balances", []) if b["asset"] == "USDT"), None)
            return {
                "ok": True,
                "enabled": True,
                "testnet": self.testnet,
                "base_url": self.base_url,
                "assets": len(acct.get("balances", [])),
                "usdt_free": round(usdt["free"], 2) if usdt else 0,
                "note": "Testnet подключён" if self.testnet else "⚠️ LIVE биржа подключена",
            }
        except Exception as e:
            logger.warning("exchange verify failed: %s", e)
            return {
                "ok": False,
                "enabled": True,
                "testnet": self.testnet,
                "error": str(e),
                "note": "Проверь ключи и EXCHANGE_TESTNET=true для testnet",
            }

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
        from decimal import Decimal, ROUND_DOWN

        d_qty = Decimal(str(qty))
        d_step = Decimal(str(step))
        if d_step <= 0:
            return qty
        units = (d_qty / d_step).to_integral_value(rounding=ROUND_DOWN)
        return float(units * d_step)

    async def account_balances(self) -> dict[str, Any]:
        if not self.enabled:
            return {"mode": "paper", "balances": [], "note": "Нет API ключей — paper режим"}
        data = await self._request("GET", "/api/v3/account", signed=True)
        balances = [
            {"asset": b["asset"], "free": float(b["free"]), "locked": float(b["locked"])}
            for b in data.get("balances", [])
            if float(b["free"]) + float(b["locked"]) > 0
        ]
        self._balances_cache = {b["asset"]: b["free"] + b["locked"] for b in balances}
        self._balances_cache_ts = time.time()
        return {"mode": "testnet" if self.testnet else "live", "balances": balances[:30]}

    async def asset_balance(self, asset: str) -> float:
        """Free+locked for one asset (cached ~20s)."""
        if time.time() - self._balances_cache_ts > 20:
            await self.account_balances()
        return float(self._balances_cache.get(asset, 0.0))

    async def deposit_address(self, coin: str = "USDT", network: str = "TRC20") -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("exchange disabled")
        data = await self._request(
            "GET",
            "/sapi/v1/capital/deposit/address",
            {"coin": coin, "network": network},
            signed=True,
        )
        return {
            "address": data.get("address", ""),
            "tag": data.get("tag") or data.get("memo") or "",
            "url": data.get("url", ""),
        }

    async def deposit_history(self, coin: str = "USDT", limit: int = 10) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            data = await self._request(
                "GET",
                "/sapi/v1/capital/deposit/hisrec",
                {"coin": coin, "limit": min(limit, 50)},
                signed=True,
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("deposit_history: %s", e)
            return []

    async def withdraw_usdt(
        self,
        amount: float,
        address: str,
        network: str = "TRC20",
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("exchange disabled")
        params = {
            "coin": "USDT",
            "address": address,
            "amount": round(amount, 2),
            "network": network,
        }
        data = await self._request("POST", "/sapi/v1/capital/withdraw/apply", params, signed=True)
        return {
            "id": data.get("id"),
            "amount": amount,
            "address": address,
            "network": network,
            "status": "submitted",
        }

    async def withdraw_history(self, coin: str = "USDT", limit: int = 10) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            data = await self._request(
                "GET",
                "/sapi/v1/capital/withdraw/history",
                {"coin": coin, "limit": min(limit, 50)},
                signed=True,
            )
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("withdraw_history: %s", e)
            return []

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

    def order_limits(self) -> dict[str, float]:
        from exchange.trading_mode import trading_mode
        from learning.live_micro_mode import is_live_micro_active, live_micro_limits
        if trading_mode.is_live() and is_live_micro_active():
            return live_micro_limits()
        if trading_mode.is_live():
            return {
                "max_order_usd": config.LIVE_MAX_ORDER_USD,
                "max_daily_loss_pct": config.LIVE_MAX_DAILY_LOSS_PCT,
                "max_position_pct": config.LIVE_MAX_POSITION_PCT,
            }
        return {
            "max_order_usd": config.EXCHANGE_MAX_ORDER_USD,
            "max_daily_loss_pct": config.EXCHANGE_MAX_DAILY_LOSS_PCT,
            "max_position_pct": config.EXCHANGE_MAX_POSITION_PCT,
        }

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        amount_usd: float,
        portfolio_value: float,
        pnl_pct: float,
        price: float | None = None,
        from_paper_sync: bool = False,
        portfolio_pnl_pct: float | None = None,
    ) -> dict[str, Any]:
        side = side.lower()
        if side not in ("buy", "sell"):
            return {"ok": False, "error": "side must be buy or sell"}

        limits = self.order_limits()
        ok, reason = self.risk.check_order(
            side, amount_usd, portfolio_value, pnl_pct,
            portfolio_pnl_pct=portfolio_pnl_pct,
            **limits,
        )
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
        self.risk.record_result(pnl_delta)
        return {
            "ok": True,
            "mode": "live",
            "from_paper_sync": from_paper_sync,
            "order": data,
            "order_id": data.get("orderId"),
            "status": data.get("status"),
            "fills_quote": round(fills_quote, 4),
            "order_type": "market",
        }

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        amount_usd: float,
        limit_price: float,
        portfolio_value: float,
        pnl_pct: float,
        price: float | None = None,
        portfolio_pnl_pct: float | None = None,
    ) -> dict[str, Any]:
        side = side.lower()
        if side not in ("buy", "sell"):
            return {"ok": False, "error": "side must be buy or sell"}
        if limit_price <= 0:
            return {"ok": False, "error": "limit_price must be > 0"}

        limits = self.order_limits()
        ok, reason = self.risk.check_order(
            side, amount_usd, portfolio_value, pnl_pct,
            portfolio_pnl_pct=portfolio_pnl_pct,
            **limits,
        )
        if not ok:
            return {"ok": False, "error": reason, "mode": "blocked"}

        if not self.enabled:
            return {
                "ok": False,
                "mode": "paper",
                "note": "Limit на бирже — включи EXCHANGE_ENABLED",
            }

        rules = await self._load_symbol_rules(symbol)
        mark = price or limit_price
        qty = self._round_step(amount_usd / mark, rules["step_size"])
        if qty < rules["min_qty"]:
            return {"ok": False, "error": f"Слишком мало base (min {rules['min_qty']})"}
        if qty * limit_price < rules["min_notional"]:
            return {"ok": False, "error": f"Notional < ${rules['min_notional']}"}

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "price": f"{limit_price:.8f}".rstrip("0").rstrip("."),
            "quantity": qty,
        }
        try:
            data = await self._request("POST", "/api/v3/order", params, signed=True)
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": e.response.text, "mode": "live"}

        return {
            "ok": True,
            "mode": "testnet" if self.testnet else "live",
            "order_type": "limit",
            "order": data,
            "order_id": data.get("orderId"),
            "status": data.get("status"),
            "limit_price": limit_price,
            "quantity": qty,
        }

    async def place_stop_limit_order(
        self,
        symbol: str,
        side: str,
        amount_usd: float,
        stop_price: float,
        limit_price: float,
        portfolio_value: float,
        pnl_pct: float,
        price: float | None = None,
        portfolio_pnl_pct: float | None = None,
    ) -> dict[str, Any]:
        side = side.lower()
        if side not in ("buy", "sell"):
            return {"ok": False, "error": "side must be buy or sell"}
        if stop_price <= 0 or limit_price <= 0:
            return {"ok": False, "error": "stop_price and limit_price required"}

        limits = self.order_limits()
        ok, reason = self.risk.check_order(
            side, amount_usd, portfolio_value, pnl_pct,
            portfolio_pnl_pct=portfolio_pnl_pct,
            **limits,
        )
        if not ok:
            return {"ok": False, "error": reason, "mode": "blocked"}

        if not self.enabled:
            return {"ok": False, "mode": "paper", "note": "Stop-limit на бирже — включи EXCHANGE_ENABLED"}

        rules = await self._load_symbol_rules(symbol)
        mark = price or stop_price
        qty = self._round_step(amount_usd / mark, rules["step_size"])
        if qty * limit_price < rules["min_notional"]:
            return {"ok": False, "error": f"Notional < ${rules['min_notional']}"}

        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "STOP_LOSS_LIMIT",
            "timeInForce": "GTC",
            "stopPrice": f"{stop_price:.8f}".rstrip("0").rstrip("."),
            "price": f"{limit_price:.8f}".rstrip("0").rstrip("."),
            "quantity": qty,
        }
        try:
            data = await self._request("POST", "/api/v3/order", params, signed=True)
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": e.response.text, "mode": "live"}

        return {
            "ok": True,
            "mode": "testnet" if self.testnet else "live",
            "order_type": "stop_limit",
            "order": data,
            "order_id": data.get("orderId"),
            "status": data.get("status"),
            "stop_price": stop_price,
            "limit_price": limit_price,
            "quantity": qty,
        }

    async def cancel_order(self, symbol: str, order_id: int) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "exchange disabled"}
        try:
            data = await self._request(
                "DELETE", "/api/v3/order",
                {"symbol": symbol, "orderId": order_id},
                signed=True,
            )
            return {"ok": True, "order": data}
        except httpx.HTTPStatusError as e:
            return {"ok": False, "error": e.response.text}

    async def open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol
        try:
            data = await self._request("GET", "/api/v3/openOrders", params, signed=True)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("open_orders: %s", e)
            return []
