"""Runtime trading mode — paper vs testnet vs live exchange."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import config

logger = logging.getLogger(__name__)

MODES = ("paper", "testnet", "live")
_STATE_FILE = config.DATA_DIR / "trading_mode.json"


def _load_state() -> dict[str, Any]:
    try:
        if _STATE_FILE.exists():
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning("trading_mode load: %s", e)
    return {}


def _load() -> str:
    mode = str(_load_state().get("mode", config.TRADING_MODE_DEFAULT)).lower()
    return mode if mode in MODES else config.TRADING_MODE_DEFAULT


def _save(mode: str, extra: dict[str, Any] | None = None) -> None:
    state = _load_state()
    state["mode"] = mode
    now = time.time()
    if extra:
        state.update(extra)
    if mode == "testnet" and not state.get("testnet_since"):
        state["testnet_since"] = now
    if mode == "paper" and not state.get("paper_since"):
        state["paper_since"] = now
    if mode == "live" and not state.get("live_since"):
        state["live_since"] = now
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


class TradingModeManager:
    """Paper simulation vs mirrored testnet/live orders."""

    def __init__(self):
        self._mode = _load()
        if not _load_state().get("paper_since"):
            _save(self._mode)

    @property
    def mode(self) -> str:
        return self._mode

    def milestones(self) -> dict[str, Any]:
        return _load_state()

    def set_mode(
        self,
        mode: str,
        *,
        exchange,
        readiness: dict[str, Any] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
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
                "error": "Live режим: задай EXCHANGE_TESTNET=false в .env и перезапусти",
                "mode": self._mode,
            }

        if mode == "testnet" and not exchange.testnet:
            return {
                "ok": False,
                "error": "Testnet режим: задай EXCHANGE_TESTNET=true в .env",
                "mode": self._mode,
            }

        allow_force = force and config.LIVE_ALLOW_FORCE
        allow_bypass = config.LIVE_BYPASS_READINESS and config.LIVE_ALLOW_FORCE
        if force and not config.LIVE_ALLOW_FORCE:
            logger.warning("Live force ignored — set LIVE_ALLOW_FORCE=true in .env to bypass readiness")
        if config.LIVE_BYPASS_READINESS and not config.LIVE_ALLOW_FORCE:
            logger.warning("LIVE_BYPASS_READINESS ignored without LIVE_ALLOW_FORCE=true")
        if mode == "live" and config.LIVE_REQUIRE_READINESS and not allow_force and not allow_bypass:
            if not readiness or not readiness.get("ready_for_live"):
                score = readiness.get("score_pct", 0) if readiness else 0
                failed = [
                    c["label"] for c in (readiness or {}).get("checks", [])
                    if c.get("required", True) and not c.get("ok")
                ]
                return {
                    "ok": False,
                    "error": (
                        f"Live заблокирован — готовность {score}%"
                        f"{': ' + ', '.join(failed[:3]) if failed else ''}"
                    ),
                    "mode": self._mode,
                    "live_readiness": readiness,
                }

        self._mode = mode
        _save(self._mode)
        logger.info("Trading mode → %s", mode)
        result = self.status(exchange)
        if mode == "live":
            result["warning"] = (
                f"⚠️ LIVE — реальные деньги · лимит ${config.LIVE_MAX_ORDER_USD}/ордер"
            )
        return result

    def should_mirror_to_exchange(self) -> bool:
        return self._mode in ("testnet", "live")

    def is_live(self) -> bool:
        return self._mode == "live"

    def status(self, exchange) -> dict[str, Any]:
        ex = exchange.status() if exchange else {}
        ready = self._mode == "paper" or bool(ex.get("enabled"))
        meta = self.milestones()
        return {
            "ok": True,
            "mode": self._mode,
            "label": {"paper": "Paper", "testnet": "Testnet", "live": "Live"}[self._mode],
            "exchange_enabled": bool(ex.get("enabled")),
            "exchange_testnet": bool(ex.get("testnet")),
            "mirror_bots": self.should_mirror_to_exchange(),
            "ready": ready,
            "note": self._note(ex),
            "testnet_days": round(max(0, (time.time() - float(meta.get("testnet_since", 0))) / 86400), 1)
            if meta.get("testnet_since")
            else 0,
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
