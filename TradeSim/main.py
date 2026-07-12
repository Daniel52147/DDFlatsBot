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
from exchange.binance_live import BinanceLiveExchange
from learning.analytics import build_portfolio_analytics
from learning.logger import LearningLogger
from learning.optimizer import StrategyOptimizer
from security import SecurityMiddleware, auth_required
from simulator.backtest import Backtester
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
live_exchange = BinanceLiveExchange()

state: dict[str, Any] = {
    "connected_clients": set(),
    "running": False,
    "chat_history": [],
    "brain_cycle": None,
    "background_tasks": [],
}


class DepositRequest(BaseModel):
    amount: float
    target: str = "split"  # split — на все рынки | symbol — на одну монету
    symbol: str | None = None
    note: str = ""


class ChatRequest(BaseModel):
    message: str


class ManualTradeRequest(BaseModel):
    symbol: str
    side: str  # buy | sell
    amount_usd: float = 25.0
    reason: str = "ручная сделка"


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSDT"
    limit: int = 500
    initial_balance: float | None = None


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


def ensure_all_markets() -> list[str]:
    """Add any markets from config that are missing (after code update without full restart)."""
    added = []
    for m in config.MARKETS:
        sym = m["symbol"]
        if sym not in sessions:
            s = MarketSession(m)
            s.learning_logger = logger_db
            sessions[sym] = s
            added.append(sym)
            logger.info("Added new market session: %s", sym)
    return added


def total_portfolio() -> dict[str, Any]:
    total = sum(s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"] for s in sessions.values())
    start = sum(s.engine.start_balance for s in sessions.values())
    pnl = total - start
    return {
        "total_value": round(total, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / start * 100, 2) if start else 0,
        "start_balance": round(start, 2),
        "markets_count": len(sessions),
        "markets_configured": len(config.MARKETS),
    }


def _learning_honesty(stats: dict) -> dict[str, Any]:
    return {
        "version": config.APP_VERSION,
        "markets_configured": len(config.MARKETS),
        "markets_active": len(sessions),
        "project_readiness": "beta ~75% — paper lab + бэктест, не production биржа",
        "really_learns": True,
        "learning_kind": "эвристики + статистика (не нейросеть)",
        "what_is_real": [
            "Сделки на живых ценах Binance/Bybit",
            "Параметры DCA/DIP/TP меняются по vs_hold и сделкам",
            "Shadow Lab: 12 клонов тестируют настройки параллельно",
            "Всё пишется в SQLite — можно проверить",
        ],
        "what_is_not": [
            "Это не настоящие деньги и не гарантия прибыли",
            "12 агентов — правила на Python, не ChatGPT",
            "Реальная биржа только с BINANCE_API_KEY (testnet)",
        ],
        "evidence": stats,
    }


def _markets_table_rows() -> list[dict[str, Any]]:
    rows = []
    for m in config.MARKETS:
        sym = m["symbol"]
        s = sessions.get(sym)
        if s:
            price = s.feed.price or s.demo_price
            snap = s.engine.snapshot(price)
            st = s.bot.status(price, s.candles.sma(int(s.bot.params.get("sma_period", 20))))
            rows.append({
                "symbol": sym,
                "label": m["label"],
                "tier": m.get("tier", "major"),
                "viral": m.get("viral", False),
                "growth": m.get("growth", False),
                "price": price,
                "portfolio_value": snap["portfolio_value"],
                "pnl_pct": snap["pnl_pct"],
                "vs_hold_pct": snap.get("vs_hold_pct", 0),
                "trades": snap["trade_count"],
                "bot_enabled": st.get("enabled", True),
                "active": True,
            })
        else:
            rows.append({
                "symbol": sym,
                "label": m["label"],
                "tier": m.get("tier", "major"),
                "viral": m.get("viral", False),
                "growth": m.get("growth", False),
                "active": False,
            })
    return rows


async def run_session_loop(session: MarketSession):
    async def on_tick(price: float, ts: float):
        msgs = await session.on_tick(price, ts)
        if shadow_lab and config.SHADOW_LAB_ENABLED:
            period = int(session.bot.params.get("sma_period", 20))
            sma = session.candles.sma(period)
            closed_candle = None
            for msg in msgs:
                if msg.get("type") == "candle" and msg.get("candle"):
                    closed_candle = msg["candle"]
            shadow_lab.on_market_update(session.symbol, price, sma, closed_candle)
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
            "growth": m.get("growth", False),
            "viral": m.get("viral", False),
            "tier": m.get("tier", "major"),
            "price_decimals": config.PRICE_DECIMALS.get(m["label"], 2),
        }
        for m in config.MARKETS
    ]


def _all_trades(limit: int | None = 30) -> list[dict[str, Any]]:
    all_trades = []
    for sym, s in sessions.items():
        for t in s.engine.trades:
            all_trades.append({
                "symbol": sym,
                "label": s.label,
                "side": t.side,
                "price": t.price,
                "amount_quote": t.amount_quote,
                "amount_base": t.amount_base,
                "fee": t.fee,
                "reason": t.reason,
                "ts": t.ts,
            })
    all_trades.sort(key=lambda x: x["ts"], reverse=True)
    return all_trades if limit is None else all_trades[:limit]


