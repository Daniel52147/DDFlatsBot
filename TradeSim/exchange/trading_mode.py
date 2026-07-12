"""Runtime trading mode — paper vs testnet vs live exchange."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

MODES = ("paper", "testnet", "live")
_STATE_FILE = config.DATA_DIR / "trading_mode.json"


def _load() -> str:
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            mode = str(data.get("mode", "paper")).lower()
            if mode in MODES:
                return mode
    except Exception as e:
        logger.warning("trading_mode load: %s", e)
    return config.TRADING_MODE_DEFAULT


def _save(mode: str) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({"mode": mode}, indent=2), encoding="utf-8")


class TradingModeManager:
    """Paper simulation vs mirrored testnet/live orders."""

    def __init__(self):
        self._mode = _load()

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str, *, exchange) -> dict[str, Any]:
        mode = str(mode).lower().strip()
        if mode not in MODES:
            return {"ok": False, "error": f"unknown mode {mode}", "allowed": list(MODES)}

        if mode == "paper":
            self._mode = "paper"
            _save(self._mode)
            return self.status(exchange)

        if not exchange.enabled:
            return {
                "ok": False,
                "error": "Нужны BINANCE_API_KEY + EXCHANGE_ENABLED=true в .env",
                "mode": self._mode,
            }

        if mode == "live" and exchange.testnet:
            return {
                "ok": False,
                "error": "Live режим: задай EXCHANGE_TESTNET=false в .env",
                "mode": self._mode,
            }

        if mode == "testnet" and not exchange.testnet:
            return {
                "ok": False,
                "error": "Testnet режим: задай EXCHANGE_TESTNET=true в .env",
                "mode": self._mode,
            }

        self._mode = mode
        _save(self._mode)
        logger.info("Trading mode → %s", mode)
        return self.status(exchange)

    def should_mirror_to_exchange(self) -> bool:
        return self._mode in ("testnet", "live")

    def status(self, exchange) -> dict[str, Any]:
        ex = exchange.status() if exchange else {}
        ready = self._mode == "paper" or bool(ex.get("enabled"))
        return {
            "ok": True,
            "mode": self._mode,
            "label": {"paper": "Paper", "testnet": "Testnet", "live": "Live"}[self._mode],
            "exchange_enabled": bool(ex.get("enabled")),
            "exchange_testnet": bool(ex.get("testnet")),
            "mirror_bots": self.should_mirror_to_exchange(),
            "ready": ready,
            "note": self._note(ex),
        }

    def _note(self, ex: dict[str, Any]) -> str:
        if self._mode == "paper":
            return "Только бумажный счёт — биржа не трогается"
        if not ex.get("enabled"):
            return "Добавь API ключи для реальной торговли"
        if self._mode == "testnet":
            return "Бот дублирует сделки на Binance TESTNET"
        return "⚠️ LIVE — реальные деньги на Binance"


trading_mode = TradingModeManager()
