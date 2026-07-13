"""Active trading mode — lower cooldowns, more signals, more round-trips."""

from __future__ import annotations

from typing import Any

from learning.strategy_presets import apply_strategy_preset

# Multiply params — values <1 shorten cooldowns / ease entries
ACTIVE_MULTIPLIERS: dict[str, float] = {
    "dca_interval_hours": 0.25,
    "dip_cooldown_minutes": 0.35,
    "spike_cooldown_minutes": 0.35,
    "take_profit_cooldown_hours": 0.5,
    "stop_loss_cooldown_hours": 0.5,
    "grid_cooldown_minutes": 0.4,
    "grid_spacing_pct": 0.75,
    "entry_cooldown_minutes": 0.4,
    "rsi_buy_cooldown_minutes": 0.4,
    "rsi_sell_cooldown_minutes": 0.4,
    "scalp_cooldown_seconds": 0.45,
    "dip_threshold_pct": 0.8,
    "breakout_pct": 0.85,
    "scalp_move_pct": 0.85,
    "rsi_oversold": 1.08,
    "rsi_overbought": 0.92,
}

ACTIVE_DCA_EXTRAS: dict[str, float] = {
    "spike_threshold_pct": 5.0,
    "spike_extra_amount": 1.0,
}


def _scale_params(params: dict[str, Any], multipliers: dict[str, float]) -> dict[str, Any]:
    out = dict(params)
    for key, mult in multipliers.items():
        if key not in out:
            continue
        val = out[key]
        if isinstance(val, (int, float)):
            out[key] = type(val)(val * mult)
    return out


def apply_active_trading(session, *, reset_timers: bool = False) -> dict[str, Any]:
    """Aggressive preset + shorter cooldowns → noticeably more trades."""
    apply_strategy_preset(session, "aggressive")
    merged = _scale_params(session.bot.get_params(), ACTIVE_MULTIPLIERS)

    if getattr(session, "strategy_type", "dca") == "dca":
        for key, val in ACTIVE_DCA_EXTRAS.items():
            if key not in merged or key == "spike_extra_amount":
                base = merged.get("dip_extra_amount", merged.get("dca_amount", 25))
                if key == "spike_extra_amount":
                    merged["spike_extra_amount"] = base
                else:
                    merged[key] = val

    session.set_params_bounded(merged)

    if reset_timers:
        session.bot.last_dca_ts = 0.0
        session.bot.last_dip_ts = 0.0
        session.bot.last_spike_ts = 0.0
        session.bot.last_take_profit_ts = 0.0
        session.bot.last_stop_loss_ts = 0.0

    return {
        "symbol": session.symbol,
        "label": session.label,
        "strategy_type": getattr(session, "strategy_type", "dca"),
        "params": session.bot.get_params(),
        "mode": "active",
    }


def apply_active_all(sessions: dict, *, reset_timers: bool = False) -> list[dict[str, Any]]:
    return [
        apply_active_trading(s, reset_timers=reset_timers)
        for s in sessions.values()
    ]
