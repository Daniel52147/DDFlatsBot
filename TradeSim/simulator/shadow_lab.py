"""
Shadow Lab — parallel mock clones per market for accelerated learning.

Inspired by:
- v5-crypto-scalper shadow tracking (forward-walk rejected/hypothetical paths)
- Jesse / Freqtrade hyperopt (parallel param search)
"""

from __future__ import annotations

import copy
import logging
import random
import time
from typing import Any

import config
from learning.optimizer import StrategyOptimizer
from simulator.engine import SimulatorEngine
from simulator.price_walk import prices_for_tick
from simulator.strategy import StrategyBot

logger = logging.getLogger(__name__)

# Deterministic seeds per clone index for reproducible jitter
_JITTER_PROFILES = [
    {"dca_amount": 1.0, "dip_threshold_pct": 1.0, "take_profit_pct": 1.0, "sma_period": 0},
    {"dca_amount": 0.85, "dip_threshold_pct": 1.1, "take_profit_pct": 0.9, "sma_period": -2},
    {"dca_amount": 1.15, "dip_threshold_pct": 0.9, "take_profit_pct": 1.1, "sma_period": 2},
    {"dca_amount": 0.75, "dip_threshold_pct": 1.2, "dip_extra_amount": 1.2, "sma_period": -4},
    {"dca_amount": 1.25, "dip_threshold_pct": 0.85, "dip_extra_amount": 0.8, "sma_period": 4},
    {"dca_amount": 0.9, "take_profit_pct": 0.85, "take_profit_fraction": 1.2, "stop_loss_pct": 1.1},
    {"dca_amount": 1.1, "take_profit_pct": 1.15, "take_profit_fraction": 0.85, "stop_loss_pct": 0.9},
    {"dca_amount": 0.8, "dca_interval_hours": 0.75, "dip_cooldown_minutes": 0.7},
    {"dca_amount": 1.2, "dca_interval_hours": 1.25, "dip_cooldown_minutes": 1.3},
    {"dip_threshold_pct": 1.3, "spike_threshold_pct": 0.9, "spike_extra_amount": 1.15},
    {"dip_threshold_pct": 0.8, "spike_threshold_pct": 1.1, "spike_extra_amount": 0.85},
    {"sma_period": -6, "take_profit_pct": 1.2, "stop_loss_pct": 1.15, "dca_amount": 0.95},
]


class ShadowClone:
    """Lightweight paper bot — same price feed, different params."""

    __slots__ = ("clone_id", "symbol", "label", "volatile", "engine", "bot", "optimizer", "trades")

    def __init__(
        self,
        clone_id: int,
        symbol: str,
        label: str,
        params: dict,
        volatile: bool = False,
    ):
        self.clone_id = clone_id
        self.symbol = symbol
        self.label = label
        self.volatile = volatile
        self.engine = SimulatorEngine(initial_balance=config.SHADOW_BALANCE)
        bounds = StrategyOptimizer.BOUNDS_VOLATILE if volatile else StrategyOptimizer.BOUNDS
        self.optimizer = StrategyOptimizer(params, bounds=bounds, volatile=volatile)
        self.bot = StrategyBot(self.engine, params=self.optimizer.get_params())
        self.trades = 0

    def process_price(self, price: float, sma: float | None) -> bool:
        if price <= 0:
            return False
        before = len(self.engine.trades)
        self.bot.maybe_trade(price, sma)
        if len(self.engine.trades) > before:
            self.trades = len(self.engine.trades)
            return True
        return False

    def snapshot(self, price: float) -> dict[str, Any]:
        snap = self.engine.snapshot(price)
        return {
            "id": self.clone_id,
            "vs_hold_pct": snap.get("vs_hold_pct", 0),
            "pnl_pct": snap.get("pnl_pct", 0),
            "trades": len(self.engine.trades),
            "params": self.bot.get_params(),
        }