async def _all_trades_db(limit: int | None = 500, symbol: str | None = None) -> list[dict[str, Any]]:
    """Full trade history from SQLite (authoritative)."""
    rows = await logger_db.all_trades(symbol=symbol, limit=limit, ascending=False)
    label_map = {s.symbol: s.label for s in sessions.values()}
    for r in rows:
        r["label"] = label_map.get(r.get("symbol", ""), r.get("symbol", ""))
    return rows


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
    ensure_all_markets()
    payload = _bootstrap_payload()
    stats = await logger_db.learning_stats()
    payload["learning"] = await logger_db.performance_summary()
    equity = await logger_db.equity_curve(48)
    payload["equity"] = equity
    payload["brain_history"] = await logger_db.brain_history(6)
    payload["analytics"] = _analytics_payload(equity)
    payload["strategy_history"] = await logger_db.strategy_history(limit=10)
    payload["deposits"] = await logger_db.deposit_history(15)
    payload["learning_honesty"] = _learning_honesty(stats)
    payload["markets_table"] = _markets_table_rows()
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
        "trader_watcher": {
            **_agent(cycle["trader_watcher"]),
            "signals": cycle["trader_watcher"].get("signals", [])[:5],
            "hot": cycle["trader_watcher"].get("hot", [])[:3],
            "warnings": cycle["trader_watcher"].get("warnings", [])[:3],
        },
        "ts": cycle.get("ts"),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global shadow_lab
    await logger_db.init()
    added = ensure_all_markets()
    shadow_lab = ShadowLab(sessions)
    for session in sessions.values():
        session.learning_logger = logger_db
    for session in sessions.values():
        await session.restore_from_db()
    for session in sessions.values():
        await session.startup()

    state["running"] = True
    tasks: list[asyncio.Task] = []
    for s in sessions.values():
        tasks.append(asyncio.create_task(run_session_loop(s)))
    state["background_tasks"] = tasks
    tasks.append(asyncio.create_task(brain_loop()))
    tasks.append(asyncio.create_task(shadow_eval_loop()))
    tasks.append(asyncio.create_task(snapshot_loop()))
    logger.info(
        "TradeSim v%s ready — %d markets — http://127.0.0.1:8765",
        config.APP_VERSION, len(sessions),
    )

    async def first_brain_cycle():
        """Don't block HTTP — agents can take 30–60s on first run."""
        try:
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
            logger.info("Первый цикл мозга завершён — агенты готовы")
        except Exception:
            logger.exception("Первый цикл мозга не удался — UI всё равно работает")

    tasks.append(asyncio.create_task(first_brain_cycle()))
    logger.info("Сайт открывай: http://127.0.0.1:8765  (не localhost, не agent.cvm.dev)")

    yield

    state["running"] = False
    for s in sessions.values():
        await s.persist()
        s.feed.stop()
    for t in tasks:
        t.cancel()


app = FastAPI(title="TradeSim", description="Multi-market paper trading", lifespan=lifespan)
app.add_middleware(SecurityMiddleware)
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
async def api_export_trades(symbol: str | None = None, limit: int | None = None):
    trades = await _all_trades_db(limit=limit or 5000, symbol=symbol)
    return {"trades": trades, "count": len(trades), "version": config.APP_VERSION, "source": "sqlite"}


@app.get("/api/trades")
async def api_all_trades(symbol: str | None = None, limit: int = 200):
    trades = await _all_trades_db(limit=limit, symbol=symbol)
    mem_count = sum(len(s.engine.trades) for s in sessions.values())
    return {
        "trades": trades,
        "count": len(trades),
        "memory_trades": mem_count,
        "source": "sqlite",
    }


@app.get("/api/candles")
async def api_candles(symbol: str, limit: int = 200):
    """Historical OHLC for chart — refreshes sparse markets."""
    if symbol not in sessions:
        return {"error": "unknown symbol"}
    s = sessions[symbol]
    lim = min(max(limit, 10), 500)
    try:
        candles = await s.feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=lim)
    except Exception as e:
        logger.warning("[%s] candles fetch: %s", symbol, e)
        candles = s.candles.all_candles()[-lim:]
    return {"symbol": symbol, "label": s.label, "candles": candles, "count": len(candles)}


@app.post("/api/backtest")
async def api_backtest(body: BacktestRequest):
    sym = body.symbol
    if sym not in sessions:
        return {"error": f"unknown symbol {sym}"}
    s = sessions[sym]
    try:
        candles = await s.feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=min(body.limit, 1000))
    except Exception as e:
        return {"error": f"klines failed: {e}"}
    market = next(m for m in config.MARKETS if m["symbol"] == sym)
    params = s.bot.get_params()
    bt = Backtester(params=params, initial_balance=body.initial_balance or config.BALANCE_PER_MARKET)
    result = bt.run(candles)
    result["symbol"] = sym
    result["label"] = s.label
    result["market_tier"] = market.get("tier", "major")
    return result


@app.get("/api/exchange/status")
async def api_exchange_status():
    return live_exchange.status()


