"""Testnet discipline — conservative params, no paper-learn leftovers."""

from __future__ import annotations

import logging
from typing import Any

import config
from learning.strategy_presets import apply_strategy_preset

logger = logging.getLogger(__name__)

TESTNET_DCA_FLOOR_HOURS = float(getattr(config, "TESTNET_MIN_DCA_HOURS", 6))
TESTNET_DIP_COOLDOWN_FLOOR = float(getattr(config, "TESTNET_MIN_DIP_COOLDOWN_MIN", 15))


def apply_testnet_conservative_trading(session, *, reset_timers: bool = False) -> dict[str, Any]:
    """Conservative preset + longer cooldowns — fewer fees, respects brain risk."""
    apply_strategy_preset(session, "conservative")
    p = dict(session.bot.get_params())
    p["dca_interval_hours"] = max(float(p.get("dca_interval_hours", 8)), TESTNET_DCA_FLOOR_HOURS)
    p["dip_cooldown_minutes"] = max(float(p.get("dip_cooldown_minutes", 10)), TESTNET_DIP_COOLDOWN_FLOOR)
    p["grid_cooldown_minutes"] = max(float(p.get("grid_cooldown_minutes", 6)), 8)
    p["scalp_cooldown_seconds"] = max(int(p.get("scalp_cooldown_seconds", 45)), 60)
    session.set_params_bounded(p)
    session.sync_base_params()

    if reset_timers:
        session.bot.last_dca_ts = 0.0
        session.bot.last_dip_ts = 0.0
        session.bot.last_spike_ts = 0.0

    return {
        "symbol": session.symbol,
        "label": session.label,
        "strategy_type": getattr(session, "strategy_type", "dca"),
        "params": session.bot.get_params(),
        "mode": "testnet_conservative",
    }


def apply_testnet_conservative_all(sessions: dict, *, reset_timers: bool = False) -> list[dict[str, Any]]:
    return [
        apply_testnet_conservative_trading(s, reset_timers=reset_timers)
        for s in sessions.values()
    ]


def apply_testnet_on_mode_switch(sessions: dict, mode: str) -> int:
    """When leaving paper for testnet/live, drop paper-learn aggression."""
    if mode not in ("testnet", "live"):
        return 0
    if not getattr(config, "TESTNET_APPLY_CONSERVATIVE_ON_SWITCH", True):
        return 0
    apply_testnet_conservative_all(sessions, reset_timers=True)
    logger.info("Testnet discipline: conservative params on %d markets", len(sessions))
    return len(sessions)
