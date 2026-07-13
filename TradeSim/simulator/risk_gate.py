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


def blocks_new_buys(symbol: str = "") -> bool:
    if _portfolio_halt or _correlation_block:
        return True
    if symbol:
        from learning.protections import protections_engine
        blocked, _ = protections_engine.blocks_buy(symbol)
        return blocked
    return False


def halt_reason() -> str:
    if _portfolio_halt:
        return _halt_reason
    if _correlation_block:
        return _correlation_reason
    return ""


def protection_reason(symbol: str = "") -> str:
    if not symbol:
        return ""
    from learning.protections import protections_engine
    blocked, reason = protections_engine.blocks_buy(symbol)
    return reason if blocked else ""


def risk_status() -> dict[str, bool | str]:
    from learning.protections import protections_engine
    prot = protections_engine.status()
    return {
        "portfolio_halt": _portfolio_halt,
        "correlation_block": _correlation_block,
        "brain_reduce_aggression": _brain_reduce_aggression,
        "blocks_buys": blocks_new_buys(),
        "reason": halt_reason() or protection_reason(),
        "protections": prot,
    }
