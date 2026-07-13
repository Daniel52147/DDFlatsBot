"""Live Micro — first real money: tiny orders, rare trades, fee-safe."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import config
from learning.strategy_presets import apply_strategy_preset
from learning.testnet_mode import apply_testnet_conservative_trading

logger = logging.getLogger(__name__)

_STATE_FILE = config.DATA_DIR / "live_prep.json"


def _load_state() -> dict[str, Any]:
    try:
        if _STATE_FILE.exists():
            return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(data: dict[str, Any]) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def is_live_micro_active() -> bool:
    return bool(_load_state().get("live_micro_active"))


def set_live_micro_active(active: bool) -> None:
    state = _load_state()
    state["live_micro_active"] = active
    state["live_micro_since"] = time.time() if active else state.get("live_micro_since", 0)
    _save_state(state)


def apply_live_micro_trading(session, *, reset_timers: bool = False) -> dict[str, Any]:
    """Ultra-conservative: ~1–3 trades/day/market, small size, higher TP bar."""
    apply_testnet_conservative_trading(session, reset_timers=False)
    apply_strategy_preset(session, "conservative")
    p = dict(session.bot.get_params())
    p["dca_interval_hours"] = max(float(p.get("dca_interval_hours", 8)), config.LIVE_MICRO_DCA_HOURS)
    p["dip_cooldown_minutes"] = max(float(p.get("dip_cooldown_minutes", 15)), config.LIVE_MICRO_DIP_COOLDOWN_MIN)
    p["spike_cooldown_minutes"] = max(float(p.get("spike_cooldown_minutes", 30)), 45)
    p["grid_cooldown_minutes"] = max(float(p.get("grid_cooldown_minutes", 8)), 20)
    p["scalp_cooldown_seconds"] = max(int(p.get("scalp_cooldown_seconds", 60)), 300)
    p["take_profit_pct"] = max(float(p.get("take_profit_pct", 2)), config.LIVE_MICRO_TAKE_PROFIT_PCT)
    p["dip_threshold_pct"] = max(float(p.get("dip_threshold_pct", 1.5)), 2.5)
    p["dca_amount"] = min(float(p.get("dca_amount", 25)), config.LIVE_MICRO_ORDER_USD)
    p["max_buy_pct_of_cash"] = min(float(p.get("max_buy_pct_of_cash", 0.5)), 0.25)
    session.set_params_bounded(p)
    session.sync_base_params()

    if reset_timers:
        session.bot.last_dca_ts = 0.0
        session.bot.last_dip_ts = 0.0
        session.bot.last_spike_ts = 0.0

    return {
        "symbol": session.symbol,
        "label": session.label,
        "mode": "live_micro",
        "params": session.bot.get_params(),
    }


def apply_live_micro_all(sessions: dict, *, reset_timers: bool = False) -> list[dict[str, Any]]:
    return [apply_live_micro_trading(s, reset_timers=reset_timers) for s in sessions.values()]


def live_micro_limits() -> dict[str, float]:
    return {
        "max_order_usd": config.LIVE_MICRO_ORDER_USD,
        "max_daily_loss_pct": min(config.LIVE_MAX_DAILY_LOSS_PCT, 2.0),
        "max_position_pct": min(config.LIVE_MAX_POSITION_PCT, 0.05),
    }
