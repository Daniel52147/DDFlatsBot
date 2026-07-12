"""Shared strategy preset multipliers — used by API and auto-tactics."""

from __future__ import annotations

from typing import Any

STRATEGY_PRESETS: dict[str, dict[str, dict[str, float]]] = {
    "dca": {
        "aggressive": {
            "dca_amount": 1.35,
            "dip_extra_amount": 1.4,
            "dip_threshold_pct": 0.85,
            "take_profit_fraction": 0.85,
        },
        "conservative": {
            "dca_amount": 0.75,
            "dip_extra_amount": 0.8,
            "dip_threshold_pct": 1.15,
            "stop_loss_pct": 0.9,
        },
        "balanced": {"dca_amount": 1.0, "dip_extra_amount": 1.0, "dip_threshold_pct": 1.0},
    },
    "grid": {
        "aggressive": {"grid_spacing_pct": 0.85, "grid_buy_amount": 1.3, "grid_sell_fraction": 0.9},
        "conservative": {"grid_spacing_pct": 1.15, "grid_buy_amount": 0.8, "grid_sell_fraction": 1.1},
        "balanced": {"grid_spacing_pct": 1.0, "grid_buy_amount": 1.0},
    },
    "momentum": {
        "aggressive": {"breakout_pct": 0.85, "momentum_buy_amount": 1.25, "trailing_stop_pct": 0.9},
        "conservative": {"breakout_pct": 1.15, "momentum_buy_amount": 0.8, "trailing_stop_pct": 1.1},
        "balanced": {"breakout_pct": 1.0, "momentum_buy_amount": 1.0},
    },
    "rsi": {
        "aggressive": {"rsi_buy_amount": 1.3, "rsi_oversold": 1.05, "rsi_overbought": 0.95},
        "conservative": {"rsi_buy_amount": 0.8, "rsi_oversold": 0.95, "rsi_overbought": 1.05},
        "balanced": {"rsi_buy_amount": 1.0},
    },
    "scalper": {
        "aggressive": {"scalp_buy_amount": 1.25, "scalp_move_pct": 0.9, "scalp_tp_pct": 0.85},
        "conservative": {"scalp_buy_amount": 0.8, "scalp_move_pct": 1.1, "scalp_tp_pct": 1.1},
        "balanced": {"scalp_buy_amount": 1.0, "scalp_move_pct": 1.0},
    },
}


def apply_strategy_preset(session, preset_name: str) -> bool:
    """Multiply bot params by preset multipliers for the session strategy type."""
    stype = getattr(session, "strategy_type", "dca")
    type_presets = STRATEGY_PRESETS.get(stype, STRATEGY_PRESETS["dca"])
    preset = type_presets.get(preset_name)
    if preset is None:
        return False
    merged = dict(session.bot.get_params())
    for key, mult in preset.items():
        if key in merged and isinstance(merged[key], (int, float)):
            merged[key] = type(merged[key])(merged[key] * mult)
    session.set_params_bounded(merged)
    return True


def preset_payload(session, preset_name: str) -> dict[str, Any] | None:
    if not apply_strategy_preset(session, preset_name):
        return None
    return {
        "ok": True,
        "symbol": session.symbol,
        "preset": preset_name,
        "strategy_type": getattr(session, "strategy_type", "dca"),
        "params": session.bot.get_params(),
    }
