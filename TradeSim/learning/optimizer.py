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

  # Paper learn — allow sub-4h DCA and short cooldowns for more round-trips.
  BOUNDS_PAPER_OVERRIDES = {
    "dca_interval_hours": (0.5, 48),
    "dip_cooldown_minutes": (1, 120),
    "spike_cooldown_minutes": (2, 180),
    "take_profit_cooldown_hours": (0.25, 12),
    "stop_loss_cooldown_hours": (0.25, 12),
  }

  BOUNDS_PAPER_VOLATILE_OVERRIDES = {
    "dca_interval_hours": (0.5, 24),
    "dip_cooldown_minutes": (1, 60),
    "spike_cooldown_minutes": (2, 90),
    "take_profit_cooldown_hours": (0.25, 6),
    "stop_loss_cooldown_hours": (0.25, 6),
  }

  BOUNDS_EXTENDED = {
    "grid_spacing_pct": (0.5, 5.0),
    "grid_cooldown_minutes": (0.0, 30.0),
    "grid_buy_amount": (5.0, 80.0),
    "grid_sell_fraction": (0.05, 0.5),
    "scalp_cooldown_seconds": (1, 120),
    "scalp_move_pct": (0.1, 3.0),
    "scalp_tp_pct": (0.1, 2.0),
    "scalp_buy_amount": (5.0, 60.0),
    "breakout_pct": (0.3, 5.0),
    "trailing_stop_pct": (1.0, 12.0),
    "momentum_buy_amount": (5.0, 80.0),
    "entry_cooldown_minutes": (0.0, 30.0),
    "rsi_oversold": (20, 45),
    "rsi_overbought": (55, 80),
    "rsi_buy_amount": (5.0, 60.0),
    "rsi_buy_cooldown_minutes": (0.0, 30.0),
    "rsi_sell_cooldown_minutes": (0.0, 30.0),
    "stop_loss_cooldown_hours": (0.25, 12.0),
  }

  @classmethod
  def bounds_for_paper_learn(cls, volatile: bool = False) -> dict:
    base = cls.BOUNDS_VOLATILE if volatile else cls.BOUNDS
    overrides = cls.BOUNDS_PAPER_VOLATILE_OVERRIDES if volatile else cls.BOUNDS_PAPER_OVERRIDES
    return {**base, **overrides}

  def __init__(self, params: dict | None = None, bounds: dict | None = None, volatile: bool = False):
    self.params = copy.deepcopy(params or config.STRATEGY)
    self.bounds = bounds or self.BOUNDS
    self.volatile = volatile

  def get_params(self) -> dict:
    return copy.deepcopy(self.params)

  def tune_interval_sec(self) -> int:
    return config.LEARNING_CHECK_VOLATILE_SEC if self.volatile else config.LEARNING_CHECK_SEC

  def min_trades(self) -> int:
    from learning.paper_learn_mode import effective_min_trades_for_tuning
    return effective_min_trades_for_tuning(self.volatile)

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
    from learning.paper_learn_mode import effective_fast_learn_every_n
    fast_every_n = effective_fast_learn_every_n()
    if (
        trades_since_tune >= fast_every_n
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
      from learning.paper_learn_mode import is_paper_learn_mode
      paper_float_dca = is_paper_learn_mode() or isinstance(
          self.params.get("dca_interval_hours"), float,
      )
      for key, delta in deltas.items():
        if key not in p:
          continue
        old = p[key]
        if key == "dca_interval_hours" and paper_float_dca:
          p[key] = float(old) + float(delta)
        elif isinstance(old, int) or key in ("sma_period",):
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
    from learning.paper_learn_mode import is_paper_learn_mode
    for k, v in params.items():
      if k not in self.params:
        continue
      bounds = self.bounds
      if k in self.BOUNDS_EXTENDED:
        lo, hi = self.BOUNDS_EXTENDED[k]
      else:
        lo, hi = bounds.get(k, (v, v))
      if k == "dca_interval_hours" and (is_paper_learn_mode() or isinstance(v, float)):
        self.params[k] = max(lo, min(hi, float(v)))
      elif isinstance(v, int) or (isinstance(self.params.get(k), int) and k != "dca_interval_hours"):
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