class ShadowLab:
    """
    Runs N mock clones per market on the same live prices.
    Best performers promote params to the real bot.
    """

    def __init__(self, sessions: dict):
        self.sessions = sessions
        self.clones: dict[str, list[ShadowClone]] = {}
        self.last_eval_ts = 0.0
        self.last_promotions: list[dict[str, Any]] = []
        self.total_shadow_trades = 0
        self._init_clones()

    def _init_clones(self):
        n = config.SHADOW_CLONES_PER_MARKET
        for sym, session in self.sessions.items():
            base = copy.deepcopy(session.bot.get_params())
            volatile = session.volatile
            label = session.label
            clones: list[ShadowClone] = []
            for i in range(n):
                params = self._jitter_params(base, i, volatile)
                clones.append(ShadowClone(i, sym, label, params, volatile=volatile))
            self.clones[sym] = clones
        logger.info(
            "Shadow Lab: %d markets × %d clones = %d mock bots",
            len(self.clones), n, len(self.clones) * n,
        )

    def _jitter_params(self, base: dict, index: int, volatile: bool) -> dict:
        p = copy.deepcopy(base)
        profile = _JITTER_PROFILES[index % len(_JITTER_PROFILES)]
        bounds = StrategyOptimizer.BOUNDS_VOLATILE if volatile else StrategyOptimizer.BOUNDS
        opt = StrategyOptimizer(p, bounds=bounds, volatile=volatile)

        for key, mult in profile.items():
            if key not in p or mult == 1.0 or mult == 0:
                continue
            val = p[key]
            if key == "sma_period":
                p[key] = int(val + mult)
            elif isinstance(val, int):
                p[key] = int(val * mult) if mult > 0 else val
            else:
                p[key] = float(val * mult)

        # Extra randomness for clones beyond profile list
        if index >= len(_JITTER_PROFILES):
            rng = random.Random(index * 9973 + hash(tuple(sorted(base.items()))) % 10000)
            for key in ("dca_amount", "dip_threshold_pct", "take_profit_pct"):
                if key in p:
                    jitter = 1 + rng.uniform(-config.SHADOW_PARAM_JITTER, config.SHADOW_PARAM_JITTER)
                    p[key] = type(p[key])(p[key] * jitter)

        return opt.apply_params(p)

    def on_market_update(
        self,
        symbol: str,
        price: float,
        sma: float | None,
        closed_candle: dict | None = None,
    ) -> int:
        """Same price path as live bot — tick or OHLC on candle close."""
        if not config.SHADOW_LAB_ENABLED:
            return 0
        walk = prices_for_tick(price, closed_candle)
        new_trades = 0
        for clone in self.clones.get(symbol, []):
            for p in walk:
                if clone.process_price(p, sma):
                    new_trades += 1
        self.total_shadow_trades += new_trades
        return new_trades

    def on_tick(self, symbol: str, price: float, sma: float | None) -> int:
        return self.on_market_update(symbol, price, sma, None)

    def on_candle(self, symbol: str, candle: dict, sma: float | None) -> int:
        """Deprecated — use on_market_update with closed_candle."""
        return self.on_market_update(symbol, candle.get("close", 0), sma, candle)

    def evaluate_and_promote(self) -> list[dict[str, Any]]:
        """Pick best clone per market; merge winning params into live bot."""
        if not config.SHADOW_LAB_ENABLED:
            return []
        promotions = []
        now = time.time()

        for sym, session in self.sessions.items():
            clones = self.clones.get(sym, [])
            if not clones:
                continue
            price = session.feed.price or session.demo_price
            ranked = sorted(
                [c.snapshot(price) for c in clones],
                key=lambda x: (x["vs_hold_pct"], x["pnl_pct"]),
                reverse=True,
            )
            best = ranked[0]
            live = session.engine.snapshot(price)
            live_vs = live.get("vs_hold_pct", 0)

            if best["trades"] < config.SHADOW_MIN_TRADES_PROMOTE:
                continue
            if best["vs_hold_pct"] <= live_vs + config.SHADOW_PROMOTE_MARGIN:
                continue

            winner = clones[best["id"]]
            promoted_keys = []
            live_params = session.bot.get_params()
            winner_params = winner.bot.get_params()

            for key in ("dca_amount", "dip_threshold_pct", "dip_extra_amount",
                        "take_profit_pct", "take_profit_fraction", "sma_period",
                        "stop_loss_pct", "dip_cooldown_minutes"):
                if key not in live_params or key not in winner_params:
                    continue
                old = live_params[key]
                new = winner_params[key]
                if old != new:
                    promoted_keys.append(f"{key}:{old}→{new}")

            if not promoted_keys:
                continue

            session.set_params_bounded(winner_params)
            session.base_params = dict(session.bot.get_params())

            promo = {
                "ts": now,
                "symbol": sym,
                "label": session.label,
                "clone_id": best["id"],
                "vs_hold_pct": best["vs_hold_pct"],
                "live_vs_hold": live_vs,
                "trades": best["trades"],
                "changes": promoted_keys[:5],
                "total_clones": len(clones),
            }
            promotions.append(promo)
            logger.info(
                "[%s] Shadow promote clone #%d: vs hold %+.2f%% (live %+.2f%%) — %s",
                session.label, best["id"], best["vs_hold_pct"], live_vs,
                ", ".join(promoted_keys[:3]),
            )

        self.last_promotions = (promotions + self.last_promotions)[:20]
        self.last_eval_ts = now
        return promotions

    def reset_clones(self, symbol: str | None = None):
        targets = [symbol] if symbol else list(self.sessions.keys())
        for sym in targets:
            session = self.sessions.get(sym)
            if not session:
                continue
            base = copy.deepcopy(session.bot.get_params())
            n = config.SHADOW_CLONES_PER_MARKET
            self.clones[sym] = [
                ShadowClone(i, sym, session.label, self._jitter_params(base, i, session.volatile),
                            volatile=session.volatile)
                for i in range(n)
            ]

    def sync_markets(self, sessions: dict):
        """Add shadow clones for any new markets."""
        n = config.SHADOW_CLONES_PER_MARKET
        for sym, session in sessions.items():
            if sym in self.clones:
                continue
            base = copy.deepcopy(session.bot.get_params())
            self.clones[sym] = [
                ShadowClone(
                    i, sym, session.label,
                    self._jitter_params(base, i, session.volatile),
                    volatile=session.volatile,
                )
                for i in range(n)
            ]
            logger.info("Shadow Lab: added %d clones for %s", n, session.label)

    def status(self) -> dict[str, Any]:
        markets = []
        for sym, session in self.sessions.items():
            clones = self.clones.get(sym, [])
            price = session.feed.price or session.demo_price
            if not clones:
                continue
            snaps = [c.snapshot(price) for c in clones]
            best = max(snaps, key=lambda x: x["vs_hold_pct"])
            worst = min(snaps, key=lambda x: x["vs_hold_pct"])
            live = session.engine.snapshot(price)
            markets.append({
                "symbol": sym,
                "label": session.label,
                "clones": len(clones),
                "best_clone": best["id"],
                "best_vs_hold": best["vs_hold_pct"],
                "worst_vs_hold": worst["vs_hold_pct"],
                "live_vs_hold": live.get("vs_hold_pct", 0),
                "shadow_trades": sum(s["trades"] for s in snaps),
                "top3": sorted(snaps, key=lambda x: -x["vs_hold_pct"])[:3],
            })

        return {
            "enabled": config.SHADOW_LAB_ENABLED,
            "clones_per_market": config.SHADOW_CLONES_PER_MARKET,
            "total_clones": sum(len(v) for v in self.clones.values()),
            "total_shadow_trades": self.total_shadow_trades,
            "last_eval_ts": self.last_eval_ts,
            "promotions": self.last_promotions[:8],
            "markets": markets,
        }

    def leaderboard(self, symbol: str | None = None, limit: int = 15) -> list[dict]:
        rows = []
        symbols = [symbol] if symbol else list(self.clones.keys())
        for sym in symbols:
            session = self.sessions.get(sym)
            if not session:
                continue
            price = session.feed.price or session.demo_price
            for c in self.clones.get(sym, []):
                s = c.snapshot(price)
                rows.append({
                    "symbol": sym,
                    "label": session.label,
                    "clone_id": s["id"],
                    "vs_hold_pct": s["vs_hold_pct"],
                    "pnl_pct": s["pnl_pct"],
                    "trades": s["trades"],
                })
        rows.sort(key=lambda x: (-x["vs_hold_pct"], -x["trades"]))
        return rows[:limit]
