"""Historical backtest — run strategy on candle OHLC in minutes."""

from __future__ import annotations

from typing import Any

import config
from simulator.engine import SimulatorEngine
from simulator.price_walk import ohlc_prices, run_strategy_prices
from simulator.strategies import create_bot


class Backtester:
    """Replay candles with the same OHLC walk as live + Shadow Lab."""

    def __init__(
        self,
        params: dict | None = None,
        initial_balance: float | None = None,
        strategy_type: str = "dca",
    ):
        bal = initial_balance if initial_balance is not None else config.BALANCE_PER_MARKET
        self.engine = SimulatorEngine(initial_balance=bal)
        self.strategy_type = strategy_type
        self.bot = create_bot(self.engine, strategy_type, params=params)

    def run(self, candles: list[dict[str, Any]]) -> dict[str, Any]:
        if not candles:
            return {"error": "no candles", "trades": 0}

        start_price = float(candles[0]["close"])
        self.engine.note_price(start_price)

        sma_period = int(self.bot.params.get("sma_period", 20))
        closes: list[float] = []
        executed = []

        for candle in candles:
            closes.append(float(candle["close"]))
            sma = (
                sum(closes[-sma_period:]) / sma_period
                if len(closes) >= sma_period
                else None
            )
            for price in ohlc_prices(candle):
                self.engine.note_price(price)
                executed.extend(run_strategy_prices(self.bot, [price], sma))

        last_price = float(candles[-1]["close"])
        snap = self.engine.snapshot(last_price)
        sells = sum(1 for t in executed if t.side == "sell")
        buys = sum(1 for t in executed if t.side == "buy")

        return {
            "strategy_type": self.strategy_type,
            "candles": len(candles),
            "trades": len(executed),
            "buys": buys,
            "sells": sells,
            "portfolio_value": snap["portfolio_value"],
            "pnl_pct": snap["pnl_pct"],
            "vs_hold_pct": snap["vs_hold_pct"],
            "hold_pnl_pct": snap.get("hold_pnl_pct", 0),
            "avg_entry": snap.get("avg_entry"),
            "params": self.bot.get_params(),
            "trade_log": [
                {
                    "side": t.side,
                    "price": t.price,
                    "amount_quote": t.amount_quote,
                    "reason": t.reason,
                    "fee": t.fee,
                }
                for t in executed[-30:]
            ],
        }


def compare_strategies(
    candles: list[dict[str, Any]],
    strategy_types: list[str],
    initial_balance: float | None = None,
) -> list[dict[str, Any]]:
    """Run multiple strategy types on the same candle set."""
    results = []
    for st in strategy_types:
        bt = Backtester(initial_balance=initial_balance, strategy_type=st)
        row = bt.run(candles)
        row["strategy_type"] = st
        results.append(row)
    results.sort(key=lambda x: x.get("vs_hold_pct", -999), reverse=True)
    return results