@app.post("/api/exchange/order")
async def api_exchange_order(body: ManualTradeRequest):
    if body.symbol not in sessions:
        return {"error": "unknown symbol"}
    s = sessions[body.symbol]
    snap = s.engine.snapshot(s.feed.price or s.demo_price)
    price = s.feed.price or s.demo_price
    return await live_exchange.place_market_order(
        body.symbol, body.side, body.amount_usd,
        snap["portfolio_value"], snap.get("pnl_pct", 0),
        price=price,
    )


@app.get("/api/exchange/reconcile")
async def api_exchange_reconcile(symbol: str = "BTCUSDT"):
    if symbol not in sessions:
        return {"error": "unknown symbol"}
    s = sessions[symbol]
    return await live_exchange.reconcile(
        symbol, s.engine.position.base, s.engine.position.quote,
    )


@app.get("/api/exchange/balances")
async def api_exchange_balances():
    return await live_exchange.account_balances()


@app.get("/api/brain/history")
async def api_brain_history():
    return {"history": await logger_db.brain_history(10)}


@app.get("/api/ping")
async def api_ping():
    ensure_all_markets()
    return {
        "version": config.APP_VERSION,
        "markets": list(sessions.keys()),
        "markets_count": len(config.MARKETS),
        "sessions_active": len(sessions),
        "markets_labels": [m["label"] for m in config.MARKETS],
        "market_meta": _market_meta(),
        "brain": state.get("brain_cycle") is not None,
        "total": total_portfolio(),
        "auth_required": auth_required(),
    }


@app.post("/api/sync-markets")
async def api_sync_markets():
    """Hot-add markets after update — без полного перезапуска."""
    added = ensure_all_markets()
    for sym in added:
        s = sessions[sym]
        await s.restore_from_db()
        await s.startup()
        if state["running"]:
            state["background_tasks"].append(asyncio.create_task(run_session_loop(s)))
    if shadow_lab:
        shadow_lab.sync_markets(sessions)
    await broadcast({
        "type": "markets_sync",
        "added": added,
        "markets": {sym: s.status_payload() for sym, s in sessions.items()},
        "market_meta": _market_meta(),
        "total": total_portfolio(),
    })
    return {
        "ok": True,
        "added": added,
        "markets_active": len(sessions),
        "market_meta": _market_meta(),
        "markets": {sym: s.status_payload() for sym, s in sessions.items()},
        "total": total_portfolio(),
    }


@app.post("/api/deposit")
async def api_deposit(body: DepositRequest):
    """Пополнить paper-счёт в любой момент."""
    ensure_all_markets()
    amount = float(body.amount)
    if amount < 1 or amount > 100_000:
        return {"error": "Сумма от $1 до $100,000"}
    target = (body.target or "split").lower()
    if target == "symbol":
        if not body.symbol or body.symbol not in sessions:
            return {"error": "Укажи symbol, например BTCUSDT"}
        await sessions[body.symbol].deposit(amount)
        note = body.note or f"На {body.symbol}"
    else:
        per = amount / max(len(sessions), 1)
        for s in sessions.values():
            await s.deposit(per)
        note = body.note or f"На все {len(sessions)} рынков"
    total = total_portfolio()
    await logger_db.log_deposit(amount, target, body.symbol or "", note, total["total_value"])
    await broadcast({"type": "deposit", "amount": amount, "total": total})
    return {
        "ok": True,
        "deposited": amount,
        "total": total,
        "deposits": await logger_db.deposit_history(10),
    }


@app.get("/api/deposits")
async def api_deposits():
    return {"deposits": await logger_db.deposit_history(30)}


@app.get("/api/learning/honesty")
async def api_learning_honesty():
    stats = await logger_db.learning_stats()
    return _learning_honesty(stats)


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
    ensure_all_markets()
    if full:
        await logger_db.full_reset()
    else:
        await logger_db.clear_sessions()
    per_market = config.INITIAL_BALANCE / len(config.MARKETS)
    for s in sessions.values():
        market = next(m for m in config.MARKETS if m["symbol"] == s.symbol)
        s.engine.reset(per_market)
        s.base_params = copy.deepcopy({**config.STRATEGY, **market.get("strategy", {})})
        bounds = StrategyOptimizer.BOUNDS_VOLATILE if (s.volatile or s.growth) else StrategyOptimizer.BOUNDS
        s.optimizer = StrategyOptimizer(
            s.base_params, bounds=bounds, volatile=(s.volatile or s.growth),
        )
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
    ensure_all_markets()
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
    import sys
    import threading
    import time
    import webbrowser

    import uvicorn

    host = config.BIND_HOST
    if host == "0.0.0.0" and not config.API_TOKEN:
        logger.warning(
            "TRADESIM_API_TOKEN не задан — не открывай 0.0.0.0 без токена в интернет"
        )

    def _open_browser():
        time.sleep(2.5)
        url = "http://127.0.0.1:8765"
        logger.info("Открываю браузер: %s", url)
        webbrowser.open(url)

    if sys.platform == "win32":
        threading.Thread(target=_open_browser, daemon=True).start()

    uvicorn.run("main:app", host=host, port=8765, reload=False)
