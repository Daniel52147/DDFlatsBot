"""Global portfolio risk gate — blocks new buys during deep drawdown."""

from __future__ import annotations

_portfolio_halt = False
_halt_reason = ""


def set_portfolio_halt(active: bool, reason: str = "") -> None:
    global _portfolio_halt, _halt_reason
    _portfolio_halt = active
    _halt_reason = reason if active else ""


def blocks_new_buys() -> bool:
    return _portfolio_halt


def halt_reason() -> str:
    return _halt_reason
