"""DCA + dip-buy + take-profit strategy."""

from __future__ import annotations

import time
from typing import Any

import config
from simulator.engine import SimulatorEngine, Trade


class StrategyBot:
  def __init__(self, engine: SimulatorEngine, params: dict | None = None):
    self.engine = engine
    self.params = dict(config.STRATEGY)
    if params:
      self.params.update(params)
    self.last_dca_ts = 0.0
    self.last_take_profit_ts = 0.0
    self.enabled = True

  def update_params(self, params: dict):
    self.params.update(params)

  def get_params(self) -> dict:
    return dict(self.params)

  def _maybe_take_profit(self, price: float, sma: float) -> Trade | None:
    tp_pct = self.params.get("take_profit_pct")
    if not tp_pct or self.engine.position.base <= 0:
      return None
    profit_pct = (price - sma) / sma * 100
    if profit_pct < tp_pct:
      return None
    cooldown = self.params.get("take_profit_cooldown_hours", 6) * 3600
    if time.time() - self.last_take_profit_ts < cooldown:
      return None
    fraction = self.params.get("take_profit_fraction", 0.15)
    amount_base = self.engine.position.base * fraction
    if amount_base * price < 3:
      return None
    trade = self.engine.sell(
      price, amount_base,
      reason=f"TAKE-PROFIT: +{profit_pct:.1f}% над SMA — фиксация прибыли",
    )
    if trade:
      self.last_take_profit_ts = time.time()
    return trade

  def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
    if not self.enabled or price <= 0:
      return None

    if sma and price > sma:
      tp = self._maybe_take_profit(price, sma)
      if tp:
        return tp

    now = time.time()
    interval = self.params["dca_interval_hours"] * 3600

    if now - self.last_dca_ts >= interval:
      trade = self.engine.buy(price, self.params["dca_amount"], reason="DCA: плановая покупка")
      if trade:
        self.last_dca_ts = now
        return trade

    if not sma or price >= sma:
      return None

    dip_pct = (sma - price) / sma * 100
    spike_thr = self.params.get("spike_threshold_pct")

    if spike_thr and dip_pct >= spike_thr:
      amt = self.params.get("spike_extra_amount", self.params["dip_extra_amount"])
      return self.engine.buy(
        price, amt,
        reason=f"SPIKE: резкая просадка {dip_pct:.1f}% — шанс на отскок",
      )

    if dip_pct >= self.params["dip_threshold_pct"]:
      return self.engine.buy(
        price, self.params["dip_extra_amount"],
        reason=f"DIP: цена ниже SMA на {dip_pct:.1f}%",
      )

    return None

  def status(self, price: float, sma: float | None) -> dict[str, Any]:
    dip_pct = None
    profit_pct = None
    if sma and price:
      dip_pct = round((sma - price) / sma * 100, 2)
      if price > sma:
        profit_pct = round((price - sma) / sma * 100, 2)
    return {
      "enabled": self.enabled,
      "params": self.get_params(),
      "sma": round(sma, 2) if sma else None,
      "dip_pct": dip_pct,
      "profit_pct": profit_pct,
      "next_dca_in_hours": max(
        0,
        round(
          self.params["dca_interval_hours"]
          - (time.time() - self.last_dca_ts) / 3600,
          1,
        ),
      ),
    }
