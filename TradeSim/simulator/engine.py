"""Virtual wallet and order execution with realistic fees/slippage."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import config


@dataclass
class Position:
    quote: float = config.INITIAL_BALANCE
    base: float = 0.0

    def total_value(self, price: float) -> float:
        return self.quote + self.base * price


@dataclass
class Trade:
    id: int | None
    ts: float
    side: str
    price: float
    amount_quote: float
    amount_base: float
    fee: float
    reason: str
    balance_quote: float
    balance_base: float
    portfolio_value: float


class SimulatorEngine:
    def __init__(self, initial_balance: float | None = None):
        bal = initial_balance if initial_balance is not None else config.INITIAL_BALANCE
        self.position = Position(quote=bal, base=0.0)
        self.trades: list[Trade] = []
        self._trade_counter = 0
        self.start_balance = bal
        self.start_ts = time.time()

    def _apply_slippage(self, price: float, side: str) -> float:
        slip = config.SLIPPAGE_RATE
        if side == "buy":
            return price * (1 + slip)
        return price * (1 - slip)

    def buy(self, price: float, amount_quote: float, reason: str) -> Trade | None:
        if amount_quote <= 0 or self.position.quote < amount_quote:
            return None
        fill = self._apply_slippage(price, "buy")
        fee = amount_quote * config.FEE_RATE
        net = amount_quote - fee
        base_got = net / fill
        self.position.quote -= amount_quote
        self.position.base += base_got
        self._trade_counter += 1
        trade = Trade(
            id=self._trade_counter,
            ts=time.time(),
            side="buy",
            price=fill,
            amount_quote=amount_quote,
            amount_base=base_got,
            fee=fee,
            reason=reason,
            balance_quote=self.position.quote,
            balance_base=self.position.base,
            portfolio_value=self.position.total_value(price),
        )
        self.trades.append(trade)
        return trade

    def sell(self, price: float, amount_base: float, reason: str) -> Trade | None:
        if amount_base <= 0 or self.position.base < amount_base:
            return None
        fill = self._apply_slippage(price, "sell")
        gross = amount_base * fill
        fee = gross * config.FEE_RATE
        net = gross - fee
        self.position.base -= amount_base
        self.position.quote += net
        self._trade_counter += 1
        trade = Trade(
            id=self._trade_counter,
            ts=time.time(),
            side="sell",
            price=fill,
            amount_quote=gross,
            amount_base=amount_base,
            fee=fee,
            reason=reason,
            balance_quote=self.position.quote,
            balance_base=self.position.base,
            portfolio_value=self.position.total_value(price),
        )
        self.trades.append(trade)
        return trade

    def snapshot(self, price: float) -> dict[str, Any]:
        pv = self.position.total_value(price)
        pnl = pv - self.start_balance
        pnl_pct = (pnl / self.start_balance * 100) if self.start_balance else 0
        hold_value = self.start_balance / price if price else 0
        hold_pnl_pct = ((price * hold_value - self.start_balance) / self.start_balance * 100) if self.start_balance else 0
        return {
            "quote": round(self.position.quote, 2),
            "base": round(self.position.base, 8),
            "price": price,
            "portfolio_value": round(pv, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "vs_hold_pct": round(pnl_pct - hold_pnl_pct, 2),
            "trade_count": len(self.trades),
            "start_balance": self.start_balance,
        }

    def reset(self, initial_balance: float | None = None):
        bal = initial_balance if initial_balance is not None else config.INITIAL_BALANCE
        self.position = Position(quote=bal, base=0.0)
        self.trades.clear()
        self._trade_counter = 0
        self.start_balance = bal
        self.start_ts = time.time()
