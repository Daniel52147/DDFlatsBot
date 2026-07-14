"""Strategy factory — DCA, Grid, Momentum, RSI."""

from __future__ import annotations

import time
from typing import Any

import config
from learning.regime import detect_regime, regime_blocks_buy
from simulator.engine import SimulatorEngine, Trade
from simulator.strategy import StrategyBot as DCAStrategyBot


STRATEGY_META: dict[str, dict[str, str]] = {
    "dca": {
        "name": "DCA + DIP + SPIKE",
        "emoji": "📊",
        "desc": "Классика: плановые покупки, просадки ниже SMA, фиксация прибыли",
    },
    "grid": {
        "name": "Сетка (Grid)",
        "emoji": "🔲",
        "desc": "Покупки на уровнях сетки ниже SMA, продажи на отскоках",
    },
    "momentum": {
        "name": "Моментум",
        "emoji": "🚀",
        "desc": "Вход на пробой SMA, trailing stop на тренде",
    },
    "rsi": {
        "name": "RSI Mean-Reversion",
        "emoji": "📉",
        "desc": "Покупка при RSI < 30, частичная продажа при RSI > 70",
    },
    "scalper": {
        "name": "Скальпер",
        "emoji": "⚡",
        "desc": "Быстрые сделки на микро-движениях 0.4–0.8%, tight TP",
    },
}


def default_params(strategy_type: str) -> dict:
    mapping = {
        "dca": config.STRATEGY,
        "grid": config.GRID_STRATEGY,
        "momentum": config.MOMENTUM_STRATEGY,
        "rsi": config.RSI_STRATEGY,
        "scalper": config.SCALPER_STRATEGY,
    }
    return dict(mapping.get(strategy_type, config.STRATEGY))


SELL_PARAM_KEYS = (
    "take_profit_pct",
    "take_profit_cost_pct",
    "take_profit_fraction",
    "take_profit_cooldown_hours",
    "micro_take_profit_pct",
    "micro_take_profit_fraction",
    "micro_take_profit_cooldown_hours",
    "trailing_profit_pct",
    "trailing_profit_min_pct",
    "trailing_profit_fraction",
    "trailing_profit_cooldown_hours",
    "stop_loss_pct",
    "stop_loss_fraction",
    "stop_loss_cooldown_hours",
    "stale_loss_pct",
    "stale_loss_hours",
    "stale_loss_fraction",
)


def merge_sell_params(strategy_type: str, params: dict) -> dict:
    """Apply latest sell/trailing defaults without wiping user DCA tuning."""
    fresh = default_params(strategy_type)
    out = dict(params)
    for key in SELL_PARAM_KEYS:
        if key in fresh:
            out[key] = fresh[key]
    return out


def create_bot(
    engine: SimulatorEngine,
    strategy_type: str = "dca",
    params: dict | None = None,
):
    base = default_params(strategy_type)
    if params:
        base = {**base, **params}
    base = merge_sell_params(strategy_type, base)
    cls = {
        "dca": DCAStrategyBot,
        "grid": GridStrategyBot,
        "momentum": MomentumStrategyBot,
        "rsi": RSIStrategyBot,
        "scalper": ScalperStrategyBot,
    }.get(strategy_type, DCAStrategyBot)
    return cls(engine, params=base)


