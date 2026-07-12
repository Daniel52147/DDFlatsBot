"""Global portfolio risk gate — blocks new buys during deep drawdown."""

from __future__ import annotations

_portfolio_halt = False
_halt_reason = ""
_correlation_block = False
_correlation_reason = ""
_brain_reduce_aggression = False


def set_portfolio_halt(active: bool, reason: str = "") -> None:
    global _portfolio_halt, _halt_reason
    _portfolio_halt = active
    _halt_reason = reason if active else ""


def set_correlation_block(active: bool, reason: str = "") -> None:
    global _correlation_block, _correlation_reason
    _correlation_block = active
    _correlation_reason = reason if active else ""


def set_brain_reduce_aggression(active: bool) -> None:
    global _brain_reduce_aggression
    _brain_reduce_aggression = active


def brain_reduce_aggression() -> bool:
    return _brain_reduce_aggression


def blocks_new_buys() -> bool:
    return _portfolio_halt or _correlation_block


def halt_reason() -> str:
    if _portfolio_halt:
        return _halt_reason
    if _correlation_block:
        return _correlation_reason
    return ""


def risk_status() -> dict[str, bool | str]:
    return {
        "portfolio_halt": _portfolio_halt,
        "correlation_block": _correlation_block,
        "brain_reduce_aggression": _brain_reduce_aggression,
        "blocks_buys": blocks_new_buys(),
        "reason": halt_reason(),
    }
