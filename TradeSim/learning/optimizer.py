"""Adaptive self-tuning from paper-trading results and trade patterns."""

from __future__ import annotations

import copy
from typing import Any

import config
from learning.trade_analyzer import analyze_trades


class StrategyOptimizer:
  """Tunes params per market using performance + trade-pattern analysis."""

  BOUNDS = {
    "dca_amount": (10.0, 80.0),
    "dip_threshold_pct": (1.0, 10.0),
    "dip_extra_amount": (15.0, 80.0),
    "sma_period": (10, 50),
    "take_profit_pct": (4.0, 18.0),
    "take_profit_fraction": (0.08, 0.40),
    "take_profit_cooldown_hours": (1.0, 12.0),
    "dca_interval_hours": (4, 48),
    "dip_cooldown_minutes": (10, 120),
    "spike_cooldown_minutes": (15, 180),
    "stop_loss_pct": (6.0, 20.0),
    "stop_loss_fraction": (0.10, 0.40),
  }

  BOUNDS_VOLATILE = {
    "dca_amount": (5.0, 40.0),
    "dip_threshold_pct": (2.0, 15.0),
    "dip_extra_amount": (10.0, 60.0),
    "sma_period": (8, 30),
    "spike_threshold_pct": (4.0, 20.0),
    "spike_extra_amount": (10.0, 80.0),
    "take_profit_pct": (3.0, 14.0),
    "take_profit_fraction": (0.10, 0.45),
    "take_profit_cooldown_hours": (0.5, 6.0),
    "dca_interval_hours": (2, 24),
    "dip_cooldown_minutes": (5, 60),
    "spike_cooldown_minutes": (10, 90),
    "stop_loss_pct": (8.0, 25.0),
    "stop_loss_fraction": (0.10, 0.45),
  }

  def __init__(self, params: dict | None = None, bounds: dict | None = None, volatile: bool = False):
    self.params = copy.deepcopy(params or config.STRATEGY)
    self.bounds = bounds or self.BOUNDS
    self.volatile = volatile

  def get_params(self) -> dict:
    return copy.deepcopy(self.params)

  def tune_interval_sec(self) -> int:
    return config.LEARNING_CHECK_VOLATILE_SEC if self.volatile else config.LEARNING_CHECK_SEC

  def min_trades(self) -> int:
    return config.MIN_TRADES_VOLATILE if self.volatile else config.MIN_TRADES_FOR_TUNING

  def should_tune(
      self,
      trade_count: int,
      vs_hold_pct: float | None,
      pnl_pct: float = 0,
      trades_since_tune: int = 0,
  ) -> bool:
    if trade_count < self.min_trades():
      return False
    if vs_hold_pct is None:
      return False
    # Fast path: losing badly — retune every N trades without waiting for timer
    if (
        trades_since_tune >= config.FAST_LEARN_EVERY_N_TRADES
        and vs_hold_pct < -0.8
    ):
      return True
    if vs_hold_pct < 0.25:
      return True
    if pnl_pct < -0.4:
      return True
    # Reinforce winners occasionally
    if vs_hold_pct > 1.0 and trades_since_tune >= 4:
      return True
    return False

  def tune(
      self,
      vs_hold_pct: float,
      trade_count: int,
      recent_trades: list[dict] | None = None,
      volatile: bool = False,
      volatility_pct: float = 0,
      pnl_pct: float = 0,
  ) -> tuple[dict, str]:
    p = copy.deepcopy(self.params)
    reason_parts = []

    deltas = analyze_trades(
        recent_trades or [],
        vs_hold_pct,
        pnl_pct,
        volatility_pct,
        volatile or self.volatile,
    )

    if deltas:
      for key, delta in deltas.items():
        if key not in p:
          continue
        old = p[key]
        if isinstance(old, int) or key in ("sma_period", "dca_interval_hours"):
          p[key] = int(old + delta)
        else:
          p[key] = float(old) + delta
        reason_parts.append(f"{key} {old}→{p[key]}")
    elif vs_hold_pct < 0:
      old_dip = p["dip_threshold_pct"]
      p["dip_threshold_pct"] = max(self.bounds["dip_threshold_pct"][0], old_dip - 0.5)
      reason_parts.append(f"DIP {old_dip}%→{p['dip_threshold_pct']}%")
      old_dca = p["dca_amount"]
      step = 4.0 if self.volatile else 6.0
      p["dca_amount"] = max(self.bounds["dca_amount"][0], old_dca - step)
      reason_parts.append(f"DCA ${old_dca}→${p['dca_amount']}")
    else:
      old_dip = p["dip_threshold_pct"]
      p["dip_threshold_pct"] = min(self.bounds["dip_threshold_pct"][1], old_dip + 0.2)
      reason_parts.append(f"DIP {old_dip}%→{p['dip_threshold_pct']}% (лидируем)")

    self.apply_params(p)
    mode = "быстрое" if trade_count < 8 else "глубокое"
    reason = (
      f"🎓 {mode.capitalize()} обучение ({trade_count} сделок, vs hold {vs_hold_pct:+.2f}%): "
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

  def apply_deltas(self, deltas: dict[str, float]) -> tuple[dict, str]:
    p = copy.deepcopy(self.params)
    parts = []
    for key, delta in deltas.items():
      if key not in p:
        continue
      old = p[key]
      if isinstance(old, int):
        p[key] = int(old + delta)
      else:
        p[key] = old + delta
      parts.append(f"{key} {old}→{p[key]}")
    self.apply_params(p)
    return self.get_params(), "микро-настройка: " + ", ".join(parts)