class _StrategyMixin:
    """Shared helpers for alternate strategies."""

    engine: SimulatorEngine
    params: dict
    enabled: bool = True
    last_dca_ts: float = 0.0
    last_take_profit_ts: float = 0.0
    last_dip_ts: float = 0.0
    last_spike_ts: float = 0.0
    last_stop_loss_ts: float = 0.0

    def update_params(self, params: dict):
        self.params.update(params)

    def get_params(self) -> dict:
        return dict(self.params)

    def _cooldown_ok(self, last_ts: float, minutes: float) -> bool:
        return time.time() - last_ts >= minutes * 60

    def _cap_buy_amount(self, amount: float) -> float:
        max_pct = self.params.get("max_buy_pct_of_cash", 0.5)
        cap = self.engine.available_quote * max_pct
        return min(amount, cap) if cap > 0 else amount

    def _regime_blocks_buy(self, price: float, sma: float | None) -> bool:
        if not config.REGIME_FILTER_ENABLED:
            return False
        closes = getattr(self, "_prices", None)
        regime = detect_regime(price, sma, closes if isinstance(closes, list) else None)
        return regime_blocks_buy(getattr(self, "strategy_type", "dca"), regime)

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
            reason=f"STOP-LOSS: −{loss_pct:.1f}% — сокращение риска",
        )
        if trade:
            self.last_stop_loss_ts = time.time()
        return trade

    def _maybe_scheduled_dca(self, price: float) -> Trade | None:
        now = time.time()
        interval = self.params.get("dca_interval_hours", 24) * 3600
        from simulator.risk_gate import brain_reduce_aggression
        if brain_reduce_aggression():
            interval *= 2
        if now - self.last_dca_ts < interval:
            return None
        amt = self._cap_buy_amount(self.params.get("dca_amount", 20))
        trade = self.engine.buy(price, amt, reason="DCA: плановая покупка")
        if trade:
            self.last_dca_ts = now
        return trade

    def export_state(self) -> dict[str, Any]:
        return {
            "last_dca_ts": self.last_dca_ts,
            "last_take_profit_ts": self.last_take_profit_ts,
            "last_dip_ts": self.last_dip_ts,
            "last_spike_ts": self.last_spike_ts,
            "last_stop_loss_ts": self.last_stop_loss_ts,
            "enabled": self.enabled,
            "strategy": self._export_strategy_state(),
        }

    def _export_strategy_state(self) -> dict[str, Any]:
        return {}

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
        self._import_strategy_state(state.get("strategy") or {})

    def _import_strategy_state(self, data: dict[str, Any]) -> None:
        pass

    def _status_common(self, price: float, sma: float | None, extra: dict | None = None) -> dict[str, Any]:
        dip_pct = None
        if sma and price:
            dip_pct = round((sma - price) / sma * 100, 2)
        out = {
            "enabled": self.enabled,
            "params": self.get_params(),
            "strategy_type": getattr(self, "strategy_type", "dca"),
            "sma": round(sma, 2) if sma else None,
            "avg_entry": round(self.engine.avg_entry_price(), 8) if self.engine.avg_entry_price() else None,
            "dip_pct": dip_pct,
            "next_dca_in_hours": max(
                0,
                round(
                    self.params.get("dca_interval_hours", 24)
                    - (time.time() - self.last_dca_ts) / 3600,
                    1,
                ),
            ),
        }
        if extra:
            out.update(extra)
        return out


