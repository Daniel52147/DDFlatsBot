"""Simple self-tuning: adjust dip threshold based on paper results."""

from __future__ import annotations

import copy
from typing import Any

import config


class StrategyOptimizer:
  """Tunes only params in the configured niche — no cross-market learning."""

  BOUNDS = {
    "dca_amount": (50.0, 300.0),
    "dip_threshold_pct": (1.0, 8.0),
    "dip_extra_amount": (50.0, 400.0),
    "sma_period": (10, 50),
  }

  def __init__(self, params: dict | None = None):
    self.params = copy.deepcopy(params or config.STRATEGY)

  def get_params(self) -> dict:
    return copy.deepcopy(self.params)

  def should_tune(self, trade_count: int, vs_hold_pct: float | None) -> bool:
    if trade_count < config.MIN_TRADES_FOR_TUNING:
      return False
    if vs_hold_pct is None:
      return False
    # Tune when underperforming buy-and-hold
    return vs_hold_pct < -0.5

  def tune(self, vs_hold_pct: float, trade_count: int) -> tuple[dict, str]:
    p = copy.deepcopy(self.params)
    reason_parts = []

    if vs_hold_pct < 0:
      # Losing vs hold: buy dips more aggressively, smaller DCA chunks
      old_dip = p["dip_threshold_pct"]
      p["dip_threshold_pct"] = max(
        self.BOUNDS["dip_threshold_pct"][0],
        old_dip - 0.5,
      )
      reason_parts.append(f"порог DIP {old_dip}% → {p['dip_threshold_pct']}%")

      old_dca = p["dca_amount"]
      p["dca_amount"] = max(self.BOUNDS["dca_amount"][0], old_dca - 10)
      reason_parts.append(f"DCA ${old_dca} → ${p['dca_amount']}")
    else:
      # Beating hold: slightly more conservative dips
      old_dip = p["dip_threshold_pct"]
      p["dip_threshold_pct"] = min(
        self.BOUNDS["dip_threshold_pct"][1],
        old_dip + 0.3,
      )
      reason_parts.append(f"порог DIP {old_dip}% → {p['dip_threshold_pct']}% (осторожнее)")

    self.params = p
    reason = f"Автонастройка после {trade_count} сделок (vs hold {vs_hold_pct:+.2f}%): " + ", ".join(reason_parts)
    return p, reason

  def apply_params(self, params: dict):
    for k, v in params.items():
      if k in self.params:
        lo, hi = self.BOUNDS.get(k, (v, v))
        if isinstance(v, int):
          self.params[k] = int(max(lo, min(hi, v)))
        else:
          self.params[k] = max(lo, min(hi, float(v)))
