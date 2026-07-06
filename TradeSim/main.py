"""
TradeSim — multi-market paper trading with live crypto data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

import config
from assistant.coordinator import CentralBrain
from learning.logger import LearningLogger
from simulator.market_session import MarketSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tradesim")

BASE_DIR = Path(__file__).resolve().parent

sessions: dict[str, MarketSession] = {
    m["symbol"]: MarketSession(m) for m in config.MARKETS
}
logger_db = LearningLogger()
brain = CentralBrain()

state: dict[str, Any] = {
    "connected_clients": set(),
    "running": False,
    "chat_history": [],
    "brain_cycle": None,
}


class ChatRequest(BaseModel):
    message: str


async def broadcast(data: dict):
    dead = set()
    for ws in state["connected_clients"]:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    state["connected_clients"] -= dead


def all_contexts() -> list[dict[str, Any]]:
    return [s.context_for_assistant() for s in sessions.values()]


def total_portfolio() -> dict[str, Any]:
    total = sum(s.engine.snapshot(s.feed.price)["portfolio_value"] for s in sessions.values())
    start = config.INITIAL_BALANCE
    pnl = total - start
    return {
        "total_value": round(total, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / start * 100, 2) if start else 0,
        "start_balance": start,
    }


async def run_session_loop(session: MarketSession):
    async def on_tick(price: float, ts: float):
        for msg in await session.on_tick(price, ts):
            await broadcast(msg)

    session.feed.on_tick(on_tick)
    try:
        await session.feed.fetch_price()
        session.candles.add_tick(session.feed.price, session.feed.last_update)
    except Exception as e:
        logger.warning("[%s] initial price: %s", session.symbol, e)

    ws_task = asyncio.create_task(session.feed.run_websocket())
    try:
        while state["running"]:
            await asyncio.sleep(3)
            if time.time() - session.feed.last_update > 2:
                try:
                    p = await session.feed.fetch_price()
                    await on_tick(p, session.feed.last_update)
                except Exception as e:
                    logger.warning("[%s] poll failed: %s", session.symbol, e)
    finally:
        session.feed.stop()
        ws_task.cancel()


async def brain_loop():
    """Central brain thinks every 2 minutes — agents report, brain decides."""
    await asyncio.sleep(15)  # wait for market data
    while state["running"]:
        try:
            ctx = all_contexts()
            total = total_portfolio()
            cycle = await brain.think(ctx, total)
            state["brain_cycle"] = cycle
            brain.apply_decision(sessions, cycle["decision"])
            await logger_db.log_assistant("brain", cycle["summary"])
            await broadcast({"type": "brain_update", "cycle": _brain_public(cycle)})
        except Exception as e:
            logger.warning("brain loop error: %s", e)
        await asyncio.sleep(120)


def _brain_public(cycle: dict) -> dict:
    """Trim cycle for frontend."""
    return {
        "verdict": cycle.get("verdict"),
        "decision": cycle.get("decision"),
        "summary": cycle.get("summary"),
        "mentor": {
            "emoji": cycle["mentor"]["emoji"],
            "name": cycle["mentor"]["name"],
            "summary": cycle["mentor"]["summary"],
        },
        "news": {
            "emoji": cycle["news"]["emoji"],
            "name": cycle["news"]["name"],
            "summary": cycle["news"]["summary"],
            "sentiment": cycle["news"].get("sentiment"),
        },
        "schemer": {
            "emoji": cycle["schemer"]["emoji"],
            "name": cycle["schemer"]["name"],
            "summary": cycle["schemer"]["summary"],
        },
        "ts": cycle.get("ts"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    await logger_db.init()
    for session in sessions.values():
        await session.startup()

    state["running"] = True
    tasks = [asyncio.create_task(run_session_loop(s)) for s in sessions.values()]
    tasks.append(asyncio.create_task(brain_loop()))

    # First brain think
    cycle = await brain.think(all_contexts(), total_portfolio())
    state["brain_cycle"] = cycle
    brain.apply_decision(sessions, cycle["decision"])

    greeting = brain.chat("привет", all_contexts(), total_portfolio())
    state["chat_history"] = [
        {"role": "assistant", "content": greeting},
        {"role": "assistant", "content": cycle["summary"]},
    ]
    await logger_db.log_assistant("assistant", greeting)

    yield

    state["running"] = False
    for s in sessions.values():
        s.feed.stop()
    for t in tasks:
        t.cancel()


app = FastAPI(title="TradeSim", description="Multi-market paper trading", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    payload = {
        "markets": {sym: s.status_payload() for sym, s in sessions.items()},
        "total": total_portfolio(),
        "brain": _brain_public(state["brain_cycle"]) if state.get("brain_cycle") else None,
        "chat": state["chat_history"][-1]["content"] if state.get("chat_history") else "",
    }
    return templates.TemplateResponse(
        request,
        "index.html",
        {"initial_json": json.dumps(payload, ensure_ascii=False)},
    )


@app.get("/api/markets")
async def api_markets():
    return {
        "markets": [m for m in config.MARKETS],
        "total": total_portfolio(),
        "mode": "paper",
    }


@app.get("/api/bootstrap")
async def api_bootstrap():
    """Один запрос — все данные для UI."""
    all_trades = []
    for sym, s in sessions.items():
        for t in s.engine.trades:
            all_trades.append({
                "symbol": sym, "label": s.label,
                "side": t.side, "price": t.price,
                "amount_quote": t.amount_quote,
                "reason": t.reason, "ts": t.ts,
            })
    all_trades.sort(key=lambda x: x["ts"], reverse=True)
    return {
        "version": 3,
        "markets": {sym: s.status_payload() for sym, s in sessions.items()},
        "total": total_portfolio(),
        "brain": _brain_public(state["brain_cycle"]) if state.get("brain_cycle") else None,
        "trades": all_trades[:30],
        "chat": state["chat_history"][-1]["content"] if state.get("chat_history") else "",
    }


@app.get("/api/ping")
async def api_ping():
    return {
        "version": 3,
        "markets": list(sessions.keys()),
        "brain": state.get("brain_cycle") is not None,
    }


@app.get("/api/status")
async def api_status(symbol: str | None = None):
    if symbol and symbol in sessions:
        return sessions[symbol].status_payload()
    return {
        "markets": {sym: s.status_payload() for sym, s in sessions.items()},
        "total": total_portfolio(),
        "assistant_briefing": state["chat_history"][-1]["content"] if state["chat_history"] else "",
    }


@app.get("/api/brain")
async def api_brain():
    cycle = state.get("brain_cycle")
    if not cycle:
        return {"status": "thinking"}
    return {"status": "ok", "cycle": _brain_public(cycle)}


@app.get("/api/assistant")
async def api_assistant():
    briefing = brain.chat("как идут дела", all_contexts(), total_portfolio())
    messages = await logger_db.recent_assistant_messages(20)
    return {
        "briefing": briefing,
        "messages": messages,
        "chat": state["chat_history"][-10:],
        "brain": _brain_public(state["brain_cycle"]) if state.get("brain_cycle") else None,
    }


@app.post("/api/assistant/chat")
async def api_chat(body: ChatRequest):
    msg = (body.message or "").strip()
    if not msg:
        return {"reply": "Напиши: «как дела?», «новости», «что думает мозг?», «схемы»"}
    reply = brain.chat(msg, all_contexts(), total_portfolio())
    state["chat_history"].append({"role": "user", "content": msg})
    state["chat_history"].append({"role": "assistant", "content": reply})
    state["chat_history"] = state["chat_history"][-40:]
    await logger_db.log_assistant("user", msg)
    await logger_db.log_assistant("assistant", reply)
    return {"reply": reply, "chat": state["chat_history"][-10:]}


@app.get("/api/trades")
async def api_all_trades():
    all_trades = []
    for sym, s in sessions.items():
        for t in s.engine.trades:
            all_trades.append({
                "symbol": sym,
                "label": s.label,
                "side": t.side,
                "price": t.price,
                "amount_quote": t.amount_quote,
                "reason": t.reason,
                "ts": t.ts,
            })
    all_trades.sort(key=lambda x: x["ts"], reverse=True)
    return {"trades": all_trades[:30]}


@app.post("/api/bot/toggle")
async def toggle_bot(symbol: str = config.MARKETS[0]["symbol"]):
    if symbol not in sessions:
        return {"error": "unknown symbol"}
    s = sessions[symbol]
    s.bot.enabled = not s.bot.enabled
    return {"symbol": symbol, "enabled": s.bot.enabled}


@app.post("/api/reset")
async def reset_portfolio():
    for s in sessions.values():
        s.engine.reset(config.BALANCE_PER_MARKET)
        s.bot.last_dca_ts = 0.0
    return {"total": total_portfolio()}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    state["connected_clients"].add(ws)
    try:
        await ws.send_json({
            "type": "init",
            "markets": {sym: s.status_payload() for sym, s in sessions.items()},
            "total": total_portfolio(),
            "assistant": state["chat_history"][-1]["content"] if state["chat_history"] else "",
            "brain": _brain_public(state["brain_cycle"]) if state.get("brain_cycle") else None,
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
