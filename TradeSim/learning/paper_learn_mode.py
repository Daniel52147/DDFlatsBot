"""Paper learning mode — maximum trades on virtual wallet for faster tuning."""

from __future__ import annotations

import logging
from typing import Any

import config
from learning.optimizer import StrategyOptimizer
from learning.trade_mode import apply_active_trading, _scale_params

logger = logging.getLogger(__name__)

PAPER_LEARN_MULTIPLIERS: dict[str, float] = {
    "dca_interval_hours": 0.12,
    "dip_cooldown_minutes": 0.2,
    "spike_cooldown_minutes": 0.2,
    "take_profit_cooldown_hours": 0.35,
    "stop_loss_cooldown_hours": 0.35,
    "grid_cooldown_minutes": 0.25,
    "grid_spacing_pct": 0.55,
    "entry_cooldown_minutes": 0.25,
    "rsi_buy_cooldown_minutes": 0.25,
    "rsi_sell_cooldown_minutes": 0.25,
    "scalp_cooldown_seconds": 0.25,
    "dip_threshold_pct": 0.65,
    "breakout_pct": 0.7,
    "scalp_move_pct": 0.7,
    "scalp_tp_pct": 0.85,
    "rsi_oversold": 1.12,
    "rsi_overbought": 0.88,
}


def is_paper_learn_mode() -> bool:
    if not config.PAPER_LEARN_ENABLED:
        return False
    try:
        from exchange.trading_mode import trading_mode
        return trading_mode.mode == "paper"
    except Exception:
        return True


def effective_min_trades_for_tuning(volatile: bool = False) -> int:
    if is_paper_learn_mode():
        return config.PAPER_LEARN_MIN_TRADES_TUNING
    return config.MIN_TRADES_VOLATILE if volatile else config.MIN_TRADES_FOR_TUNING


def effective_fast_learn_every_n() -> int:
    if is_paper_learn_mode():
        return config.PAPER_LEARN_FAST_EVERY_N
    return config.FAST_LEARN_EVERY_N_TRADES


def effective_portfolio_max_drawdown_pct() -> float:
    if is_paper_learn_mode():
        return config.PAPER_LEARN_MAX_DRAWDOWN_PCT
    return config.PORTFOLIO_MAX_DRAWDOWN_PCT


def apply_paper_learn_trading(session, *, reset_timers: bool = False) -> dict[str, Any]:
    """Stack aggressive + paper-learn caps → many round-trips for SQLite learning."""
    apply_active_trading(session, reset_timers=False)
    merged = _scale_params(session.bot.get_params(), PAPER_LEARN_MULTIPLIERS)

    merged["dca_interval_hours"] = min(
        float(merged.get("dca_interval_hours", 8)),
        config.PAPER_LEARN_DCA_MAX_HOURS,
    )
    merged["scalp_cooldown_seconds"] = min(
        int(merged.get("scalp_cooldown_seconds", 45)),
        config.PAPER_LEARN_SCALP_COOLDOWN_SEC,
    )
    merged["grid_cooldown_minutes"] = min(
        float(merged.get("grid_cooldown_minutes", 6)),
        config.PAPER_LEARN_GRID_COOLDOWN_MIN,
    )
    merged["dip_threshold_pct"] = max(0.8, float(merged.get("dip_threshold_pct", 2)) * 0.9)
    merged["grid_spacing_pct"] = max(0.8, float(merged.get("grid_spacing_pct", 1.5)) * 0.85)

    volatile = bool(getattr(session, "volatile", False) or getattr(session, "growth", False))
    session.optimizer.bounds = StrategyOptimizer.bounds_for_paper_learn(volatile)
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
        "mode": "paper_learn",
    }


def apply_paper_learn_all(sessions: dict, *, reset_timers: bool = False) -> list[dict[str, Any]]:
    return [
        apply_paper_learn_trading(session, reset_timers=reset_timers)
        for session in sessions.values()
    ]


def apply_paper_learn_on_boot(sessions: dict) -> int:
    if not is_paper_learn_mode() or not config.PAPER_LEARN_ON_START:
        return 0
    apply_paper_learn_all(sessions, reset_timers=config.PAPER_LEARN_RESET_TIMERS)
    logger.info("Paper learn mode: aggressive params on %d markets", len(sessions))
    return len(sessions)
