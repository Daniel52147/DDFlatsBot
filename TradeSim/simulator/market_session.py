"""One paper-trading market: feed, candles, bot, portfolio."""

from __future__ import annotations

import logging
import time
from typing import Any

import config
from learning.optimizer import StrategyOptimizer
from simulator.candles import CandleBuilder
from simulator.engine import SimulatorEngine
from simulator.feed import PriceFeed
from simulator.strategy import StrategyBot

logger = logging.getLogger(__name__)


class MarketSession:
    def __init__(self, market: dict[str, Any]):
        self.symbol = market["symbol"]
        self.label = market["label"]
        self.name = market["name"]
        self.demo_price = market["demo_price"]
        self.volatile = market.get("volatile", False)
        self.feed = PriceFeed(self.symbol)
        self.candles = CandleBuilder(interval=config.CANDLE_INTERVAL, max_candles=config.MAX_CANDLES)
        self.engine = SimulatorEngine(initial_balance=config.BALANCE_PER_MARKET)
        self.bot = StrategyBot(self.engine, params=market.get("strategy"))
        bounds = StrategyOptimizer.BOUNDS_VOLATILE if self.volatile else StrategyOptimizer.BOUNDS
        self.optimizer = StrategyOptimizer(self.bot.get_params(), bounds=bounds)
        self.last_tune_ts = 0.0
        self.last_snapshot_ts = 0.0

    async def startup(self):
        try:
            history = await self.feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=100)
        except Exception as e:
            logger.error("[%s] klines failed: %s", self.symbol, e)
            try:
                price = await self.feed.fetch_price()
            except Exception:
                price = self.demo_price
                self.feed.price = price
                self.feed.last_update = time.time()
                self.feed.source = "demo-fallback"
            history = self.feed._synthetic_candles(price, 100)
        self.candles.load_history(history)
        if history:
            self.feed.price = history[-1]["close"]
            self.feed.last_update = time.time()

        # Первая покупка сразу при старте — чтобы было видно, что бот живой
        price = self.feed.price
        if price > 0:
            sma = self.candles.sma(int(self.bot.params["sma_period"]))
            trade = self.bot.maybe_trade(price, sma)
            if trade:
                logger.info("[%s] стартовая сделка: %s", self.symbol, trade.reason)

    async def on_tick(self, price: float, ts: float) -> list[dict[str, Any]]:
        """Process tick; return list of WS messages to broadcast."""
        msgs: list[dict[str, Any]] = []
        closed = self.candles.add_tick(price, ts)
        sma_period = int(self.bot.params.get("sma_period", 20))
        sma = self.candles.sma(sma_period)

        trade = self.bot.maybe_trade(price, sma)
        if trade:
            msgs.append({
                "type": "trade",
                "symbol": self.symbol,
                "trade": {
                    "side": trade.side,
                    "price": trade.price,
                    "amount_quote": trade.amount_quote,
                    "reason": trade.reason,
                    "ts": trade.ts,
                },
            })

        if closed:
            msgs.append({"type": "candle", "symbol": self.symbol, "candle": closed.to_dict()})

        snap = self.engine.snapshot(price)
        msgs.append({
            "type": "tick",
            "symbol": self.symbol,
            "price": price,
            "portfolio": snap,
            "sma": sma,
            "candle": self.candles.current_candle(),
            "source": self.feed.source,
            "strategy": self.bot.status(price, sma),
        })

        now = time.time()
        if now - self.last_snapshot_ts >= 300:
            self.last_snapshot_ts = now

        if self.optimizer.should_tune(snap["trade_count"], snap.get("vs_hold_pct")):
            if now - self.last_tune_ts > config.LEARNING_CHECK_HOURS * 3600:
                new_params, reason = self.optimizer.tune(snap["vs_hold_pct"], snap["trade_count"])
                self.bot.update_params(new_params)
                self.last_tune_ts = now
                msgs.append({
                    "type": "strategy_update",
                    "symbol": self.symbol,
                    "params": new_params,
                    "reason": reason,
                })
        return msgs

    def status_payload(self) -> dict[str, Any]:
        price = self.feed.price
        sma = self.candles.sma(int(self.bot.params["sma_period"]))
        return {
            "symbol": self.symbol,
            "label": self.label,
            "name": self.name,
            "volatile": self.volatile,
            "price": price,
            "portfolio": self.engine.snapshot(price),
            "strategy": self.bot.status(price, sma),
            "candles": self.candles.all_candles()[-100:],
            "trades": [
                {
                    "side": t.side,
                    "price": t.price,
                    "amount_quote": t.amount_quote,
                    "reason": t.reason,
                    "ts": t.ts,
                }
                for t in self.engine.trades[-15:]
            ],
        }

    def context_for_assistant(self) -> dict[str, Any]:
        price = self.feed.price
        sma = self.candles.sma(int(self.bot.params["sma_period"]))
        candles = self.candles.last_n(20)
        volatility = self._volatility_pct(candles)
        recent = [
            {
                "side": t.side,
                "price": t.price,
                "amount_quote": t.amount_quote,
                "reason": t.reason,
                "ts": t.ts,
            }
            for t in self.engine.trades[-3:]
        ]
        return {
            "symbol": self.symbol,
            "label": self.label,
            "name": self.name,
            "price": price,
            "sma": sma,
            "volatile": self.volatile,
            "volatility_pct": volatility,
            "portfolio": self.engine.snapshot(price),
            "strategy": self.bot.status(price, sma),
            "candles": candles,
            "trade_count": len(self.engine.trades),
            "recent_trades": recent,
            "feed_source": self.feed.source,
        }

    @staticmethod
    def _volatility_pct(candles: list) -> float:
        if len(candles) < 5:
            return 0.0
        closes = [c.close for c in candles]
        avg = sum(closes) / len(closes)
        if avg <= 0:
            return 0.0
        hi = max(c.high for c in candles)
        lo = min(c.low for c in candles)
        return round((hi - lo) / avg * 100, 2)
