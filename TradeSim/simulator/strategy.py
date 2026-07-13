"""DCA + dip-buy + take-profit + stop-loss strategy."""

from __future__ import annotations

import time
from typing import Any

import config
from learning.regime import detect_regime, regime_blocks_buy
from simulator.engine import SimulatorEngine, Trade


class StrategyBot:
    def __init__(self, engine: SimulatorEngine, params: dict | None = None):
        self.engine = engine
        self.params = dict(config.STRATEGY)
        if params:
            self.params.update(params)
        self.last_dca_ts = 0.0
        self.last_take_profit_ts = 0.0
        self.last_dip_ts = 0.0
        self.last_spike_ts = 0.0
        self.last_stop_loss_ts = 0.0
        self.enabled = True

    def update_params(self, params: dict):
        self.params.update(params)

    def get_params(self) -> dict:
        return dict(self.params)

    def export_state(self) -> dict[str, Any]:
        return {
            "last_dca_ts": self.last_dca_ts,
            "last_take_profit_ts": self.last_take_profit_ts,
            "last_dip_ts": self.last_dip_ts,
            "last_spike_ts": self.last_spike_ts,
            "last_stop_loss_ts": self.last_stop_loss_ts,
            "enabled": self.enabled,
            "strategy": {},
        }

    def import_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            return
        self.last_dca_ts = float(state.get("last_dca_ts", self.last_dca_ts))
        self.last_take_profit_ts = float(state.get("last_take_profit_ts", self.last_take_profit_ts))
        self.last_dip_ts = float(state.get("last_dip_ts", self.last_dip_ts))
        self.last_spike_ts = float(state.get("last_spike_ts", self.last_spike_ts))
        self.last_stop_loss_ts = float(state.get("last_stop_loss_ts", self.last_stop_loss_ts))
        if "enabled" in state:
            self.enabled = bool(state["enabled"])

    def _cooldown_ok(self, last_ts: float, minutes: float) -> bool:
        return time.time() - last_ts >= minutes * 60

    def _cap_buy_amount(self, amount: float) -> float:
        max_pct = self.params.get("max_buy_pct_of_cash", 0.5)
        cap = self.engine.available_quote * max_pct
        return min(amount, cap) if cap > 0 else amount

    def _regime_blocks_buy(self, price: float, sma: float | None) -> bool:
        if not config.REGIME_FILTER_ENABLED:
            return False
        closes = [c.close for c in getattr(self, "_recent_candles", [])[-30:]]
        regime = detect_regime(price, sma, closes if len(closes) >= 5 else None)
        return regime_blocks_buy("dca", regime)

    def _maybe_stop_loss(self, price: float) -> Trade | None:
        sl_pct = self.params.get("stop_loss_pct")
        if not sl_pct or self.engine.position.base <= 0:
            return None
        avg = self.engine.avg_entry_price()
        if not avg or avg <= 0:
            return None
        loss_pct = (avg - price) / avg * 100
        if loss_pct < sl_pct:
            return None
        cooldown_h = self.params.get("stop_loss_cooldown_hours", 12)
        if time.time() - self.last_stop_loss_ts < cooldown_h * 3600:
            return None
        fraction = self.params.get("stop_loss_fraction", 0.2)
        amount_base = self.engine.position.base * fraction
        if amount_base * price < 3:
            return None
        trade = self.engine.sell(
            price, amount_base,
            reason=f"STOP-LOSS: −{loss_pct:.1f}% от средней входа — сокращение риска",
        )
        if trade:
            self.last_stop_loss_ts = time.time()
        return trade

    def _maybe_take_profit(self, price: float, sma: float | None) -> Trade | None:
        tp_pct = self.params.get("take_profit_pct")
        if not tp_pct or self.engine.position.base <= 0:
            return None

        triggers: list[tuple[str, float]] = []
        if sma and sma > 0 and price > sma:
            sma_profit = (price - sma) / sma * 100
            if sma_profit >= tp_pct:
                triggers.append(("SMA", sma_profit))

        avg = self.engine.avg_entry_price()
        if avg and avg > 0:
            cost_profit = (price - avg) / avg * 100
            cost_thresh = self.params.get("take_profit_cost_pct", tp_pct * 0.85)
            if cost_profit >= cost_thresh:
                triggers.append(("cost", cost_profit))

        if not triggers:
            return None

        cooldown = self.params.get("take_profit_cooldown_hours", 6) * 3600
        if time.time() - self.last_take_profit_ts < cooldown:
            return None

        _, profit_pct = max(triggers, key=lambda x: x[1])
        fraction = self.params.get("take_profit_fraction", 0.15)
        amount_base = self.engine.position.base * fraction
        if amount_base * price < 3:
            return None
        trade = self.engine.sell(
            price, amount_base,
            reason=f"TAKE-PROFIT: +{profit_pct:.1f}% — фиксация прибыли",
        )
        if trade:
            self.last_take_profit_ts = time.time()
        return trade

    def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
        if not self.enabled or price <= 0:
            return None

        sl = self._maybe_stop_loss(price)
        if sl:
            return sl

        if sma and price > sma:
            tp = self._maybe_take_profit(price, sma)
            if tp:
                return tp
        elif self.engine.avg_entry_price():
            tp = self._maybe_take_profit(price, sma)
            if tp:
                return tp

        now = time.time()
        interval = self.params["dca_interval_hours"] * 3600
        from simulator.risk_gate import brain_reduce_aggression
        if brain_reduce_aggression():
            interval *= 2

        if now - self.last_dca_ts >= interval:
            if not self._regime_blocks_buy(price, sma):
                amt = self._cap_buy_amount(self.params["dca_amount"])
                trade = self.engine.buy(price, amt, reason="DCA: плановая покупка")
                if trade:
                    self.last_dca_ts = now
                    return trade

        if not sma or price >= sma:
            return None

        if self._regime_blocks_buy(price, sma):
            return None

        dip_pct = (sma - price) / sma * 100
        spike_thr = self.params.get("spike_threshold_pct")
        dip_cd = self.params.get("dip_cooldown_minutes", 30)
        spike_cd = self.params.get("spike_cooldown_minutes", 60)

        if spike_thr and dip_pct >= spike_thr:
            if self._cooldown_ok(self.last_spike_ts, spike_cd):
                amt = self._cap_buy_amount(
                    self.params.get("spike_extra_amount", self.params["dip_extra_amount"])
                )
                trade = self.engine.buy(
                    price, amt,
                    reason=f"SPIKE: резкая просадка {dip_pct:.1f}% — шанс на отскок",
                )
                if trade:
                    self.last_spike_ts = time.time()
                    return trade

        if dip_pct >= self.params["dip_threshold_pct"]:
            if self._cooldown_ok(self.last_dip_ts, dip_cd):
                amt = self._cap_buy_amount(self.params["dip_extra_amount"])
                trade = self.engine.buy(
                    price, amt,
                    reason=f"DIP: цена ниже SMA на {dip_pct:.1f}%",
                )
                if trade:
                    self.last_dip_ts = time.time()
                    return trade

        return None

    def status(self, price: float, sma: float | None) -> dict[str, Any]:
        dip_pct = None
        profit_pct = None
        cost_profit_pct = None
        avg_entry = self.engine.avg_entry_price()
        if sma and price:
            dip_pct = round((sma - price) / sma * 100, 2)
            if price > sma:
                profit_pct = round((price - sma) / sma * 100, 2)
        if avg_entry and price:
            cost_profit_pct = round((price - avg_entry) / avg_entry * 100, 2)
        return {
            "enabled": self.enabled,
            "params": self.get_params(),
            "sma": round(sma, 2) if sma else None,
            "avg_entry": round(avg_entry, 8) if avg_entry else None,
            "dip_pct": dip_pct,
            "profit_pct": profit_pct,
            "cost_profit_pct": cost_profit_pct,
            "next_dca_in_hours": max(
                0,
                round(
                    self.params["dca_interval_hours"]
                    - (time.time() - self.last_dca_ts) / 3600,
                    1,
                ),
            ),
        }
