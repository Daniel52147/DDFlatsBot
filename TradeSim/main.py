"""
TradeSim — multi-market paper trading with live crypto data.
"""

from __future__ import annotations

import asyncio
import copy
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
from learning.analytics import build_portfolio_analytics
from learning.logger import LearningLogger
from learning.optimizer import StrategyOptimizer
from simulator.market_session import MarketSession
from simulator.shadow_lab import ShadowLab

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tradesim")

BASE_DIR = Path(__file__).resolve().parent

sessions: dict[str, MarketSession] = {
    m["symbol"]: MarketSession(m) for m in config.MARKETS
}
shadow_lab: ShadowLab | None = None
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


class ManualTradeRequest(BaseModel):
    symbol: str
    side: str  # buy | sell
    amount_usd: float = 25.0
    reason: str = "ручная сделка"


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
        msgs = await session.on_tick(price, ts)
        if shadow_lab and config.SHADOW_LAB_ENABLED:
            period = int(session.bot.params.get("sma_period", 20))
            sma = session.candles.sma(period)
            shadow_lab.on_tick(session.symbol, price, sma)
            for msg in msgs:
                if msg.get("type") == "candle" and msg.get("candle"):
                    shadow_lab.on_candle(session.symbol, msg["candle"], sma)
        for msg in msgs:
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
    """Central brain thinks every BRAIN_CYCLE_SEC — agents report, brain decides."""
    await asyncio.sleep(15)
    while state["running"]:
        try:
            ctx = all_contexts()
            total = total_portfolio()
            cycle = await brain.think(ctx, total)
            state["brain_cycle"] = cycle
            prev_decision = brain.last_applied_decision
            brain.apply_decision(sessions, cycle["decision"])
            if brain.last_applied_decision != prev_decision:
                for s in sessions.values():
                    await s.persist()
            brain.apply_learning_boost(sessions, ctx)
            brain.apply_schemer_hints(sessions, cycle.get("schemer", {}))
            await logger_db.log_brain_cycle(cycle["decision"], cycle["verdict"])
            await logger_db.log_assistant("brain", cycle["summary"])
            await broadcast({"type": "brain_update", "cycle": _brain_public(cycle)})
        except Exception as e:
            logger.warning("brain loop error: %s", e)
        await asyncio.sleep(config.BRAIN_CYCLE_SEC)


async def shadow_eval_loop():
    """Evaluate shadow clones and promote winners to live bots."""
    await asyncio.sleep(30)
    while state["running"]:
        try:
            if shadow_lab and config.SHADOW_LAB_ENABLED:
                promotions = shadow_lab.evaluate_and_promote()
                for p in promotions:
                    sym = p["symbol"]
                    if sym in sessions:
                        s = sessions[sym]
                        await s.persist()
                        reason = (
                            f"🔬 Shadow Lab: клон #{p['clone_id']} vs hold {p['vs_hold_pct']:+.2f}% "
                            f"(live {p['live_vs_hold']:+.2f}%) — {', '.join(p['changes'])}"
                        )
                        await logger_db.log_strategy_change(
                            s.bot.get_params(), reason,
                            s.engine.snapshot(s.feed.price).get("pnl_pct", 0),
                            symbol=sym,
                        )
                        await broadcast({
                            "type": "shadow_promote",
                            "symbol": sym,
                            "label": p["label"],
                            "clone_id": p["clone_id"],
                            "reason": reason,
                        })
        except Exception as e:
            logger.warning("shadow eval error: %s", e)
        await asyncio.sleep(config.SHADOW_EVAL_SEC)


async def snapshot_loop():
    """Log total portfolio value every 5 minutes for equity curve."""
    await asyncio.sleep(60)
    while state["running"]:
        try:
            t = total_portfolio()
            await logger_db.log_total_snapshot(t["total_value"], t["pnl_pct"])
        except Exception as e:
            logger.warning("snapshot loop error: %s", e)
        await asyncio.sleep(300)


def _market_meta() -> list[dict[str, Any]]:
    return [
        {
            "symbol": m["symbol"],
            "label": m["label"],
            "name": m.get("name", m["label"]),
            "volatile": m.get("volatile", False),
            "price_decimals": config.PRICE_DECIMALS.get(m["label"], 2),
        }
        for m in config.MARKETS
    ]


def _all_trades(limit: int = 30) -> list[dict[str, Any]]:
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
    return all_trades[:limit]


def _bootstrap_payload() -> dict[str, Any]:
    return {
        "version": config.APP_VERSION,
        "market_meta": _market_meta(),
        "markets": {sym: s.status_payload() for sym, s in sessions.items()},
        "total": total_portfolio(),
        "brain": _brain_public(state["brain_cycle"]) if state.get("brain_cycle") else None,
        "trades": _all_trades(),
        "chat": state["chat_history"][-1]["content"] if state.get("chat_history") else "",
    }


