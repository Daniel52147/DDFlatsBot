"""One paper-trading market: feed, candles, bot, portfolio."""

from __future__ import annotations

import copy
import logging
import time
from typing import Any

import config
from learning.logger import LearningLogger
from learning.optimizer import StrategyOptimizer
from simulator.candles import CandleBuilder
from simulator.engine import SimulatorEngine, Trade, Trade
from simulator.feed import PriceFeed
from simulator.price_walk import prices_for_tick, run_strategy_prices
from simulator.strategy import StrategyBot

logger = logging.getLogger(__name__)


class MarketSession:
    def __init__(self, market: dict[str, Any]):
        self.symbol = market["symbol"]
        self.label = market["label"]
        self.name = market["name"]
        self.demo_price = market["demo_price"]
        self.volatile = market.get("volatile", False)
        self.growth = market.get("growth", False)
        self.viral = market.get("viral", False)
        self.tier = market.get("tier", "major")
        self.feed = PriceFeed(self.symbol)
        self.candles = CandleBuilder(interval=config.CANDLE_INTERVAL, max_candles=config.MAX_CANDLES)
        self.engine = SimulatorEngine(initial_balance=config.BALANCE_PER_MARKET)
        self.bot = StrategyBot(self.engine, params=market.get("strategy"))
        self.base_params = copy.deepcopy(self.bot.get_params())
        bounds = (
            StrategyOptimizer.BOUNDS_VOLATILE
            if (self.volatile or self.growth)
            else StrategyOptimizer.BOUNDS
        )
        self.optimizer = StrategyOptimizer(
            self.bot.get_params(), bounds=bounds, volatile=(self.volatile or self.growth),
        )
        self.learning_logger: LearningLogger | None = None
        self.last_tune_ts = 0.0
        self.last_snapshot_ts = 0.0
        self._trades_at_last_tune = 0
        self._restored = False

    def set_params_bounded(self, updates: dict):
        merged = {**self.bot.get_params(), **updates}
        self.bot.update_params(self.optimizer.apply_params(merged))

    def sync_base_params(self):
        """Keep baseline in sync with tuned params — prevents brain rollback."""
        self.base_params = copy.deepcopy(self.bot.get_params())
        bounds = (
            StrategyOptimizer.BOUNDS_VOLATILE
            if (self.volatile or self.growth)
            else StrategyOptimizer.BOUNDS
        )
        self.optimizer = StrategyOptimizer(
            self.base_params, bounds=bounds, volatile=(self.volatile or self.growth),
        )

    async def restore_from_db(self) -> bool:
        if not self.learning_logger:
            return False
        saved = await self.learning_logger.load_session(self.symbol)
        if not saved:
            return False
        self.engine.restore(
            quote=saved["quote"],
            base=saved["base"],
            trade_counter=saved["trade_counter"],
            start_balance=saved["start_balance"],
            start_ts=saved["start_ts"],
            trades=saved.get("trades"),
            cost_basis=saved.get("cost_basis", 0),
        )
        self.bot.update_params(saved["bot_params"])
        self.bot.last_dca_ts = saved.get("last_dca_ts", 0)
        self.bot.last_take_profit_ts = saved.get("last_take_profit_ts", 0)
        self.bot.last_dip_ts = saved.get("last_dip_ts", 0)
        self.bot.last_spike_ts = saved.get("last_spike_ts", 0)
        self.bot.last_stop_loss_ts = saved.get("last_stop_loss_ts", 0)
        self.bot.enabled = saved.get("bot_enabled", True)
        db_trades = await self.learning_logger.all_trades_for_symbol(self.symbol)
        if len(db_trades) > len(self.engine.trades):
            self.engine.restore(
                quote=saved["quote"],
                base=saved["base"],
                trade_counter=max(saved["trade_counter"], len(db_trades)),
                start_balance=saved["start_balance"],
                start_ts=saved["start_ts"],
                trades=db_trades,
                cost_basis=saved.get("cost_basis", 0),
            )
        self.sync_base_params()
        self._restored = True
        logger.info("[%s] restored portfolio $%.2f (%d trades)", self.symbol,
                    self.engine.snapshot(self.feed.price or self.demo_price)["portfolio_value"],
                    len(self.engine.trades))
        return True

    async def persist(self):
        if not self.learning_logger:
            return
        price = self.feed.price or self.demo_price
        await self.learning_logger.save_session(self.symbol, {
            "quote": self.engine.position.quote,
            "base": self.engine.position.base,
            "cost_basis": self.engine.position.cost_basis,
            "trade_counter": len(self.engine.trades),
            "start_balance": self.engine.start_balance,
            "start_ts": self.engine.start_ts,
            "bot_params": self.bot.get_params(),
            "last_dca_ts": self.bot.last_dca_ts,
            "last_take_profit_ts": self.bot.last_take_profit_ts,
            "last_dip_ts": self.bot.last_dip_ts,
            "last_spike_ts": self.bot.last_spike_ts,
            "last_stop_loss_ts": self.bot.last_stop_loss_ts,
            "bot_enabled": self.bot.enabled,
            "trades": self.engine.export_trades(limit=200),
        })

    async def _log_trade(self, trade):
        if self.learning_logger:
            await self.learning_logger.log_trade(
                trade, self.bot.get_params(), symbol=self.symbol,
            )
        await self.persist()

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

        if self._restored:
            return

        price = self.feed.price
        if price > 0:
            sma = self.candles.sma(int(self.bot.params["sma_period"]))
            trade = self.bot.maybe_trade(price, sma)
            if trade:
                logger.info("[%s] стартовая сделка: %s", self.symbol, trade.reason)
                await self._log_trade(trade)

    async def _execute_trades(self, trades: list[Trade], msgs: list[dict[str, Any]]):
        for trade in trades:
            await self._log_trade(trade)
            msgs.append({
                "type": "trade",
                "symbol": self.symbol,
                "label": self.label,
                "trade": {
                    "side": trade.side,
                    "price": trade.price,
                    "amount_quote": trade.amount_quote,
                    "reason": trade.reason,
                    "ts": trade.ts,
                },
            })

    async def on_tick(self, price: float, ts: float) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        closed = self.candles.add_tick(price, ts)
        sma_period = int(self.bot.params.get("sma_period", 20))
        sma = self.candles.sma(sma_period)

        closed_dict = closed.to_dict() if closed else None
        walk_prices = prices_for_tick(price, closed_dict)
        executed = run_strategy_prices(self.bot, walk_prices, sma)
        await self._execute_trades(executed, msgs)

        if closed:
            msgs.append({"type": "candle", "symbol": self.symbol, "candle": closed_dict})

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
            if self.learning_logger:
                await self.learning_logger.log_snapshot(
                    snap, self.bot.get_params(), symbol=self.symbol,
                )

        if self.optimizer.should_tune(
            snap["trade_count"],
            snap.get("vs_hold_pct"),
            pnl_pct=snap.get("pnl_pct", 0),
            trades_since_tune=snap["trade_count"] - self._trades_at_last_tune,
        ):
            interval = self.optimizer.tune_interval_sec()
            losing_fast = (
                snap["trade_count"] - self._trades_at_last_tune >= config.FAST_LEARN_EVERY_N_TRADES
                and snap.get("vs_hold_pct", 0) < -0.5
            )
            if losing_fast or (now - self.last_tune_ts >= interval):
                vol = self._volatility_pct(self.candles.last_n(20))
                new_params, reason = self.optimizer.tune(
                    snap["vs_hold_pct"],
                    snap["trade_count"],
                    recent_trades=self.engine.export_trades()[-20:],
                    volatile=(self.volatile or self.growth),
                    volatility_pct=vol,
                    pnl_pct=snap.get("pnl_pct", 0),
                )
                self.bot.update_params(new_params)
                self.sync_base_params()
                self.last_tune_ts = now
                self._trades_at_last_tune = snap["trade_count"]
                if self.learning_logger:
                    await self.learning_logger.log_strategy_change(
                        new_params, reason, snap["pnl_pct"], symbol=self.symbol,
                    )
                await self.persist()
                msgs.append({
                    "type": "strategy_update",
                    "symbol": self.symbol,
                    "label": self.label,
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
            "growth": self.growth,
            "viral": self.viral,
            "tier": self.tier,
            "restored": self._restored,
            "price": price,
            "portfolio": self.engine.snapshot(price),
            "strategy": self.bot.status(price, sma),
            "candles": self.candles.all_candles()[-100:],
            "source": self.feed.source,
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
            "growth": self.growth,
            "viral": self.viral,
            "tier": self.tier,
            "volatility_pct": volatility,
            "portfolio": self.engine.snapshot(price),
            "strategy": self.bot.status(price, sma),
            "candles": candles,
            "trade_count": len(self.engine.trades),
            "trade_stats": self._trade_stats(),
            "recent_trades": recent,
            "feed_source": self.feed.source,
            "avg_entry": self.engine.avg_entry_price(),
            "bot_enabled": self.bot.enabled,
        }

    def _trade_stats(self) -> dict[str, int]:
        stats = {"dca": 0, "dip": 0, "spike": 0, "tp": 0, "stop": 0, "manual": 0, "buy": 0, "sell": 0}
        for t in self.engine.trades:
            stats["buy" if t.side == "buy" else "sell"] += 1
            r = t.reason.upper()
            if "STOP" in r:
                stats["stop"] += 1
            elif "MANUAL" in r:
                stats["manual"] += 1
            elif "SPIKE" in r:
                stats["spike"] += 1
            elif "DIP" in r:
                stats["dip"] += 1
            elif "DCA" in r:
                stats["dca"] += 1
            elif "TAKE-PROFIT" in r:
                stats["tp"] += 1
        return stats

    async def manual_trade(self, side: str, amount_quote: float, reason: str = "MANUAL") -> dict | None:
        price = self.feed.price or self.demo_price
        if price <= 0:
            return None
        if side == "buy":
            trade = self.engine.buy(price, amount_quote, reason=f"MANUAL: {reason}")
        elif side == "sell":
            base = amount_quote / price
            trade = self.engine.sell(price, base, reason=f"MANUAL: {reason}")
        else:
            return None
        if trade:
            await self._log_trade(trade)
        return {
            "side": trade.side,
            "price": trade.price,
            "amount_quote": trade.amount_quote,
            "reason": trade.reason,
            "ts": trade.ts,
        } if trade else None

    async def deposit(self, amount: float) -> float:
        """Add paper USDT to this market wallet."""
        if amount <= 0:
            return 0.0
        self.engine.position.quote += amount
        self.engine.start_balance += amount
        await self.persist()
        return self.engine.position.quote

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
