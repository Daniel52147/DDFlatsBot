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
        self.last_micro_take_profit_ts = 0.0
        self.last_trailing_profit_ts = 0.0
        self.last_dip_ts = 0.0
        self.last_spike_ts = 0.0
        self.last_stop_loss_ts = 0.0
        self.last_stale_loss_ts = 0.0
        self.profit_high_water = 0.0
        self.loss_since_ts = 0.0
        self.enabled = True

    def update_params(self, params: dict):
        self.params.update(params)

    def get_params(self) -> dict:
        return dict(self.params)

    def export_state(self) -> dict[str, Any]:
        return {
            "last_dca_ts": self.last_dca_ts,
            "last_take_profit_ts": self.last_take_profit_ts,
            "last_micro_take_profit_ts": self.last_micro_take_profit_ts,
            "last_trailing_profit_ts": self.last_trailing_profit_ts,
            "last_dip_ts": self.last_dip_ts,
            "last_spike_ts": self.last_spike_ts,
            "last_stop_loss_ts": self.last_stop_loss_ts,
            "last_stale_loss_ts": self.last_stale_loss_ts,
            "profit_high_water": self.profit_high_water,
            "loss_since_ts": self.loss_since_ts,
            "enabled": self.enabled,
            "strategy": {},
        }

    def import_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            return
        self.last_dca_ts = float(state.get("last_dca_ts", self.last_dca_ts))
        self.last_take_profit_ts = float(state.get("last_take_profit_ts", self.last_take_profit_ts))
        self.last_micro_take_profit_ts = float(
            state.get("last_micro_take_profit_ts", self.last_micro_take_profit_ts)
        )
        self.last_trailing_profit_ts = float(
            state.get("last_trailing_profit_ts", self.last_trailing_profit_ts)
        )
        self.last_dip_ts = float(state.get("last_dip_ts", self.last_dip_ts))
        self.last_spike_ts = float(state.get("last_spike_ts", self.last_spike_ts))
        self.last_stop_loss_ts = float(state.get("last_stop_loss_ts", self.last_stop_loss_ts))
        self.last_stale_loss_ts = float(state.get("last_stale_loss_ts", self.last_stale_loss_ts))
        self.profit_high_water = float(state.get("profit_high_water", self.profit_high_water))
        self.loss_since_ts = float(state.get("loss_since_ts", self.loss_since_ts))
        if "enabled" in state:
            self.enabled = bool(state["enabled"])

    def _cooldown_ok(self, last_ts: float, minutes: float) -> bool:
        return time.time() - last_ts >= minutes * 60

    def _cap_buy_amount(self, amount: float) -> float:
        max_pct = self.params.get("max_buy_pct_of_cash", 0.5)
        cap = self.engine.available_quote * max_pct
        return min(amount, cap) if cap > 0 else amount

    def _cost_profit_pct(self, price: float) -> float | None:
        avg = self.engine.avg_entry_price()
        if not avg or avg <= 0:
            return None
        return (price - avg) / avg * 100

    def _track_profit_peak(self, price: float, cost_profit: float | None) -> None:
        if cost_profit is not None and cost_profit > 0:
            self.profit_high_water = max(self.profit_high_water, price)
        elif self.engine.position.base <= 0:
            self.profit_high_water = 0.0

    def _track_loss_timer(self, cost_profit: float | None) -> None:
        stale_pct = self.params.get("stale_loss_pct")
        if stale_pct is None or cost_profit is None:
            self.loss_since_ts = 0.0
            return
        if cost_profit <= -stale_pct:
            if self.loss_since_ts <= 0:
                self.loss_since_ts = time.time()
        else:
            self.loss_since_ts = 0.0

    def _regime_blocks_buy(self, price: float, sma: float | None) -> bool:
        if not config.REGIME_FILTER_ENABLED:
            return False
        closes = [c.close for c in getattr(self, "_recent_candles", [])[-30:]]
        regime = detect_regime(price, sma, closes if len(closes) >= 5 else None)
        return regime_blocks_buy("dca", regime)

    def _sell_fraction(
        self,
        price: float,
        fraction: float,
        reason: str,
    ) -> Trade | None:
        amount_base = self.engine.position.base * fraction
        if amount_base * price < 3:
            return None
        return self.engine.sell(price, amount_base, reason=reason)

    def _maybe_stop_loss(self, price: float) -> Trade | None:
        sl_pct = self.params.get("stop_loss_pct")
        if not sl_pct or self.engine.position.base <= 0:
            return None
        cost_profit = self._cost_profit_pct(price)
        if cost_profit is None or cost_profit > -sl_pct:
            return None
        cooldown_h = self.params.get("stop_loss_cooldown_hours", 12)
        if time.time() - self.last_stop_loss_ts < cooldown_h * 3600:
            return None
        fraction = self.params.get("stop_loss_fraction", 0.2)
        trade = self._sell_fraction(
            price,
            fraction,
            reason=f"STOP-LOSS: {cost_profit:.1f}% от входа — сокращение риска",
        )
        if trade:
            self.last_stop_loss_ts = time.time()
        return trade

    def _maybe_stale_loss(self, price: float) -> Trade | None:
        stale_pct = self.params.get("stale_loss_pct")
        stale_hours = self.params.get("stale_loss_hours")
        if stale_pct is None or stale_hours is None or self.engine.position.base <= 0:
            return None
        cost_profit = self._cost_profit_pct(price)
        if cost_profit is None or cost_profit > -stale_pct:
            return None
        if self.loss_since_ts <= 0:
            return None
        if time.time() - self.loss_since_ts < stale_hours * 3600:
            return None
        cooldown_h = self.params.get("stop_loss_cooldown_hours", 6)
        if time.time() - self.last_stale_loss_ts < cooldown_h * 3600:
            return None
        fraction = self.params.get("stale_loss_fraction", 0.15)
        trade = self._sell_fraction(
            price,
            fraction,
            reason=f"STALE-LOSS: {cost_profit:.1f}% > {stale_hours}ч — частичный выход",
        )
        if trade:
            self.last_stale_loss_ts = time.time()
            self.loss_since_ts = 0.0
        return trade

    def _maybe_trailing_profit(self, price: float) -> Trade | None:
        trail_pct = self.params.get("trailing_profit_pct")
        min_profit = self.params.get("trailing_profit_min_pct", 2.0)
        if trail_pct is None or self.engine.position.base <= 0:
            return None
        cost_profit = self._cost_profit_pct(price)
        if cost_profit is None or cost_profit < min_profit:
            return None
        self.profit_high_water = max(self.profit_high_water, price)
        if self.profit_high_water <= 0:
            return None
        drop = (self.profit_high_water - price) / self.profit_high_water * 100
        if drop < trail_pct:
            return None
        cooldown = self.params.get("trailing_profit_cooldown_hours", 2) * 3600
        if time.time() - self.last_trailing_profit_ts < cooldown:
            return None
        fraction = self.params.get("trailing_profit_fraction", 0.18)
        trade = self._sell_fraction(
            price,
            fraction,
            reason=f"TRAIL-PROFIT: −{drop:.1f}% от пика, вход +{cost_profit:.1f}%",
        )
        if trade:
            self.last_trailing_profit_ts = time.time()
            self.profit_high_water = price
        return trade

    def _maybe_micro_take_profit(self, price: float) -> Trade | None:
        micro_pct = self.params.get("micro_take_profit_pct")
        if micro_pct is None or self.engine.position.base <= 0:
            return None
        cost_profit = self._cost_profit_pct(price)
        if cost_profit is None or cost_profit < micro_pct:
            return None
        cooldown = self.params.get("micro_take_profit_cooldown_hours", 2) * 3600
        if time.time() - self.last_micro_take_profit_ts < cooldown:
            return None
        fraction = self.params.get("micro_take_profit_fraction", 0.12)
        trade = self._sell_fraction(
            price,
            fraction,
            reason=f"MICRO-TP: +{cost_profit:.1f}% — лёгкая фиксация",
        )
        if trade:
            self.last_micro_take_profit_ts = time.time()
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

        cost_profit = self._cost_profit_pct(price)
        if cost_profit is not None:
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
        trade = self._sell_fraction(
            price,
            fraction,
            reason=f"TAKE-PROFIT: +{profit_pct:.1f}% — фиксация прибыли",
        )
        if trade:
            self.last_take_profit_ts = time.time()
        return trade

    def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
        if not self.enabled or price <= 0:
            return None

        cost_profit = self._cost_profit_pct(price)
        self._track_profit_peak(price, cost_profit)
        self._track_loss_timer(cost_profit)

        sl = self._maybe_stop_loss(price)
        if sl:
            return sl

        stale = self._maybe_stale_loss(price)
        if stale:
            return stale

        trail = self._maybe_trailing_profit(price)
        if trail:
            return trail

        micro = self._maybe_micro_take_profit(price)
        if micro:
            return micro

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
        cost_profit_pct = self._cost_profit_pct(price)
        avg_entry = self.engine.avg_entry_price()
        if sma and price:
            dip_pct = round((sma - price) / sma * 100, 2)
            if price > sma:
                profit_pct = round((price - sma) / sma * 100, 2)
        if cost_profit_pct is not None:
            cost_profit_pct = round(cost_profit_pct, 2)
        return {
            "enabled": self.enabled,
            "params": self.get_params(),
            "sma": round(sma, 2) if sma else None,
            "avg_entry": round(avg_entry, 8) if avg_entry else None,
            "dip_pct": dip_pct,
            "profit_pct": profit_pct,
            "cost_profit_pct": cost_profit_pct,
            "profit_high_water": round(self.profit_high_water, 6) if self.profit_high_water else None,
            "next_dca_in_hours": max(
                0,
                round(
                    self.params["dca_interval_hours"]
                    - (time.time() - self.last_dca_ts) / 3600,
                    1,
                ),
            ),
        }