def _analytics_payload(equity: list | None = None) -> dict[str, Any]:
    snaps = []
    for s in sessions.values():
        snaps.append({
            "symbol": s.symbol,
            "label": s.label,
            "portfolio": s.engine.snapshot(s.feed.price or s.demo_price),
            "trades": s.engine.export_trades(),
            "avg_entry": s.engine.avg_entry_price(),
            "bot_enabled": s.bot.enabled,
        })
    return build_portfolio_analytics(snaps, equity)


async def _bootstrap_payload_async() -> dict[str, Any]:
    payload = _bootstrap_payload()
    payload["learning"] = await logger_db.performance_summary()
    equity = await logger_db.equity_curve(48)
    payload["equity"] = equity
    payload["brain_history"] = await logger_db.brain_history(6)
    payload["analytics"] = _analytics_payload(equity)
    payload["strategy_history"] = await logger_db.strategy_history(limit=10)
    if shadow_lab:
        payload["shadow_lab"] = shadow_lab.status()
    return payload


def _brain_public(cycle: dict) -> dict:
    """Trim cycle for frontend with agent drill-down data."""

    def _agent(report: dict) -> dict:
        return {
            "emoji": report["emoji"],
            "name": report["name"],
            "summary": report["summary"],
            "action": report.get("action_for_brain", ""),
            "recommendation": report.get("recommendation"),
        }

    news = cycle["news"]
    return {
        "verdict": cycle.get("verdict"),
        "decision": cycle.get("decision"),
        "summary": cycle.get("summary"),
        "mentor": {**_agent(cycle["mentor"]), "insights": cycle["mentor"].get("insights", [])[:4]},
        "news": {
            **_agent(news),
            "sentiment": news.get("sentiment"),
            "headlines": news.get("headlines", [])[:4],
        },
        "schemer": {
            **_agent(cycle["schemer"]),
            "proposals": cycle["schemer"].get("proposals", [])[:3],
            "learned": cycle["schemer"].get("learned", [])[:2],
        },
        "volatility": {
            **_agent(cycle["volatility"]),
            "hot": cycle["volatility"].get("hot", []),
            "spikes": cycle["volatility"].get("spikes", []),
        },
        "risk": {
            **_agent(cycle["risk"]),
            "warnings": cycle["risk"].get("warnings", [])[:4],
            "critical": cycle["risk"].get("critical", []),
        },
        "trend": {
            **_agent(cycle["trend"]),
            "trends": cycle["trend"].get("trends", [])[:5],
            "counts": cycle["trend"].get("counts", {}),
        },
        "profit": {
            **_agent(cycle["profit"]),
            "tips": cycle["profit"].get("tips", [])[:4],
            "ready": cycle["profit"].get("ready", [])[:3],
        },
        "correlation": {
            **_agent(cycle["correlation"]),
            "pairs": cycle["correlation"].get("pairs", [])[:4],
            "leaders": cycle["correlation"].get("leaders", [])[:2],
            "laggards": cycle["correlation"].get("laggards", [])[:2],
        },
        "analyst": {
            **_agent(cycle["analyst"]),
            "highlights": cycle["analyst"].get("highlights", [])[:4],
            "metrics": cycle["analyst"].get("metrics", {}),
        },
        "guardian": {
            **_agent(cycle["guardian"]),
            "alerts": cycle["guardian"].get("alerts", [])[:4],
            "halts": cycle["guardian"].get("halts", []),
        },
        "allocator": {
            **_agent(cycle["allocator"]),
            "suggestions": cycle["allocator"].get("suggestions", [])[:3],
            "overweight": cycle["allocator"].get("overweight", [])[:2],
        },
        "ts": cycle.get("ts"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global shadow_lab
    await logger_db.init()
    shadow_lab = ShadowLab(sessions)
    for session in sessions.values():
        session.learning_logger = logger_db
    for session in sessions.values():
        await session.restore_from_db()
    for session in sessions.values():
        await session.startup()

    state["running"] = True
    tasks = [asyncio.create_task(run_session_loop(s)) for s in sessions.values()]
    tasks.append(asyncio.create_task(brain_loop()))
    tasks.append(asyncio.create_task(shadow_eval_loop()))
    tasks.append(asyncio.create_task(snapshot_loop()))

    # First brain think
    cycle = await brain.think(all_contexts(), total_portfolio())
    state["brain_cycle"] = cycle
    brain.apply_decision(sessions, cycle["decision"])
    brain.apply_learning_boost(sessions, all_contexts())
    brain.apply_schemer_hints(sessions, cycle.get("schemer", {}))

    greeting = brain.chat("привет", all_contexts(), total_portfolio())
    state["chat_history"] = [
        {"role": "assistant", "content": greeting},
        {"role": "assistant", "content": cycle["summary"]},
    ]
    await logger_db.log_assistant("assistant", greeting)

    yield

    state["running"] = False
    for s in sessions.values():
        await s.persist()
        s.feed.stop()
    for t in tasks:
        t.cancel()


app = FastAPI(title="TradeSim", description="Multi-market paper trading", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    payload = await _bootstrap_payload_async()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"initial_json": json.dumps(payload, ensure_ascii=False)},
    )


@app.get("/api/markets")
async def api_markets():
    return {
        "markets": [m for m in config.MARKETS],
        "market_meta": _market_meta(),
        "total": total_portfolio(),
        "mode": "paper",
    }


@app.get("/api/bootstrap")
async def api_bootstrap():
    return await _bootstrap_payload_async()


@app.get("/api/learning/summary")
async def api_learning_summary():
    return await logger_db.performance_summary()


@app.get("/api/learning/equity")
async def api_equity(hours: int = 48):
    return {"curve": await logger_db.equity_curve(hours)}


@app.get("/api/shadow-lab")
async def api_shadow_lab(symbol: str | None = None):
    if not shadow_lab:
        return {"enabled": False}
    return {
        **shadow_lab.status(),
        "leaderboard": shadow_lab.leaderboard(symbol, limit=20),
    }


@app.post("/api/shadow-lab/reset")
async def api_shadow_reset(symbol: str | None = None):
    if shadow_lab:
        shadow_lab.reset_clones(symbol)
    return {"ok": True, "status": shadow_lab.status() if shadow_lab else {}}


@app.get("/api/analytics")
async def api_analytics():
    equity = await logger_db.equity_curve(48)
    return _analytics_payload(equity)


@app.get("/api/strategy/history")
async def api_strategy_history(symbol: str | None = None, limit: int = 15):
    return {"history": await logger_db.strategy_history(symbol, limit)}


@app.get("/api/export/trades")
async def api_export_trades():
    trades = _all_trades(500)
    return {"trades": trades, "count": len(trades), "version": config.APP_VERSION}


@app.get("/api/brain/history")
async def api_brain_history():
    return {"history": await logger_db.brain_history(10)}


@app.get("/api/ping")
async def api_ping():
    return {
        "version": config.APP_VERSION,
        "markets": list(sessions.keys()),
        "market_meta": _market_meta(),
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
    return {"trades": _all_trades(50)}


@app.post("/api/bot/toggle")
async def toggle_bot(symbol: str = config.MARKETS[0]["symbol"]):
    if symbol not in sessions:
        return {"error": "unknown symbol"}
    s = sessions[symbol]
    s.bot.enabled = not s.bot.enabled
    await s.persist()
    return {"symbol": symbol, "enabled": s.bot.enabled}


@app.post("/api/trade")
async def manual_trade(body: ManualTradeRequest):
    if body.symbol not in sessions:
        return {"error": "unknown symbol"}
    if body.side not in ("buy", "sell"):
        return {"error": "side must be buy or sell"}
    if body.amount_usd <= 0 or body.amount_usd > 500:
        return {"error": "amount_usd must be 1–500"}
    s = sessions[body.symbol]
    trade = await s.manual_trade(body.side, body.amount_usd, body.reason)
    if not trade:
        return {"error": "trade failed — insufficient balance or price"}
    await broadcast({
        "type": "trade",
        "symbol": body.symbol,
        "label": s.label,
        "trade": trade,
    })
    return {"ok": True, "trade": trade, "portfolio": s.engine.snapshot(s.feed.price)}


@app.post("/api/reset")
async def reset_portfolio(full: bool = False):
    if full:
        await logger_db.full_reset()
    else:
        await logger_db.clear_sessions()
    for s in sessions.values():
        market = next(m for m in config.MARKETS if m["symbol"] == s.symbol)
        s.engine.reset(config.BALANCE_PER_MARKET)
        s.base_params = copy.deepcopy({**config.STRATEGY, **market.get("strategy", {})})
        bounds = StrategyOptimizer.BOUNDS_VOLATILE if s.volatile else StrategyOptimizer.BOUNDS
        s.optimizer = StrategyOptimizer(s.base_params, bounds=bounds, volatile=s.volatile)
        s.bot.update_params(dict(s.base_params))
        s.bot.last_dca_ts = 0.0
        s.bot.last_take_profit_ts = 0.0
        s.bot.last_dip_ts = 0.0
        s.bot.last_spike_ts = 0.0
        s.bot.last_stop_loss_ts = 0.0
        s.bot.enabled = True
        s._restored = False
        await s.persist()
    state["chat_history"] = []
    state["brain_cycle"] = None
    if shadow_lab:
        shadow_lab.reset_clones()
        shadow_lab.total_shadow_trades = 0
    return {"total": total_portfolio(), "full": full}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    state["connected_clients"].add(ws)
    try:
        await ws.send_json({
            "type": "init",
            "version": config.APP_VERSION,
            "market_meta": _market_meta(),
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