class GridStrategyBot(_StrategyMixin):
    strategy_type = "grid"

    def __init__(self, engine: SimulatorEngine, params: dict | None = None):
        self.engine = engine
        self.params = dict(config.GRID_STRATEGY)
        if params:
            self.params.update(params)
        self._last_buy_level = -1
        self._last_sell_level = -1

    def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
        if not self.enabled or price <= 0:
            return None
        sl = self._maybe_stop_loss(price)
        if sl:
            return sl
        spacing = self.params.get("grid_spacing_pct", 2.5)
        if sma and sma > 0:
            dip_pct = (sma - price) / sma * 100
            rise_pct = (price - sma) / sma * 100
            buy_level = int(dip_pct // spacing)
            sell_level = int(rise_pct // spacing)
            cd = self.params.get("grid_cooldown_minutes", 12)
            if buy_level > self._last_buy_level and dip_pct >= spacing:
                if self._cooldown_ok(self.last_dip_ts, cd) and not self._regime_blocks_buy(price, sma):
                    amt = self._cap_buy_amount(self.params.get("grid_buy_amount", 22))
                    trade = self.engine.buy(
                        price, amt,
                        reason=f"GRID L{buy_level}: −{dip_pct:.1f}% от SMA — уровень сетки",
                    )
                    if trade:
                        self._last_buy_level = buy_level
                        self.last_dip_ts = time.time()
                        return trade
            if sell_level > self._last_sell_level and rise_pct >= spacing and self.engine.position.base > 0:
                if self._cooldown_ok(self.last_take_profit_ts, cd):
                    fraction = self.params.get("grid_sell_fraction", 0.18)
                    amount_base = self.engine.position.base * fraction
                    if amount_base * price >= 3:
                        trade = self.engine.sell(
                            price, amount_base,
                            reason=f"GRID S{sell_level}: +{rise_pct:.1f}% — фиксация уровня",
                        )
                        if trade:
                            self._last_sell_level = sell_level
                            self.last_take_profit_ts = time.time()
                            return trade
        return self._maybe_scheduled_dca(price)

    def _export_strategy_state(self) -> dict[str, Any]:
        return {
            "last_buy_level": self._last_buy_level,
            "last_sell_level": self._last_sell_level,
        }

    def _import_strategy_state(self, data: dict[str, Any]) -> None:
        self._last_buy_level = int(data.get("last_buy_level", self._last_buy_level))
        self._last_sell_level = int(data.get("last_sell_level", self._last_sell_level))

    def status(self, price: float, sma: float | None) -> dict[str, Any]:
        return self._status_common(price, sma, {
            "grid_levels_buy": self._last_buy_level,
            "grid_levels_sell": self._last_sell_level,
        })


class MomentumStrategyBot(_StrategyMixin):
    strategy_type = "momentum"

    def __init__(self, engine: SimulatorEngine, params: dict | None = None):
        self.engine = engine
        self.params = dict(config.MOMENTUM_STRATEGY)
        if params:
            self.params.update(params)
        self.high_water = 0.0
        self.in_trend = False

    def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
        if not self.enabled or price <= 0:
            return None
        sl = self._maybe_stop_loss(price)
        if sl:
            self.in_trend = False
            self.high_water = 0.0
            return sl
        breakout = self.params.get("breakout_pct", 1.8)
        trail = self.params.get("trailing_stop_pct", 4.5)
        if sma and sma > 0:
            above_pct = (price - sma) / sma * 100
            if above_pct >= breakout and not self.in_trend:
                if self._cooldown_ok(self.last_spike_ts, self.params.get("entry_cooldown_minutes", 20)):
                    amt = self._cap_buy_amount(self.params.get("momentum_buy_amount", 35))
                    trade = self.engine.buy(
                        price, amt,
                        reason=f"MOMENTUM: пробой SMA +{above_pct:.1f}% — вход в тренд",
                    )
                    if trade:
                        self.in_trend = True
                        self.high_water = price
                        self.last_spike_ts = time.time()
                        return trade
            if self.in_trend and self.engine.position.base > 0:
                self.high_water = max(self.high_water, price)
                drop = (self.high_water - price) / self.high_water * 100 if self.high_water else 0
                if drop >= trail:
                    fraction = self.params.get("trail_sell_fraction", 0.35)
                    amount_base = self.engine.position.base * fraction
                    if amount_base * price >= 3:
                        trade = self.engine.sell(
                            price, amount_base,
                            reason=f"TRAIL: −{drop:.1f}% от пика ${self.high_water:.2f}",
                        )
                        if trade:
                            self.in_trend = False
                            self.high_water = 0.0
                            self.last_take_profit_ts = time.time()
                            return trade
        return self._maybe_scheduled_dca(price)

    def _export_strategy_state(self) -> dict[str, Any]:
        return {"high_water": self.high_water, "in_trend": self.in_trend}

    def _import_strategy_state(self, data: dict[str, Any]) -> None:
        self.high_water = float(data.get("high_water", self.high_water))
        self.in_trend = bool(data.get("in_trend", self.in_trend))

    def status(self, price: float, sma: float | None) -> dict[str, Any]:
        return self._status_common(price, sma, {
            "in_trend": self.in_trend,
            "high_water": round(self.high_water, 4) if self.high_water else None,
        })


class RSIStrategyBot(_StrategyMixin):
    strategy_type = "rsi"

    def __init__(self, engine: SimulatorEngine, params: dict | None = None):
        self.engine = engine
        self.params = dict(config.RSI_STRATEGY)
        if params:
            self.params.update(params)
        self._prices: list[float] = []

    def on_candle_close(self, close: float) -> None:
        if close <= 0:
            return
        self._prices.append(close)
        if len(self._prices) > 80:
            self._prices = self._prices[-80:]

    def _rsi(self) -> float | None:
        period = int(self.params.get("rsi_period", 14))
        if len(self._prices) < period + 1:
            return None
        gains, losses = [], []
        for i in range(-period, 0):
            diff = self._prices[i] - self._prices[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
        if not self.enabled or price <= 0:
            return None
        sl = self._maybe_stop_loss(price)
        if sl:
            return sl
        rsi = self._rsi()
        oversold = self.params.get("rsi_oversold", 30)
        overbought = self.params.get("rsi_overbought", 70)
        if rsi is not None:
            if (
                rsi <= oversold
                and self._cooldown_ok(self.last_dip_ts, self.params.get("rsi_buy_cooldown_minutes", 15))
                and not self._regime_blocks_buy(price, sma)
            ):
                amt = self._cap_buy_amount(self.params.get("rsi_buy_amount", 28))
                trade = self.engine.buy(price, amt, reason=f"RSI {rsi:.0f}: перепроданность — отскок")
                if trade:
                    self.last_dip_ts = time.time()
                    return trade
            if rsi >= overbought and self.engine.position.base > 0:
                if self._cooldown_ok(self.last_take_profit_ts, self.params.get("rsi_sell_cooldown_minutes", 20)):
                    fraction = self.params.get("rsi_sell_fraction", 0.22)
                    amount_base = self.engine.position.base * fraction
                    if amount_base * price >= 3:
                        trade = self.engine.sell(
                            price, amount_base,
                            reason=f"RSI {rsi:.0f}: перекупленность — фиксация",
                        )
                        if trade:
                            self.last_take_profit_ts = time.time()
                            return trade
        return self._maybe_scheduled_dca(price)

    def _export_strategy_state(self) -> dict[str, Any]:
        return {"prices": list(self._prices[-80:])}

    def _import_strategy_state(self, data: dict[str, Any]) -> None:
        prices = data.get("prices")
        if isinstance(prices, list):
            self._prices = [float(p) for p in prices[-80:]]

    def status(self, price: float, sma: float | None) -> dict[str, Any]:
        rsi = self._rsi()
        return self._status_common(price, sma, {"rsi": round(rsi, 1) if rsi else None})


class ScalperStrategyBot(_StrategyMixin):
    strategy_type = "scalper"

    def __init__(self, engine: SimulatorEngine, params: dict | None = None):
        self.engine = engine
        self.params = dict(config.SCALPER_STRATEGY)
        if params:
            self.params.update(params)
        self._last_price = 0.0
        self._ticks = 0
        self._scalp_entry = 0.0

    def _min_scalp_tp_pct(self) -> float:
        """Round-trip fees + slippage — scalps below this are negative EV."""
        floor = (config.FEE_RATE + config.SLIPPAGE_RATE) * 2 * 100 + 0.15
        return max(self.params.get("scalp_tp_pct", 0.45), floor)

    def maybe_trade(self, price: float, sma: float | None) -> Trade | None:
        if not self.enabled or price <= 0:
            return None
        self._ticks += 1
        sl = self._maybe_stop_loss(price)
        if sl:
            self._scalp_entry = 0.0
            return sl
        micro_pct = self.params.get("scalp_move_pct", 0.55)
        tp_micro = self._min_scalp_tp_pct()
        cd = self.params.get("scalp_cooldown_seconds", 90)
        if self._last_price > 0:
            move = (price - self._last_price) / self._last_price * 100
            if move <= -micro_pct and self._cooldown_ok(self.last_dip_ts, cd / 60):
                amt = self._cap_buy_amount(self.params.get("scalp_buy_amount", 18))
                trade = self.engine.buy(price, amt, reason=f"SCALP: dip {move:.2f}% — быстрый вход")
                if trade:
                    self.last_dip_ts = time.time()
                    self._scalp_entry = price
                    self._last_price = price
                    return trade
            if self._scalp_entry > 0 and self.engine.position.base > 0:
                pnl_pct = (price - self._scalp_entry) / self._scalp_entry * 100
                if pnl_pct >= tp_micro and self._cooldown_ok(self.last_take_profit_ts, cd / 60):
                    fraction = self.params.get("scalp_sell_fraction", 0.25)
                    amount_base = self.engine.position.base * fraction
                    if amount_base * price >= 3:
                        trade = self.engine.sell(
                            price, amount_base,
                            reason=f"SCALP TP: +{pnl_pct:.2f}% от входа — фиксация",
                        )
                        if trade:
                            self.last_take_profit_ts = time.time()
                            self._scalp_entry = 0.0
                            self._last_price = price
                            return trade
        self._last_price = price
        if self._ticks % 40 == 0:
            return self._maybe_scheduled_dca(price)
        return None

    def _export_strategy_state(self) -> dict[str, Any]:
        return {"last_price": self._last_price, "ticks": self._ticks, "scalp_entry": self._scalp_entry}

    def _import_strategy_state(self, data: dict[str, Any]) -> None:
        self._last_price = float(data.get("last_price", self._last_price))
        self._ticks = int(data.get("ticks", self._ticks))
        self._scalp_entry = float(data.get("scalp_entry", self._scalp_entry))

    def status(self, price: float, sma: float | None) -> dict[str, Any]:
        move = None
        entry_pnl = None
        if self._last_price and price:
            move = round((price - self._last_price) / self._last_price * 100, 3)
        if self._scalp_entry > 0 and price:
            entry_pnl = round((price - self._scalp_entry) / self._scalp_entry * 100, 3)
        return self._status_common(price, sma, {
            "micro_move_pct": move,
            "scalp_entry_pnl_pct": entry_pnl,
            "min_tp_pct": round(self._min_scalp_tp_pct(), 2),
            "ticks": self._ticks,
        })
