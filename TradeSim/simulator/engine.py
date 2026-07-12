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
    cost_basis: float = 0.0

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
        self.start_price: float = 0.0

    def note_price(self, price: float) -> None:
        """Record benchmark price for buy-and-hold comparison."""
        if price > 0 and self.start_price <= 0:
            self.start_price = price

    def _hold_pnl_pct(self, price: float) -> float:
        if not self.start_balance or not price or self.start_price <= 0:
            return 0.0
        hold_coins = self.start_balance / self.start_price
        hold_value = hold_coins * price
        return (hold_value - self.start_balance) / self.start_balance * 100

    def _apply_slippage(self, price: float, side: str) -> float:
        slip = config.SLIPPAGE_RATE
        if side == "buy":
            return price * (1 + slip)
        return price * (1 - slip)

    def buy(self, price: float, amount_quote: float, reason: str) -> Trade | None:
        from simulator.risk_gate import blocks_new_buys
        if blocks_new_buys():
            return None
        if amount_quote <= 0 or self.position.quote < amount_quote:
            return None
        fill = self._apply_slippage(price, "buy")
        fee = amount_quote * config.FEE_RATE
        net = amount_quote - fee
        base_got = net / fill
        self.position.quote -= amount_quote
        self.position.base += base_got
        # Economic cost = net quote that bought the base (after fee)
        self.position.cost_basis += net
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
        if self.position.base > 0:
            sold_frac = amount_base / self.position.base
            self.position.cost_basis *= max(0, 1 - sold_frac)
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

    def apply_exchange_fill(
        self,
        side: str,
        price: float,
        amount_base: float,
        amount_quote: float,
        fee: float,
        reason: str,
        mark_price: float | None = None,
    ) -> Trade | None:
        """Mirror real exchange fill — no extra paper slippage/fees."""
        side = side.lower()
        pv_price = mark_price if mark_price and mark_price > 0 else price
        if side == "buy":
            if amount_quote <= 0 or amount_base <= 0:
                return None
            if self.position.quote < amount_quote:
                return None
            self.position.quote -= amount_quote
            self.position.base += amount_base
            self.position.cost_basis += max(0, amount_quote - fee)
        elif side == "sell":
            if amount_base <= 0 or self.position.base < amount_base:
                return None
            sold_frac = amount_base / self.position.base
            self.position.cost_basis *= max(0, 1 - sold_frac)
            self.position.base -= amount_base
            self.position.quote += max(0, amount_quote)
        else:
            return None

        self._trade_counter += 1
        trade = Trade(
            id=self._trade_counter,
            ts=time.time(),
            side=side,
            price=price,
            amount_quote=amount_quote,
            amount_base=amount_base,
            fee=fee,
            reason=reason,
            balance_quote=self.position.quote,
            balance_base=self.position.base,
            portfolio_value=self.position.total_value(pv_price),
        )
        self.trades.append(trade)
        return trade

    def avg_entry_price(self) -> float | None:
        if self.position.base <= 0 or self.position.cost_basis <= 0:
            return None
        return self.position.cost_basis / self.position.base

    def snapshot(self, price: float) -> dict[str, Any]:
        self.note_price(price)
        pv = self.position.total_value(price)
        pnl = pv - self.start_balance
        pnl_pct = (pnl / self.start_balance * 100) if self.start_balance else 0
        hold_pnl_pct = self._hold_pnl_pct(price)
        avg = self.avg_entry_price()
        return {
            "quote": round(self.position.quote, 2),
            "base": round(self.position.base, 8),
            "price": price,
            "portfolio_value": round(pv, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "vs_hold_pct": round(pnl_pct - hold_pnl_pct, 2),
            "hold_pnl_pct": round(hold_pnl_pct, 2),
            "start_price": round(self.start_price, 8) if self.start_price else None,
            "trade_count": len(self.trades),
            "start_balance": self.start_balance,
            "avg_entry": round(avg, 8) if avg else None,
            "cost_profit_pct": round((price - avg) / avg * 100, 2) if avg and price else None,
        }

    def reset(self, initial_balance: float | None = None):
        bal = initial_balance if initial_balance is not None else config.INITIAL_BALANCE
        self.position = Position(quote=bal, base=0.0, cost_basis=0.0)
        self.trades.clear()
        self._trade_counter = 0
        self.start_balance = bal
        self.start_ts = time.time()
        self.start_price = 0.0

    def restore(
        self,
        quote: float,
        base: float,
        trade_counter: int,
        start_balance: float,
        start_ts: float,
        trades: list[dict] | None = None,
        cost_basis: float = 0.0,
        start_price: float = 0.0,
    ):
        self.position = Position(quote=quote, base=base, cost_basis=cost_basis or 0.0)
        self.start_balance = start_balance
        self.start_ts = start_ts
        self.start_price = start_price or 0.0
        self._trade_counter = trade_counter
        self.trades.clear()
        for row in trades or []:
            self.trades.append(Trade(
                id=row.get("id"),
                ts=row["ts"],
                side=row["side"],
                price=row["price"],
                amount_quote=row["amount_quote"],
                amount_base=row["amount_base"],
                fee=row.get("fee", 0),
                reason=row["reason"],
                balance_quote=row.get("balance_quote", 0),
                balance_base=row.get("balance_base", 0),
                portfolio_value=row.get("portfolio_value", 0),
            ))

    def export_trades(self, limit: int | None = None) -> list[dict[str, Any]]:
        rows = self.trades if limit is None else self.trades[-limit:]
        return [
            {
                "id": t.id,
                "ts": t.ts,
                "side": t.side,
                "price": t.price,
                "amount_quote": t.amount_quote,
                "amount_base": t.amount_base,
                "fee": t.fee,
                "reason": t.reason,
                "balance_quote": t.balance_quote,
                "balance_base": t.balance_base,
                "portfolio_value": t.portfolio_value,
            }
            for t in rows
        ]
