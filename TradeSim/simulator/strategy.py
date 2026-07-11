"""DCA + dip-buy strategy in one niche: BTC/USDT accumulation."""

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
    self.enabled = True

  def update_params(self, params: dict):
    self.params.update(params)

  def get_params(self) -> dict:
    return dict(self.params)

  def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
    if not self.enabled or price <= 0:
      return None

    now = time.time()
    interval = self.params["dca_interval_hours"] * 3600
    trade = None

    # Scheduled DCA
    if now - self.last_dca_ts >= interval:
      amount = self.params["dca_amount"]
      trade = self.engine.buy(price, amount, reason="DCA: плановая покупка")
      if trade:
        self.last_dca_ts = now

    # Extra buy on dip below SMA
    if sma and price < sma:
      dip_pct = (sma - price) / sma * 100
      if dip_pct >= self.params["dip_threshold_pct"]:
        extra = self.params["dip_extra_amount"]
        t2 = self.engine.buy(
          price,
          extra,
          reason=f"DIP: цена ниже SMA на {dip_pct:.1f}%",
        )
        if t2:
          trade = t2

      # Volatile coins: extra buy on deep spike below SMA
      spike_thr = self.params.get("spike_threshold_pct")
      if spike_thr and dip_pct >= spike_thr:
        spike_amt = self.params.get("spike_extra_amount", self.params["dip_extra_amount"])
        t3 = self.engine.buy(
          price,
          spike_amt,
          reason=f"SPIKE: резкая просадка {dip_pct:.1f}% — шанс на отскок",
        )
        if t3:
          trade = t3

    return trade

  def status(self, price: float, sma: float | None) -> dict[str, Any]:
    dip_pct = None
    if sma and price:
      dip_pct = round((sma - price) / sma * 100, 2)
    return {
      "enabled": self.enabled,
      "params": self.get_params(),
      "sma": round(sma, 2) if sma else None,
      "dip_pct": dip_pct,
      "next_dca_in_hours": max(
        0,
        round(
          self.params["dca_interval_hours"]
          - (time.time() - self.last_dca_ts) / 3600,
          1,
        ),
      ),
    }
