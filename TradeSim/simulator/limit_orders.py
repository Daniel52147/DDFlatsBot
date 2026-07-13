"""Paper limit and stop-limit orders — fill on tick like a mini order book."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

OrderType = Literal["limit", "stop_limit"]


@dataclass
class PendingOrder:
    id: str
    symbol: str
    side: str
    amount_usd: float
    limit_price: float
    stop_price: float | None = None
    order_type: OrderType = "limit"
    reason: str = "LIMIT"
    created_ts: float = field(default_factory=time.time)
    triggered: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "amount_usd": self.amount_usd,
            "limit_price": self.limit_price,
            "stop_price": self.stop_price,
            "order_type": self.order_type,
            "reason": self.reason,
            "created_ts": self.created_ts,
            "triggered": self.triggered,
            "status": "open",
        }


class LimitOrderBook:
    """Per-market pending limit orders for paper trading."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.orders: list[PendingOrder] = []

    def add(
        self,
        side: str,
        amount_usd: float,
        limit_price: float,
        *,
        order_type: OrderType = "limit",
        stop_price: float | None = None,
        reason: str = "LIMIT",
    ) -> PendingOrder:
        side = side.lower()
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if amount_usd <= 0 or limit_price <= 0:
            raise ValueError("amount and price must be positive")
        if order_type == "stop_limit" and not stop_price:
            raise ValueError("stop_limit requires stop_price")
        order = PendingOrder(
            id=uuid.uuid4().hex[:12],
            symbol=self.symbol,
            side=side,
            amount_usd=amount_usd,
            limit_price=limit_price,
            stop_price=stop_price,
            order_type=order_type,
            reason=reason,
        )
        self.orders.append(order)
        return order

    def cancel(self, order_id: str) -> bool:
        before = len(self.orders)
        self.orders = [o for o in self.orders if o.id != order_id]
        return len(self.orders) < before

    def cancel_all(self) -> int:
        n = len(self.orders)
        self.orders.clear()
        return n

    def open_orders(self) -> list[dict[str, Any]]:
        return [o.to_dict() for o in self.orders]

    def _should_fill(self, order: PendingOrder, price: float) -> bool:
        if order.order_type == "limit":
            if order.side == "buy":
                return price <= order.limit_price
            return price >= order.limit_price

        # stop_limit: trigger stop, then fill at limit
        if not order.triggered:
            if order.side == "buy" and order.stop_price and price >= order.stop_price:
                order.triggered = True
            elif order.side == "sell" and order.stop_price and price <= order.stop_price:
                order.triggered = True
            else:
                return False
        if order.side == "buy":
            return price <= order.limit_price
        return price >= order.limit_price

    def check_fills(self, price: float, engine) -> list[Any]:
        """Return filled Trade objects from engine."""
        filled = []
        remaining: list[PendingOrder] = []
        for order in self.orders:
            if not self._should_fill(order, price):
                remaining.append(order)
                continue
            fill_price = order.limit_price
            if order.side == "buy":
                trade = engine.buy(fill_price, order.amount_usd, reason=f"LIMIT: {order.reason}", symbol=self.symbol)
            else:
                base = order.amount_usd / fill_price if fill_price > 0 else 0
                trade = engine.sell(fill_price, base, reason=f"LIMIT: {order.reason}")
            if trade:
                filled.append(trade)
            else:
                remaining.append(order)
        self.orders = remaining
        return filled
