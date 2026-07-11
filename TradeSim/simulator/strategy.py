"""DCA + dip-buy strategy with one buy per tick guard."""

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

    # One buy per tick — DCA has priority over opportunistic DIP/SPIKE
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
