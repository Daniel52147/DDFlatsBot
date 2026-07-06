"""
TradeSim — paper trading simulator with real-time BTC/USDT data.

Virtual money, real market. Bot learns in one niche: DCA + dip buying.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import config
from assistant.helper import TradingAssistant
from learning.logger import LearningLogger
from learning.optimizer import StrategyOptimizer
from simulator.candles import CandleBuilder
from simulator.engine import SimulatorEngine
from simulator.feed import PriceFeed
from simulator.strategy import StrategyBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tradesim")

BASE_DIR = Path(__file__).resolve().parent

# Global runtime state
engine = SimulatorEngine()
feed = PriceFeed()
candles = CandleBuilder(interval=config.CANDLE_INTERVAL, max_candles=config.MAX_CANDLES)
bot = StrategyBot(engine)
logger_db = LearningLogger()
optimizer = StrategyOptimizer(bot.get_params())
assistant = TradingAssistant()

state: dict[str, Any] = {
  "connected_clients": set(),
  "last_assistant_briefing": "",
  "last_tune_ts": 0.0,
  "last_snapshot_ts": 0.0,
  "running": False,
}


async def broadcast(data: dict):
  dead = set()
  for ws in state["connected_clients"]:
    try:
      await ws.send_json(data)
    except Exception:
      dead.add(ws)
  state["connected_clients"] -= dead


async def on_tick(price: float, ts: float):
  closed = candles.add_tick(price, ts)
  sma_period = int(bot.params.get("sma_period", 20))
  sma = candles.sma(sma_period)

  trade = bot.maybe_trade(price, sma)
  if trade:
    await logger_db.log_trade(trade, bot.get_params())
    msg = assistant.explain_trade(trade.reason, price, engine.snapshot(price))
    await logger_db.log_assistant("system", msg)
    await broadcast({"type": "trade", "trade": {
      "side": trade.side,
      "price": trade.price,
      "amount_quote": trade.amount_quote,
      "reason": trade.reason,
      "ts": trade.ts,
    }})

  if closed:
    await broadcast({"type": "candle", "candle": closed.to_dict()})

  snap = engine.snapshot(price)
  current = candles.current_candle()
  await broadcast({
    "type": "tick",
    "price": price,
    "portfolio": snap,
    "sma": sma,
    "candle": current,
    "source": feed.source,
  })

  # Periodic snapshot + learning check (~every 5 min)
  now = time.time()
  if now - state["last_snapshot_ts"] >= 300:
    state["last_snapshot_ts"] = now
    await logger_db.log_snapshot(snap, bot.get_params())

  if optimizer.should_tune(snap["trade_count"], snap.get("vs_hold_pct")):
    if now - state["last_tune_ts"] > config.LEARNING_CHECK_HOURS * 3600:
      new_params, reason = optimizer.tune(snap["vs_hold_pct"], snap["trade_count"])
      bot.update_params(new_params)
      state["last_tune_ts"] = now
      await logger_db.log_strategy_change(new_params, reason, snap["pnl_pct"])
      await logger_db.log_assistant("tutor", f"🧠 {reason}")
      await broadcast({"type": "strategy_update", "params": new_params, "reason": reason})


async def run_feed_loop():
  feed.on_tick(on_tick)
  await feed.fetch_price()
  candles.add_tick(feed.price, feed.last_update)
  ws_task = asyncio.create_task(feed.run_websocket())
  poll_task = asyncio.create_task(_price_poller())
  while state["running"]:
    await asyncio.sleep(30)
  feed.stop()
  ws_task.cancel()
  poll_task.cancel()


async def _price_poller():
  """Reliable REST backup — keeps chart moving if WebSocket is blocked."""
  while state["running"]:
    await asyncio.sleep(3)
    if time.time() - feed.last_update > 2:
      try:
        p = await feed.fetch_price()
        await on_tick(p, feed.last_update)
      except Exception as e:
        logger.warning("REST poll failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
  await logger_db.init()
  try:
    history = await feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=100)
  except Exception as e:
    logger.error("Klines unavailable at startup: %s", e)
    try:
      price = await feed.fetch_price()
    except Exception as e2:
      logger.error("Price unavailable, demo fallback: %s", e2)
      price = config.DEMO_FALLBACK_PRICE
      feed.price = price
      feed.last_update = time.time()
      feed.source = "demo-fallback"
    history = feed._synthetic_candles(price, 100)
    feed.source = feed.source or "synthetic"
  candles.load_history(history)
  if history:
    feed.price = history[-1]["close"]
    feed.last_update = time.time()

  state["running"] = True
  task = asyncio.create_task(run_feed_loop())

  briefing = assistant.full_briefing(
    candles.last_n(20),
    feed.price,
    candles.sma(int(bot.params["sma_period"])),
    engine.snapshot(feed.price),
    bot.status(feed.price, candles.sma(int(bot.params["sma_period"]))),
    len(engine.trades),
  )
  state["last_assistant_briefing"] = briefing
  await logger_db.log_assistant("assistant", briefing)

  yield

  state["running"] = False
  feed.stop()
  task.cancel()
  try:
    await task
  except asyncio.CancelledError:
    pass


app = FastAPI(title="TradeSim", description="Paper trading BTC/USDT", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
  return templates.TemplateResponse(request, "index.html")


@app.get("/api/status")
async def api_status():
  price = feed.price
  sma = candles.sma(int(bot.params["sma_period"]))
  snap = engine.snapshot(price)
  return {
    "symbol": config.SYMBOL,
    "price": price,
    "portfolio": snap,
    "strategy": bot.status(price, sma),
    "candles": candles.all_candles()[-100:],
    "trades": [
      {
        "side": t.side,
        "price": t.price,
        "amount_quote": t.amount_quote,
        "reason": t.reason,
        "ts": t.ts,
      }
      for t in engine.trades[-20:]
    ],
    "assistant_briefing": state["last_assistant_briefing"],
    "learning": await logger_db.performance_summary(),
    "mode": "paper",
  }


@app.get("/api/assistant")
async def api_assistant():
  price = feed.price
  sma = candles.sma(int(bot.params["sma_period"]))
  briefing = assistant.full_briefing(
    candles.last_n(20),
    price,
    sma,
    engine.snapshot(price),
    bot.status(price, sma),
    len(engine.trades),
  )
  state["last_assistant_briefing"] = briefing
  await logger_db.log_assistant("assistant", briefing)
  messages = await logger_db.recent_assistant_messages(15)
  return {"briefing": briefing, "messages": messages}


@app.post("/api/bot/toggle")
async def toggle_bot():
  bot.enabled = not bot.enabled
  return {"enabled": bot.enabled}


@app.post("/api/reset")
async def reset_portfolio():
  engine.reset()
  bot.last_dca_ts = 0.0
  return engine.snapshot(feed.price)


@app.get("/api/candles")
async def api_candles(interval: str = "1m", limit: int = 100):
  data = await feed.fetch_klines(interval=interval, limit=min(limit, 500))
  return {"candles": data}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
  await ws.accept()
  state["connected_clients"].add(ws)
  try:
    price = feed.price
    await ws.send_json({
      "type": "init",
      "price": price,
      "portfolio": engine.snapshot(price),
      "candles": candles.all_candles()[-100:],
      "strategy": bot.status(price, candles.sma(int(bot.params["sma_period"]))),
      "assistant": state["last_assistant_briefing"],
    })
    while True:
      await ws.receive_text()
  except WebSocketDisconnect:
    pass
  finally:
    state["connected_clients"].discard(ws)


if __name__ == "__main__":
  import uvicorn
  uvicorn.run("main:app", host="0.0.0.0", port=8765, reload=False)
