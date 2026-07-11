"""Simple self-tuning: adjust dip threshold based on paper results."""

from __future__ import annotations

import copy
from typing import Any

import config


class StrategyOptimizer:
  """Tunes only params in the configured niche — no cross-market learning."""

  BOUNDS = {
    "dca_amount": (10.0, 80.0),
    "dip_threshold_pct": (1.0, 10.0),
    "dip_extra_amount": (15.0, 80.0),
    "sma_period": (10, 50),
  }

  BOUNDS_VOLATILE = {
    "dca_amount": (5.0, 40.0),
    "dip_threshold_pct": (3.0, 15.0),
    "dip_extra_amount": (10.0, 60.0),
    "sma_period": (8, 30),
    "spike_threshold_pct": (5.0, 20.0),
    "spike_extra_amount": (10.0, 80.0),
  }

  def __init__(self, params: dict | None = None, bounds: dict | None = None):
    self.params = copy.deepcopy(params or config.STRATEGY)
    self.bounds = bounds or self.BOUNDS

  def get_params(self) -> dict:
    return copy.deepcopy(self.params)

  def should_tune(self, trade_count: int, vs_hold_pct: float | None) -> bool:
    if trade_count < config.MIN_TRADES_FOR_TUNING:
      return False
    if vs_hold_pct is None:
      return False
    return vs_hold_pct < -0.5

  def tune(self, vs_hold_pct: float, trade_count: int) -> tuple[dict, str]:
    p = copy.deepcopy(self.params)
    reason_parts = []

    if vs_hold_pct < 0:
      old_dip = p["dip_threshold_pct"]
      p["dip_threshold_pct"] = max(self.bounds["dip_threshold_pct"][0], old_dip - 0.5)
      reason_parts.append(f"порог DIP {old_dip}% → {p['dip_threshold_pct']}%")

      old_dca = p["dca_amount"]
      step = 5.0 if self.bounds["dca_amount"][1] <= 40 else 10.0
      p["dca_amount"] = max(self.bounds["dca_amount"][0], old_dca - step)
      reason_parts.append(f"DCA ${old_dca} → ${p['dca_amount']}")
    else:
      old_dip = p["dip_threshold_pct"]
      p["dip_threshold_pct"] = min(self.bounds["dip_threshold_pct"][1], old_dip + 0.3)
      reason_parts.append(f"порог DIP {old_dip}% → {p['dip_threshold_pct']}% (осторожнее)")

    self.apply_params(p)
    reason = (
      f"Автонастройка после {trade_count} сделок (vs hold {vs_hold_pct:+.2f}%): "
      + ", ".join(reason_parts)
    )
    return self.get_params(), reason

  def apply_params(self, params: dict) -> dict:
    for k, v in params.items():
      if k not in self.params:
        continue
      lo, hi = self.bounds.get(k, (v, v))
      if isinstance(v, int) or isinstance(self.params.get(k), int):
        self.params[k] = int(max(lo, min(hi, int(v))))
      else:
        self.params[k] = max(lo, min(hi, float(v)))
    return self.get_params()
