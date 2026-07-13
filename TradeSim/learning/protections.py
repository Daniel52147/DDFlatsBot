"""Freqtrade-style protections — cooldown after losses, stoploss guard, trade frequency."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

_STATE_FILE = config.DATA_DIR / "protections_state.json"


class ProtectionsEngine:
    """Portfolio and per-market guards inspired by Freqtrade protections."""

    def __init__(self):
        self._global_cooldown_until = 0.0
        self._symbol_pause_until: dict[str, float] = {}
        self._recent_trades: list[dict[str, Any]] = []
        self._actions: list[dict[str, Any]] = []
        self._load_state()

    def _load_state(self) -> None:
        try:
            if _STATE_FILE.exists():
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                self._global_cooldown_until = float(data.get("global_cooldown_until", 0))
                self._symbol_pause_until = {
                    k: float(v) for k, v in (data.get("symbol_pause_until") or {}).items()
                }
        except Exception as e:
            logger.warning("protections state load: %s", e)

    def _save_state(self) -> None:
        try:
            _STATE_FILE.write_text(
                json.dumps(
                    {
                        "global_cooldown_until": self._global_cooldown_until,
                        "symbol_pause_until": self._symbol_pause_until,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("protections state save: %s", e)

    def _prune_recent(self, window_sec: float) -> None:
        cutoff = time.time() - window_sec
        self._recent_trades = [t for t in self._recent_trades if t["ts"] >= cutoff]

    def on_trade(self, symbol: str, trade: Any) -> list[dict[str, Any]]:
        """Record trade and apply protection rules. Returns actions taken."""
        if not config.PROTECTIONS_ENABLED:
            return []

        side = getattr(trade, "side", trade.get("side") if isinstance(trade, dict) else "")
        reason = getattr(trade, "reason", trade.get("reason") if isinstance(trade, dict) else "") or ""
        ts = getattr(trade, "ts", trade.get("ts") if isinstance(trade, dict) else time.time())
        price = float(getattr(trade, "price", trade.get("price", 0) if isinstance(trade, dict) else 0))
        amount_quote = float(
            getattr(trade, "amount_quote", trade.get("amount_quote", 0) if isinstance(trade, dict) else 0)
        )

        event = {
            "ts": float(ts),
            "symbol": symbol,
            "side": side,
            "reason": reason,
            "price": price,
            "amount_quote": amount_quote,
            "is_stop_loss": "STOP-LOSS" in reason.upper() or "STOP_LOSS" in reason.upper(),
            "is_losing_sell": side == "sell" and ("STOP" in reason.upper() or "−" in reason or "-" in reason),
        }
        self._recent_trades.append(event)
        self._prune_recent(max(config.PROTECTION_STOPLOSS_WINDOW_SEC, config.PROTECTION_COOLDOWN_WINDOW_SEC))

        actions: list[dict[str, Any]] = []
        actions.extend(self._check_stoploss_guard(symbol))
        actions.extend(self._check_cooldown_period())
        actions.extend(self._check_max_trades_per_day(symbol))
        for act in actions:
            self._actions.append({**act, "ts": time.time()})
        self._actions = self._actions[-50:]
        if actions:
            self._save_state()
        return actions

    def _check_stoploss_guard(self, symbol: str) -> list[dict[str, Any]]:
        window = config.PROTECTION_STOPLOSS_WINDOW_SEC
        self._prune_recent(window)
        stops = [
            t for t in self._recent_trades
            if t["symbol"] == symbol and t["is_stop_loss"]
        ]
        if len(stops) < config.PROTECTION_STOPLOSS_COUNT:
            return []

        until = time.time() + config.PROTECTION_STOPLOSS_PAUSE_SEC
        if self._symbol_pause_until.get(symbol, 0) >= until:
            return []

        self._symbol_pause_until[symbol] = until
        action = {
            "type": "stoploss_guard",
            "symbol": symbol,
            "until": until,
            "reason": f"{len(stops)} стоп-лосса за {window // 3600}ч — пауза бота",
        }
        logger.warning("[%s] StoplossGuard: pause %.0f min", symbol, config.PROTECTION_STOPLOSS_PAUSE_SEC / 60)
        return [action]

    def _check_cooldown_period(self) -> list[dict[str, Any]]:
        window = config.PROTECTION_COOLDOWN_WINDOW_SEC
        self._prune_recent(window)
        losing = [t for t in self._recent_trades if t["side"] == "sell" and t["is_losing_sell"]]
        if len(losing) < config.PROTECTION_COOLDOWN_LOSSES:
            return []

        until = time.time() + config.PROTECTION_COOLDOWN_PAUSE_SEC
        if self._global_cooldown_until >= until:
            return []

        self._global_cooldown_until = until
        action = {
            "type": "cooldown_period",
            "symbol": "*",
            "until": until,
            "reason": f"{len(losing)} убыточных продаж за {window // 60}мин — блок покупок",
        }
        logger.warning("CooldownPeriod: global buy block %.0f min", config.PROTECTION_COOLDOWN_PAUSE_SEC / 60)
        return [action]

    def _check_max_trades_per_day(self, symbol: str) -> list[dict[str, Any]]:
        if config.PROTECTION_MAX_TRADES_PER_DAY <= 0:
            return []
        day_sec = 86400
        self._prune_recent(day_sec)
        count = sum(1 for t in self._recent_trades if t["symbol"] == symbol)
        if count < config.PROTECTION_MAX_TRADES_PER_DAY:
            return []

        until = time.time() + config.PROTECTION_MAX_TRADES_PAUSE_SEC
        if self._symbol_pause_until.get(symbol, 0) >= until:
            return []

        self._symbol_pause_until[symbol] = until
        return [{
            "type": "max_trades",
            "symbol": symbol,
            "until": until,
            "reason": f"лимит {config.PROTECTION_MAX_TRADES_PER_DAY} сделок/день",
        }]

    def blocks_buy(self, symbol: str = "") -> tuple[bool, str]:
        if not config.PROTECTIONS_ENABLED:
            return False, ""
        now = time.time()
        if self._global_cooldown_until > now:
            left = int((self._global_cooldown_until - now) / 60)
            return True, f"CooldownPeriod: покупки заблокированы ещё {left} мин"
        if symbol:
            until = self._symbol_pause_until.get(symbol, 0)
            if until > now:
                left = int((until - now) / 60)
                return True, f"Protection {symbol}: пауза ещё {left} мин"
        return False, ""

    def clear_symbol(self, symbol: str) -> None:
        self._symbol_pause_until.pop(symbol, None)
        self._save_state()

    def clear_global(self) -> None:
        self._global_cooldown_until = 0.0
        self._save_state()

    def clear_all(self) -> None:
        self._global_cooldown_until = 0.0
        self._symbol_pause_until.clear()
        self._save_state()

    def status(self) -> dict[str, Any]:
        now = time.time()
        paused_symbols = {
            sym: round(max(0, until - now) / 60, 1)
            for sym, until in self._symbol_pause_until.items()
            if until > now
        }
        return {
            "enabled": config.PROTECTIONS_ENABLED,
            "global_cooldown_min": round(max(0, self._global_cooldown_until - now) / 60, 1),
            "global_active": self._global_cooldown_until > now,
            "paused_symbols": paused_symbols,
            "recent_actions": list(reversed(self._actions[-8:])),
            "rules": {
                "stoploss_guard": (
                    f"{config.PROTECTION_STOPLOSS_COUNT} стопов / "
                    f"{config.PROTECTION_STOPLOSS_WINDOW_SEC // 3600}ч → "
                    f"пауза {config.PROTECTION_STOPLOSS_PAUSE_SEC // 60}мин"
                ),
                "cooldown_period": (
                    f"{config.PROTECTION_COOLDOWN_LOSSES} убыт. продаж / "
                    f"{config.PROTECTION_COOLDOWN_WINDOW_SEC // 60}мин → "
                    f"блок {config.PROTECTION_COOLDOWN_PAUSE_SEC // 60}мин"
                ),
                "max_trades_per_day": (
                    f"{config.PROTECTION_MAX_TRADES_PER_DAY} сделок/день"
                    if config.PROTECTION_MAX_TRADES_PER_DAY > 0
                    else "выкл"
                ),
            },
        }


protections_engine = ProtectionsEngine()
