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
from exchange.paper_sync import mirror_base_from_exchange, sync_order_to_paper, sync_trade_to_exchange
from exchange.trading_mode import trading_mode
from exchange.wallet_service import (
    deposit_info,
    exchange_withdraw_usdt,
    mirror_usdt_to_paper,
    paper_withdraw,
    refresh_wallet_bridge,
    wallet_summary,
)
from exchange.live_readiness import assess_live_readiness
from exchange.pnl_tracker import snapshot_exchange_portfolio
from learning.analytics import build_portfolio_analytics
from learning.auto_tactics import AutoTacticsEngine
from learning.capital_allocator import CapitalAllocator
from learning.strategy_outcomes import evaluate_pending, log_switch
from learning.strategy_presets import apply_strategy_preset
from learning.profit_focus import ProfitFocusEngine, apply_profit_max_startup
from learning.scorecard import build_scorecard
from learning.paper_learn_mode import (
    apply_paper_learn_all,
    apply_paper_learn_on_boot,
    apply_paper_learn_trading,
    is_paper_learn_mode,
)
from learning.testnet_mode import apply_testnet_conservative_all, apply_testnet_on_mode_switch
from learning.trade_mode import apply_active_all, apply_active_trading
from learning.logger import LearningLogger
from learning.optimizer import StrategyOptimizer
from security import SecurityMiddleware, auth_required
from simulator.backtest import Backtester, compare_strategies
from simulator.market_session import MarketSession
from simulator.portfolio_benchmark import portfolio_benchmark as compute_portfolio_benchmark
from simulator.feed_hub import FeedHub
from simulator.shadow_lab import ShadowLab
from simulator.strategies import STRATEGY_META, create_bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tradesim")

BASE_DIR = Path(__file__).resolve().parent

sessions: dict[str, MarketSession] = {
    m["symbol"]: MarketSession(m) for m in config.MARKETS
}
shadow_lab: ShadowLab | None = None
feed_hub: FeedHub | None = None
auto_tactics: AutoTacticsEngine | None = None
capital_allocator: CapitalAllocator | None = None
profit_focus: ProfitFocusEngine | None = None
logger_db = LearningLogger()
brain = CentralBrain()
live_exchange = BinanceLiveExchange()

def api_fail(error: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": error, **extra}


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


class WithdrawRequest(BaseModel):
    amount: float
    target: str = "split"
    symbol: str | None = None
    note: str = ""
    wallet: str = "paper"  # paper | exchange
    address: str = ""
    network: str | None = None
    confirm_live: bool = False


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
    strategy_type: str | None = None


class BacktestCompareRequest(BaseModel):
    symbol: str = "BTCUSDT"
    limit: int = 500
    strategies: list[str] = ["dca", "grid", "momentum", "rsi", "scalper"]
    initial_balance: float | None = None


class StrategySwitchRequest(BaseModel):
    symbol: str
    strategy_type: str


class ShadowApplyRequest(BaseModel):
    symbol: str
    clone_id: int


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
            s.on_after_trade = after_paper_trade
            sessions[sym] = s
            added.append(sym)
            logger.info("Added new market session: %s", sym)
    return added


def portfolio_benchmark() -> dict[str, Any]:
    return compute_portfolio_benchmark(sessions)


def total_portfolio() -> dict[str, Any]:
    total = sum(s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"] for s in sessions.values())
    start = sum(s.engine.start_balance for s in sessions.values())
    pnl = total - start
    peak = float(state.get("portfolio_peak", 0) or 0)
    peak = max(peak, start, total)
    if total > peak:
        peak = total
    state["portfolio_peak"] = peak
    bench = portfolio_benchmark()
    return {
        "total_value": round(total, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl / start * 100, 2) if start else 0,
        "start_balance": round(start, 2),
        "portfolio_peak": round(peak, 2),
        "drawdown_pct": round((peak - total) / peak * 100, 2) if peak else 0,
        "markets_count": len(sessions),
        "markets_configured": len(config.MARKETS),
        "benchmark": bench,
        "vs_hold_pct": bench.get("vs_hold_pct", 0),
        "benchmark_note": bench.get("benchmark_note", ""),
        "benchmark_misleading": bench.get("benchmark_misleading", False),
    }


def _learning_honesty(stats: dict) -> dict[str, Any]:
    return {
        "version": config.APP_VERSION,
        "markets_configured": len(config.MARKETS),
        "markets_active": len(sessions),
        "project_readiness": "v40 — безопасность Live, честный drawdown, Paper Learn",
        "really_learns": True,
        "learning_kind": "эвристики + статистика (не нейросеть)",
        "what_is_real": [
            "Сделки на живых ценах Binance/Bybit",
            "Авто-выбор стратегии на каждую монету (grid/momentum/RSI/scalper/DCA)",
            "Копирование идей популярных трейдеров (Ansem, PlanB, Hsaka…)",
            "5 стратегий с state persist и Shadow Lab sync",
            "vs hold benchmark с реальной start_price",
            "Shadow Lab: promote по типу стратегии + ручное применение",
            "Бэктест: сравнение 5 стратегий на одних свечах",
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
                "strategy_type": getattr(s, "strategy_type", m.get("strategy_type", "dca")),
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


class StrategyPresetRequest(BaseModel):
    symbol: str
    preset: str  # aggressive | conservative | balanced


class ActiveTradeRequest(BaseModel):
    symbol: str | None = None
    reset_timers: bool = False


class TradingModeRequest(BaseModel):
    mode: str  # paper | testnet | live
    force: bool = False


async def run_session_loop(session: MarketSession):
    last_lag_fix = 0.0

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
        if session._candles_ready:
            await session.feed.fetch_price()
            await on_tick(session.feed.price, time.time())
    except Exception as e:
        logger.warning("[%s] initial price: %s", session.symbol, e)

    ws_task = None
    if not feed_hub:
        ws_task = asyncio.create_task(session.feed.run_websocket())
    try:
        while state["running"]:
            await asyncio.sleep(3)
            now = time.time()
            lag = session.candles.lag_sec()
            if lag > config.CANDLE_MAX_LAG_SEC and now - last_lag_fix > 30:
                last_lag_fix = now
                try:
                    await session.refresh_candles(force=True)
                    await broadcast({
                        "type": "candles_refreshed",
                        "symbols": [session.symbol],
                    })
                except Exception as e:
                    logger.warning("[%s] lag heal failed: %s", session.symbol, e)
            if feed_hub and session._candles_ready and (session.feed.price or 0) > 0:
                ui_tick = await session.push_candle_ui(session.feed.price, update_candles=False)
                if ui_tick:
                    await broadcast(ui_tick)
            elif not feed_hub and now - session.feed.last_update > 2:
                try:
                    p = await session.feed.fetch_price()
                    await on_tick(p, time.time())
                except Exception as e:
                    logger.warning("[%s] poll failed: %s", session.symbol, e)
    finally:
        session.feed.stop()
        if ws_task:
            ws_task.cancel()


async def brain_loop():
    """Central brain thinks every BRAIN_CYCLE_SEC — agents report, brain decides."""
    from learning.correlation_risk import assess_correlation_risk
    from simulator.risk_gate import set_correlation_block, set_portfolio_halt, set_brain_reduce_aggression

    await asyncio.sleep(15)
    while state["running"]:
        try:
            ctx = all_contexts()
            total = total_portfolio()
            live_exchange.risk.note_portfolio_value(total["total_value"])
            from learning.paper_learn_mode import (
                effective_portfolio_max_drawdown_pct,
                is_paper_learn_mode,
            )
            max_drawdown = effective_portfolio_max_drawdown_pct()
            if total["pnl_pct"] <= -max_drawdown:
                set_portfolio_halt(
                    True,
                    f"portfolio {total['pnl_pct']:+.1f}%",
                )
            else:
                set_portfolio_halt(False)

            corr = assess_correlation_risk(ctx)
            if is_paper_learn_mode() and config.PAPER_LEARN_IGNORE_CORRELATION_BLOCK:
                set_correlation_block(False)
            else:
                set_correlation_block(corr.get("block_buys", False), corr.get("reason", ""))
            state["correlation_risk"] = corr

            cycle = await brain.think(ctx, total)
            state["brain_cycle"] = cycle
            decision = cycle.get("decision", "continue")
            set_brain_reduce_aggression(
                decision in ("reduce_aggression", "pause_dip", "emergency_halt")
            )
            prev_decision = brain.last_applied_decision
            brain.apply_decision(sessions, cycle["decision"])
            if brain.last_applied_decision != prev_decision:
                for s in sessions.values():
                    await s.persist()
            tuned = brain.apply_learning_boost(sessions, ctx)
            hinted = brain.apply_schemer_hints(sessions, cycle.get("schemer", {}))
            for sym in set(tuned + hinted):
                s = sessions[sym]
                price = s.feed.price or s.demo_price
                snap = s.engine.snapshot(price)
                await s.persist()
                await logger_db.log_strategy_change(
                    s.bot.get_params(), "brain micro-tune", snap.get("pnl_pct", 0), symbol=sym,
                )
            if auto_tactics and (config.AUTO_TACTICS_ENABLED or config.AUTO_TRADER_COPY_ENABLED):
                plays = cycle.get("trader_watcher", {}).get("market_plays", {})
                tactic_changes = await auto_tactics.apply_all(
                    sessions, ctx, plays, shadow_lab, logger_db,
                )
                for ch in tactic_changes:
                    await broadcast({"type": "auto_tactic", **ch})
            outcomes = await evaluate_pending(logger_db, sessions)
            if outcomes:
                state["strategy_outcomes"] = outcomes[-5:]
            if capital_allocator:
                alloc_changed = capital_allocator.apply(sessions, ctx)
                for sym in alloc_changed:
                    await sessions[sym].persist()
                state["capital_allocation"] = capital_allocator.status(sessions)
            if profit_focus:
                focus_actions = profit_focus.review(sessions)
                for act in focus_actions:
                    sym = act["symbol"]
                    if sym in sessions:
                        await sessions[sym].persist()
                    await broadcast({"type": "profit_focus", **act})
                state["profit_focus"] = profit_focus.status(sessions)
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


async def candle_health_loop():
    """Detect stale candles and backfill gaps (e.g. after long downtime)."""
    await asyncio.sleep(10)
    while state["running"]:
        try:
            stale = []
            for sym, session in sessions.items():
                lag = session.candles.lag_sec()
                if not session._candles_ready or lag > config.CANDLE_MAX_LAG_SEC:
                    stale.append((sym, lag))
            if stale:
                logger.info("Candle health: refreshing %d markets (max lag %.0fs)", len(stale), max(l for _, l in stale))
                await asyncio.gather(
                    *[sessions[sym].refresh_candles(force=True) for sym, _ in stale],
                    return_exceptions=True,
                )
                await broadcast({
                    "type": "candles_refreshed",
                    "symbols": [s for s, _ in stale],
                })
        except Exception as e:
            logger.warning("candle health error: %s", e)
        await asyncio.sleep(config.CANDLE_HEALTH_SEC)


async def snapshot_loop():
    """Log total portfolio value every 5 minutes for equity curve."""
    await asyncio.sleep(60)
    while state["running"]:
        try:
            t = total_portfolio()
            bench = portfolio_benchmark()
            await logger_db.log_total_snapshot(
                t["total_value"], t["pnl_pct"],
                hold_value=bench["hold_value"], hold_pnl_pct=bench["hold_pnl_pct"],
            )
            if live_exchange.enabled:
                ex = await snapshot_exchange_portfolio(sessions, live_exchange)
                if ex.get("enabled") and not ex.get("error"):
                    await logger_db.log_exchange_snapshot(
                        ex["exchange_total_usd"],
                        ex["paper_total_usd"],
                        ex.get("usdt_free", 0),
                        ex.get("paper_vs_hold_pct", 0),
                    )
                    state["exchange_pnl"] = ex
        except Exception as e:
            logger.warning("snapshot loop error: %s", e)
        await asyncio.sleep(config.EXCHANGE_PNL_SNAPSHOT_SEC)


def collect_alerts() -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    cycle = state.get("brain_cycle")
    if cycle:
        for key in ("risk", "guardian", "volatility"):
            rep = cycle.get(key, {})
            for w in rep.get("warnings", [])[:2]:
                alerts.append({"level": "warn", "source": key, "text": str(w)[:120]})
            for h in rep.get("halts", [])[:1]:
                alerts.append({"level": "halt", "source": key, "text": str(h)[:120]})
        for w in cycle.get("trader_watcher", {}).get("warnings", [])[:2]:
            alerts.append({"level": "info", "source": "trader", "text": str(w)[:120]})
        for p in cycle.get("trader_watcher", {}).get("copy_candidates", [])[:2]:
            alerts.append({
                "level": "good",
                "source": "auto",
                "text": f"👁️ {p['label']}: копируем {p['trader']} → {p['strategy']}",
            })
    for sym, s in sessions.items():
        price = s.feed.price or s.demo_price
        snap = s.engine.snapshot(price)
        if snap.get("vs_hold_pct", 0) < -3:
            alerts.append({
                "level": "warn",
                "source": sym,
                "text": f"{s.label}: отстаёт от hold {snap['vs_hold_pct']:+.1f}%",
            })
        if snap.get("pnl_pct", 0) > 5:
            alerts.append({
                "level": "good",
                "source": sym,
                "text": f"{s.label}: +{snap['pnl_pct']:.1f}% P&L",
            })
    return alerts[:12]


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
            "strategy_type": m.get("strategy_type", "dca"),
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
        "trading_mode": trading_mode.status(live_exchange),
        "profit_focus": profit_focus.status(sessions) if profit_focus else None,
        "paper_learn": is_paper_learn_mode(),
    }


async def _live_readiness_payload() -> dict[str, Any]:
    verify = None
    if live_exchange.enabled:
        verify = await live_exchange.verify_connection()
    tot = total_portfolio()
    return await assess_live_readiness(
        sessions,
        live_exchange,
        logger_db,
        trading_mode,
        benchmark=portfolio_benchmark(),
        verify=verify,
        portfolio_peak=tot.get("portfolio_peak", 0),
    )


def _analytics_payload(equity: list | None = None) -> dict[str, Any]:
    snaps = []
    for s in sessions.values():
        snaps.append({
            "symbol": s.symbol,
            "label": s.label,
            "portfolio": s.engine.snapshot(s.feed.price or s.demo_price),
            "trades": s.engine.export_trades(limit=500),
            "avg_entry": s.engine.avg_entry_price(),
            "bot_enabled": s.bot.enabled,
        })
    return build_portfolio_analytics(snaps, equity)


async def _analytics_payload_db(equity: list | None = None) -> dict[str, Any]:
    """Analytics from SQLite — survives restarts."""
    snaps = []
    for s in sessions.values():
        db_trades = await logger_db.all_trades_for_symbol(s.symbol, limit=500)
        snaps.append({
            "symbol": s.symbol,
            "label": s.label,
            "portfolio": s.engine.snapshot(s.feed.price or s.demo_price),
            "trades": db_trades if db_trades else s.engine.export_trades(limit=500),
            "avg_entry": s.engine.avg_entry_price(),
            "bot_enabled": s.bot.enabled,
        })
    return build_portfolio_analytics(snaps, equity)


async def _scorecard_payload() -> dict[str, Any]:
    summary = await logger_db.performance_summary()
    trade_count = int(summary.get("trade_count", 0))
    readiness = await _live_readiness_payload()
    return build_scorecard(
        total=total_portfolio(),
        trade_count=trade_count,
        readiness=readiness,
        trading_mode=trading_mode.mode,
    )


async def _bootstrap_payload_async() -> dict[str, Any]:
    ensure_all_markets()
    payload = _bootstrap_payload()
    stats = await logger_db.learning_stats()
    payload["learning"] = await logger_db.performance_summary()
    equity = await logger_db.equity_curve(48)
    payload["equity"] = equity
    payload["brain_history"] = await logger_db.brain_history(6)
    payload["analytics"] = await _analytics_payload_db(equity)
    payload["strategy_history"] = await logger_db.strategy_history(limit=10)
    payload["deposits"] = await logger_db.deposit_history(15)
    payload["learning_honesty"] = _learning_honesty(stats)
    payload["markets_table"] = _markets_table_rows()
    if shadow_lab:
        payload["shadow_lab"] = shadow_lab.status()
    payload["auto_tactics"] = _auto_tactics_payload()
    payload["live_readiness"] = await _live_readiness_payload()
    payload["scorecard"] = await _scorecard_payload()
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
            "market_plays": list(cycle["trader_watcher"].get("market_plays", {}).values())[:8],
            "copy_candidates": cycle["trader_watcher"].get("copy_candidates", [])[:5],
        },
        "ts": cycle.get("ts"),
    }


async def after_paper_trade(session, trade):
    result = None
    if trading_mode.should_mirror_to_exchange() and config.EXCHANGE_SYNC_FROM_PAPER:
        tot = total_portfolio()
        result = await sync_trade_to_exchange(
            session, trade, live_exchange,
            portfolio_value=tot["total_value"],
            portfolio_pnl_pct=tot["pnl_pct"],
        )
    payload = {
        "type": "exchange_sync",
        "symbol": session.symbol,
        "label": session.label,
        "total": total_portfolio(),
        "trading_mode": trading_mode.mode,
    }
    if result and result.get("ok"):
        payload["paper_to_exchange"] = result
        await broadcast(payload)
    elif result and not result.get("ok"):
        payload["paper_to_exchange"] = result
        await broadcast(payload)
        logger.warning("[%s] paper→exchange sync failed: %s", session.label, result.get("error"))


async def wallet_bridge_loop():
    """Keep exchange USDT available to bots on testnet/live."""
    await asyncio.sleep(10)
    while state["running"]:
        try:
            await refresh_wallet_bridge(sessions, live_exchange, trading_mode)
        except Exception as e:
            logger.warning("wallet bridge: %s", e)
        await asyncio.sleep(config.WALLET_BRIDGE_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global shadow_lab, feed_hub, auto_tactics, capital_allocator, profit_focus

    await logger_db.init()
    auto_tactics = AutoTacticsEngine()
    capital_allocator = CapitalAllocator()
    profit_focus = ProfitFocusEngine()
    added = ensure_all_markets()
    shadow_lab = ShadowLab(sessions)
    feed_hub = FeedHub(list(sessions.keys()))
    for session in sessions.values():
        feed_hub.register(session.symbol, session.feed)
        session.learning_logger = logger_db
        session.on_after_trade = after_paper_trade
    for session in sessions.values():
        await session.restore_from_db()

    if config.PROFIT_MAX_ON_START:
        apply_profit_max_startup(sessions)
        for s in sessions.values():
            await s.persist()
    elif config.TRADE_MODE == "active" and config.ACTIVE_TRADE_ON_START:
        apply_active_all(
            sessions,
            reset_timers=config.ACTIVE_TRADE_RESET_TIMERS,
        )
        for s in sessions.values():
            await s.persist()
        logger.info("Active trade mode applied to %d markets", len(sessions))

    paper_learn_count = apply_paper_learn_on_boot(sessions)
    if paper_learn_count:
        for s in sessions.values():
            await s.persist()

    if live_exchange.enabled:
        verify = await live_exchange.verify_connection()
        if verify.get("ok"):
            logger.info(
                "Binance %s OK — USDT %.2f · %d assets",
                "testnet" if live_exchange.testnet else "LIVE",
                verify.get("usdt_free", 0),
                verify.get("assets", 0),
            )
        else:
            logger.warning("Binance verify failed: %s", verify.get("error") or verify.get("note"))
    await refresh_wallet_bridge(sessions, live_exchange, trading_mode)

    if config.AUTO_APPLY_TRADING_MODE_ON_START and live_exchange.enabled:
        desired_mode = config.TRADING_MODE_DEFAULT
        if desired_mode in ("testnet", "live") and trading_mode.mode != desired_mode:
            readiness = await _live_readiness_payload() if desired_mode == "live" else None
            mode_result = trading_mode.set_mode(
                desired_mode,
                exchange=live_exchange,
                readiness=readiness,
            )
            if mode_result.get("ok"):
                logger.info("Trading mode auto-applied: %s", desired_mode)
            else:
                logger.warning("Trading mode auto-apply failed: %s", mode_result.get("error"))

    state["running"] = True

    async def parallel_market_startup():
        from simulator.feed_hub import fetch_all_klines_parallel

        try:
            await fetch_all_klines_parallel(sessions, config.CANDLE_INTERVAL, config.CANDLE_STARTUP_LIMIT)
        except Exception as e:
            logger.warning("parallel klines warmup: %s", e)
        await asyncio.gather(
            *[s.startup() for s in sessions.values()],
            return_exceptions=True,
        )
        ready = sum(1 for s in sessions.values() if s._candles_ready)
        max_lag = max((s.candles.lag_sec() for s in sessions.values()), default=0.0)
        logger.info("Candles ready: %d/%d markets (max lag %.0fs)", ready, len(sessions), max_lag)
        from simulator.portfolio_benchmark import sync_all_hold_benchmarks
        sync_all_hold_benchmarks(sessions)
        await broadcast({
            "type": "candles_ready",
            "ready": ready,
            "total": len(sessions),
            "max_lag_sec": round(max_lag, 1),
        })

    try:
        await asyncio.wait_for(parallel_market_startup(), timeout=config.CANDLE_STARTUP_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("Candle startup timeout (%ss) — торговля стартует с частичными данными", config.CANDLE_STARTUP_TIMEOUT_SEC)

    tasks: list[asyncio.Task] = []
    tasks.append(feed_hub.start())
    for s in sessions.values():
        tasks.append(asyncio.create_task(run_session_loop(s)))
    state["background_tasks"] = tasks
    tasks.append(asyncio.create_task(brain_loop()))
    if config.WALLET_BRIDGE_ENABLED:
        tasks.append(asyncio.create_task(wallet_bridge_loop()))
    tasks.append(asyncio.create_task(shadow_eval_loop()))
    tasks.append(asyncio.create_task(snapshot_loop()))
    tasks.append(asyncio.create_task(candle_health_loop()))

    logger.info(
        "TradeSim v%s HTTP ready — свечи синхронизированы — http://127.0.0.1:8765",
        config.APP_VERSION,
    )

    async def first_brain_cycle():
        """Don't block HTTP — agents can take 30–60s on first run."""
        try:
            cycle = await brain.think(all_contexts(), total_portfolio())
            state["brain_cycle"] = cycle
            brain.apply_decision(sessions, cycle["decision"])
            ctx = all_contexts()
            tuned = brain.apply_learning_boost(sessions, ctx)
            hinted = brain.apply_schemer_hints(sessions, cycle.get("schemer", {}))
            for sym in set(tuned + hinted):
                await sessions[sym].persist()
            if auto_tactics and (config.AUTO_TACTICS_ENABLED or config.AUTO_TRADER_COPY_ENABLED):
                plays = cycle.get("trader_watcher", {}).get("market_plays", {})
                await auto_tactics.apply_all(sessions, ctx, plays, shadow_lab, logger_db)
            greeting = brain.chat("привет", ctx, total_portfolio())
            state["chat_history"] = [
                {"role": "assistant", "content": greeting},
                {"role": "assistant", "content": cycle["summary"]},
            ]
            await logger_db.log_assistant("assistant", greeting)
            logger.info("Первый цикл мозга завершён — агенты готовы")
        except Exception:
            logger.exception("Первый цикл мозга не удался — UI всё равно работает")

    tasks.append(asyncio.create_task(first_brain_cycle()))

    import sys

    async def _open_browser_when_ready():
        await asyncio.sleep(1.0)
        import webbrowser
        url = "http://127.0.0.1:8765/health"
        webbrowser.open(url)
        logger.info("Браузер открыт: %s → затем перейди на главную", url)

    if sys.platform == "win32":
        asyncio.create_task(_open_browser_when_ready())

    logger.info("Сайт: http://127.0.0.1:8765  (не localhost, не agent.cvm.dev)")

    yield

    state["running"] = False
    for s in sessions.values():
        await s.persist()
        s.feed.stop()
    for t in tasks:
        t.cancel()
    if feed_hub:
        await feed_hub.close()


app = FastAPI(title="TradeSim", description="Multi-market paper trading", lifespan=lifespan)
app.add_middleware(SecurityMiddleware)
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web" / "static")), name="static")


@app.get("/health", response_class=HTMLResponse)
async def health_page():
    t = total_portfolio()
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
        <title>TradeSim OK</title></head>
        <body style="font-family:system-ui;background:#0c1220;color:#e8eef8;padding:2rem">
        <h1>✅ TradeSim v{config.APP_VERSION} работает</h1>
        <p>Рынков: {len(sessions)} · Портфель: ${t['total_value']:,.2f}</p>
        <p><a href="/" style="color:#00e5a8">→ Открыть панель управления</a></p>
        <p><a href="/api/health" style="color:#7eb8ff">→ JSON health</a></p>
        </body></html>"""
    )


@app.get("/api/health")
async def api_health():
    t = total_portfolio()
    return {
        "ok": True,
        "version": config.APP_VERSION,
        "markets_active": len(sessions),
        "markets_configured": len(config.MARKETS),
        "running": state.get("running", False),
        "feed_hub": feed_hub is not None,
        "shadow_lab": shadow_lab is not None and config.SHADOW_LAB_ENABLED,
        "exchange_enabled": live_exchange.enabled,
        "trading_mode": trading_mode.status(live_exchange),
        "total_value": t["total_value"],
        "pnl_pct": t["pnl_pct"],
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Быстрый ответ — данные подгрузит JS через /api/bootstrap
    return templates.TemplateResponse(
        request,
        "index.html",
        {"initial_json": "null"},
    )


@app.get("/api/markets")
async def api_markets():
    return {
        "markets": [m for m in config.MARKETS],
        "market_meta": _market_meta(),
        "total": total_portfolio(),
        "mode": trading_mode.mode,
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


@app.post("/api/shadow-lab/apply")
async def api_shadow_apply(body: ShadowApplyRequest):
    if not shadow_lab:
        return api_fail("shadow lab disabled")
    if body.symbol not in sessions:
        return api_fail("unknown symbol")
    result = shadow_lab.apply_clone(body.symbol, body.clone_id)
    if result.get("ok"):
        await sessions[body.symbol].persist()
    return result


def _auto_tactics_payload() -> dict[str, Any]:
    cycle = state.get("brain_cycle") or {}
    tw = cycle.get("trader_watcher", {})
    extra = {
        "trader_plays": list(tw.get("market_plays", {}).values())[:12],
        "copy_candidates": tw.get("copy_candidates", [])[:8],
    }
    if auto_tactics:
        return {**auto_tactics.status(sessions), **extra}
    return {
        "enabled": config.AUTO_TACTICS_ENABLED,
        "trader_copy": config.AUTO_TRADER_COPY_ENABLED,
        "total_switches": 0,
        "markets": [],
        **extra,
    }


@app.get("/api/auto-tactics")
async def api_auto_tactics():
    return _auto_tactics_payload()


@app.get("/api/strategies")
async def api_strategies():
    return {"strategies": STRATEGY_META, "version": config.APP_VERSION}


@app.post("/api/strategy/switch")
async def api_strategy_switch(body: StrategySwitchRequest):
    if body.symbol not in sessions:
        return api_fail("unknown symbol")
    if body.strategy_type not in STRATEGY_META:
        return api_fail(f"unknown strategy {body.strategy_type}")
    s = sessions[body.symbol]
    old_type = s.strategy_type
    price = s.feed.price or s.demo_price
    snap_before = s.engine.snapshot(price)
    try:
        result = s.switch_strategy(body.strategy_type)
    except ValueError as e:
        return api_fail(str(e))
    await log_switch(
        logger_db,
        symbol=body.symbol,
        old_type=old_type,
        new_type=body.strategy_type,
        vs_hold_at=float(snap_before.get("vs_hold_pct", 0)),
        pnl_at=float(snap_before.get("pnl_pct", 0)),
        reason="manual UI switch",
    )
    if shadow_lab:
        shadow_lab.reset_clones(body.symbol)
    await s.persist()
    return {"ok": True, "symbol": body.symbol, **result}


@app.get("/api/alerts")
async def api_alerts():
    return {"alerts": collect_alerts(), "benchmark": portfolio_benchmark()}


@app.get("/api/benchmark")
async def api_benchmark():
    return portfolio_benchmark()


@app.get("/api/analytics")
async def api_analytics():
    equity = await logger_db.equity_curve(48)
    return await _analytics_payload_db(equity)



@app.post("/api/strategy/paper-learn")
async def api_strategy_paper_learn(body: ActiveTradeRequest | None = None):
    """Max trades on Paper — faster SQLite learning (only in paper mode)."""
    if trading_mode.mode != "paper":
        return {
            "ok": False,
            "error": "Paper learn только в режиме 📄 Paper",
            "mode": trading_mode.mode,
        }
    body = body or ActiveTradeRequest()
    if body.symbol:
        if body.symbol not in sessions:
            return api_fail("unknown symbol")
        info = apply_paper_learn_trading(
            sessions[body.symbol], reset_timers=body.reset_timers,
        )
        await sessions[body.symbol].persist()
        return {"ok": True, "markets": [info], "mode": "paper_learn"}
    results = apply_paper_learn_all(sessions, reset_timers=body.reset_timers)
    for session in sessions.values():
        await session.persist()
    await broadcast({"type": "paper_learn", "count": len(results)})
    return {"ok": True, "markets": results, "count": len(results), "mode": "paper_learn"}


@app.post("/api/strategy/active")
async def api_strategy_active(body: ActiveTradeRequest | None = None):
    """Shorter cooldowns on one market or all — more buys/sells."""
    body = body or ActiveTradeRequest()
    if body.symbol:
        if body.symbol not in sessions:
            return api_fail("unknown symbol")
        info = apply_active_trading(
            sessions[body.symbol], reset_timers=body.reset_timers,
        )
        await sessions[body.symbol].persist()
        return {"ok": True, "markets": [info]}
    results = apply_active_all(sessions, reset_timers=body.reset_timers)
    for s in sessions.values():
        await s.persist()
    await broadcast({"type": "strategy_active", "count": len(results)})
    return {"ok": True, "markets": results, "count": len(results)}


@app.post("/api/strategy/preset")
async def api_strategy_preset(body: StrategyPresetRequest):
    if body.symbol not in sessions:
        return api_fail("unknown symbol")
    s = sessions[body.symbol]
    if not apply_strategy_preset(s, body.preset):
        return api_fail(f"unknown preset {body.preset}")
    await s.persist()
    return {
        "ok": True,
        "symbol": body.symbol,
        "preset": body.preset,
        "strategy_type": getattr(s, "strategy_type", "dca"),
        "params": s.bot.get_params(),
    }


@app.get("/api/fees")
async def api_fees(hours: int = 168):
    summary = await logger_db.fee_summary(hours)
    label_map = {s.symbol: s.label for s in sessions.values()}
    for row in summary.get("per_symbol", []):
        row["label"] = label_map.get(row.get("symbol", ""), "")
    return summary


@app.get("/api/portfolio/heatmap")
async def api_heatmap():
    cells = []
    for s in sessions.values():
        price = s.feed.price or s.demo_price
        snap = s.engine.snapshot(price)
        cells.append({
            "symbol": s.symbol,
            "label": s.label,
            "tier": s.tier,
            "strategy_type": s.strategy_type,
            "pnl_pct": snap["pnl_pct"],
            "vs_hold_pct": snap.get("vs_hold_pct", 0),
            "portfolio_value": snap["portfolio_value"],
            "bot_enabled": s.bot.enabled,
            "source": s.feed.source,
            "price_stale_sec": round(max(0, time.time() - s.feed.last_update), 1) if s.feed.last_update else 999,
        })
    cells.sort(key=lambda x: x["vs_hold_pct"], reverse=True)
    return {"cells": cells, "benchmark": portfolio_benchmark()}


@app.get("/api/strategy-outcomes")
async def api_strategy_outcomes(limit: int = 25):
    history = await logger_db.strategy_switch_history(min(limit, 50))
    labels = {s.symbol: s.label for s in sessions.values()}
    for row in history:
        row["label"] = labels.get(row.get("symbol", ""), "")
    wins = sum(1 for h in history if h.get("evaluated") and (h.get("outcome_pp") or 0) > 0)
    evaluated = sum(1 for h in history if h.get("evaluated"))
    return {
        "version": config.APP_VERSION,
        "history": history,
        "evaluated": evaluated,
        "wins": wins,
        "win_rate_pct": round(wins / evaluated * 100, 1) if evaluated else 0,
    }


@app.get("/api/scorecard")
async def api_scorecard():
    return await _scorecard_payload()


@app.get("/api/profit-focus")
async def api_profit_focus():
    if not profit_focus:
        return {"enabled": False}
    return profit_focus.status(sessions)


@app.get("/api/capital-allocation")
async def api_capital_allocation():
    if not capital_allocator:
        return {"enabled": False}
    return capital_allocator.status(sessions)


@app.get("/api/strategy-report")
async def api_strategy_report():
    from learning.strategy_report import build_strategy_report

    report = build_strategy_report(sessions)
    report["version"] = config.APP_VERSION
    report["correlation_risk"] = state.get("correlation_risk", {})
    from simulator.risk_gate import risk_status
    report["risk_gate"] = risk_status()
    return report


@app.get("/api/daily-report")
async def api_daily_report():
    since = time.time() - 86400
    trades = await logger_db.trades_since(since, limit=300)
    bench = portfolio_benchmark()
    total = total_portfolio()
    cells = []
    for s in sessions.values():
        snap = s.engine.snapshot(s.feed.price or s.demo_price)
        cells.append({"label": s.label, "pnl_pct": snap["pnl_pct"], "vs_hold_pct": snap.get("vs_hold_pct", 0)})
    cells.sort(key=lambda x: x["pnl_pct"], reverse=True)
    fees = await logger_db.fee_summary(24)
    brain_hist = await logger_db.brain_history(12)
    from learning.strategy_report import build_strategy_report
    strat = build_strategy_report(sessions)
    return {
        "version": config.APP_VERSION,
        "period_hours": 24,
        "total": total,
        "benchmark": bench,
        "trades_count": len(trades),
        "fees_24h": fees.get("total_fees", 0),
        "top_gainers": cells[:3],
        "top_losers": list(reversed(cells[-3:])) if len(cells) >= 3 else [],
        "brain_decisions": brain_hist[-5:],
        "shadow_promotions": shadow_lab.last_promotions[:3] if shadow_lab else [],
        "strategy_leaderboard": strat.get("by_strategy", [])[:5],
        "correlation_risk": state.get("correlation_risk", {}),
    }


@app.get("/api/brain/timeline")
async def api_brain_timeline(limit: int = 25):
    return {"history": await logger_db.brain_history(min(limit, 50))}


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
async def api_candles(symbol: str, limit: int = 200, refresh: bool = False):
    """Historical OHLC for chart — auto backfill if lagging."""
    if symbol not in sessions:
        return api_fail("unknown symbol")
    s = sessions[symbol]
    lim = min(max(limit, 10), config.CANDLE_STARTUP_LIMIT)
    lag = s.candles.lag_sec()
    if refresh or not s._candles_ready or lag > config.CANDLE_MAX_LAG_SEC:
        try:
            info = await s.refresh_candles(force=refresh or lag > config.CANDLE_MAX_LAG_SEC)
            lag = info.get("lag_sec", lag)
        except Exception as e:
            logger.warning("[%s] candle refresh: %s", symbol, e)
    candles = s.candles.all_candles()[-lim:]
    if len(candles) < 30:
        try:
            fetched = await s.feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=lim)
            s.candles.load_history(fetched)
            candles = s.candles.all_candles()[-lim:]
            lag = s.candles.lag_sec()
        except Exception as e:
            logger.warning("[%s] candles fetch fallback: %s", symbol, e)
    return {
        "symbol": symbol,
        "label": s.label,
        "candles": candles,
        "count": len(candles),
        "candle_lag_sec": round(lag, 1),
        "candles_ready": s._candles_ready,
        "candle_source": s.feed.source,
        "server_time": int(time.time()),
    }


@app.post("/api/backtest")
async def api_backtest(body: BacktestRequest):
    sym = body.symbol
    if sym not in sessions:
        return api_fail(f"unknown symbol {sym}")
    s = sessions[sym]
    try:
        candles = await s.feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=min(body.limit, 1000))
    except Exception as e:
        return api_fail(f"klines failed: {e}")
    market = next(m for m in config.MARKETS if m["symbol"] == sym)
    stype = body.strategy_type or getattr(s, "strategy_type", market.get("strategy_type", "dca"))
    params = s.bot.get_params()
    bt = Backtester(
        params=params,
        initial_balance=body.initial_balance or config.BALANCE_PER_MARKET,
        strategy_type=stype,
    )
    result = bt.run(candles)
    result["symbol"] = sym
    result["label"] = s.label
    result["market_tier"] = market.get("tier", "major")
    return result


@app.post("/api/backtest/compare")
async def api_backtest_compare(body: BacktestCompareRequest):
    sym = body.symbol
    if sym not in sessions:
        return api_fail(f"unknown symbol {sym}")
    s = sessions[sym]
    try:
        candles = await s.feed.fetch_klines(interval=config.CANDLE_INTERVAL, limit=min(body.limit, 1000))
    except Exception as e:
        return api_fail(f"klines failed: {e}")
    strategies = [st for st in body.strategies if st in STRATEGY_META] or list(STRATEGY_META.keys())
    results = compare_strategies(
        candles,
        strategies,
        initial_balance=body.initial_balance or config.BALANCE_PER_MARKET,
    )
    return {
        "symbol": sym,
        "label": s.label,
        "candles": len(candles),
        "results": results,
        "winner": results[0]["strategy_type"] if results else None,
    }


@app.get("/api/exchange/verify")
async def api_exchange_verify():
    """Check API keys — call after pasting .env."""
    return await live_exchange.verify_connection()


@app.get("/api/exchange/pnl")
async def api_exchange_pnl():
    snap = await snapshot_exchange_portfolio(sessions, live_exchange)
    snap["version"] = config.APP_VERSION
    snap["curve"] = await logger_db.exchange_pnl_curve(48)
    return snap


@app.get("/api/exchange/status")
async def api_exchange_status():
    return {**live_exchange.status(), **trading_mode.status(live_exchange)}


@app.get("/api/trading-mode")
async def api_trading_mode_get():
    return trading_mode.status(live_exchange)


@app.get("/api/live-readiness")
async def api_live_readiness():
    return await _live_readiness_payload()


@app.post("/api/week-prep/start")
async def api_week_prep_start():
    """One-click: conservative Testnet trading for the 7-day path to Live."""
    apply_testnet_conservative_all(sessions, reset_timers=True)
    for session in sessions.values():
        await session.persist()
    mode_result: dict[str, Any] = {"mode": trading_mode.mode, "ok": True}
    if live_exchange.enabled:
        mode_result = trading_mode.set_mode("testnet", exchange=live_exchange)
    else:
        mode_result = {
            "ok": False,
            "error": "Добавь BINANCE_API_KEY + EXCHANGE_ENABLED=true для Testnet",
            "mode": trading_mode.mode,
        }
    readiness = await _live_readiness_payload()
    if mode_result.get("ok"):
        await broadcast({"type": "trading_mode", **trading_mode.status(live_exchange)})
    return {
        "ok": mode_result.get("ok", False),
        "trading_mode": mode_result,
        "active_markets": len(sessions),
        "live_readiness": readiness,
        "hint": "Testnet + консервативная торговля. Следи P&L, vs Hold и комиссии.",
    }


@app.post("/api/trading-mode")
async def api_trading_mode_set(body: TradingModeRequest):
    readiness = None
    if body.mode == "live":
        readiness = await _live_readiness_payload()
    result = trading_mode.set_mode(
        body.mode,
        exchange=live_exchange,
        readiness=readiness,
        force=body.force,
    )
    if result.get("ok"):
        await broadcast({"type": "trading_mode", **result})
        if body.mode == "paper" and config.PAPER_LEARN_ENABLED:
            apply_paper_learn_all(sessions, reset_timers=True)
            for session in sessions.values():
                await session.persist()
            result["paper_learn"] = True
        elif body.mode in ("testnet", "live"):
            n = apply_testnet_on_mode_switch(sessions, body.mode)
            if n:
                for session in sessions.values():
                    await session.persist()
                result["testnet_discipline"] = True
            await refresh_wallet_bridge(sessions, live_exchange, trading_mode)
    return result


@app.post("/api/exchange/order")
async def api_exchange_order(body: ManualTradeRequest):
    if trading_mode.mode == "paper":
        return api_fail("Биржевые ордера только в режиме 🧪 Testnet или 🏦 Live")
    if body.symbol not in sessions:
        return api_fail("unknown symbol")
    s = sessions[body.symbol]
    snap = s.engine.snapshot(s.feed.price or s.demo_price)
    price = s.feed.price or s.demo_price
    tot = total_portfolio()
    result = await live_exchange.place_market_order(
        body.symbol, body.side, body.amount_usd,
        tot["total_value"], snap.get("pnl_pct", 0),
        price=price,
        portfolio_pnl_pct=tot["pnl_pct"],
    )
    if isinstance(result, dict) and result.get("error"):
        return result
    if (
        result.get("ok")
        and config.EXCHANGE_SYNC_TO_PAPER
        and live_exchange.enabled
        and not result.get("from_paper_sync")
    ):
        paper_sync = await sync_order_to_paper(s, result)
        result["paper_sync"] = paper_sync
        if paper_sync and not paper_sync.get("ok"):
            result["ok"] = False
            result["error"] = (
                paper_sync.get("error") or "paper wallet sync failed after exchange order"
            )
            result["exchange_order_placed"] = True
            result["warning"] = result["error"]
        if paper_sync and paper_sync.get("ok"):
            await broadcast({
                "type": "trade",
                "symbol": body.symbol,
                "label": s.label,
                "trade": {
                    "side": paper_sync.get("side"),
                    "price": paper_sync.get("price"),
                    "amount_quote": paper_sync.get("amount_quote"),
                    "reason": paper_sync.get("reason"),
                    "ts": time.time(),
                },
            })
            await broadcast({
                "type": "exchange_sync",
                "symbol": body.symbol,
                "label": s.label,
                "paper_sync": paper_sync,
                "total": total_portfolio(),
            })
    return result


@app.post("/api/exchange/sync-paper")
async def api_exchange_sync_paper(symbol: str = "BTCUSDT"):
    """Mirror exchange base balance into paper wallet for one market."""
    if symbol not in sessions:
        return api_fail("unknown symbol")
    if not config.EXCHANGE_SYNC_TO_PAPER:
        return api_fail("EXCHANGE_SYNC_TO_PAPER=false")
    result = await mirror_base_from_exchange(sessions[symbol], live_exchange)
    if result.get("ok"):
        await broadcast({
            "type": "exchange_sync",
            "symbol": symbol,
            "label": sessions[symbol].label,
            "mirror": result,
            "total": total_portfolio(),
        })
    return result


@app.get("/api/exchange/reconcile")
async def api_exchange_reconcile(symbol: str = "BTCUSDT"):
    if symbol not in sessions:
        return api_fail("unknown symbol")
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


@app.get("/api/ready")
async def api_ready():
    """Fast readiness probe — no heavy DB work."""
    return {
        "ok": True,
        "version": config.APP_VERSION,
        "running": state.get("running", False),
        "markets_active": len(sessions),
        "markets_count": len(config.MARKETS),
    }


@app.get("/api/ping")
async def api_ping():
    from simulator.risk_gate import risk_status

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
        "ws_auth_required": auth_required(),
        "risk_gate": risk_status(),
        "correlation_risk": state.get("correlation_risk", {}),
    }


@app.post("/api/market/sync-strategy")
async def api_market_sync_strategy(symbol: str):
    """Re-apply config strategy + refresh price feed for one market."""
    market = next((m for m in config.MARKETS if m["symbol"] == symbol), None)
    if not market or symbol not in sessions:
        return api_fail("unknown symbol")
    s = sessions[symbol]
    stype = market.get("strategy_type", "dca")
    params = market.get("strategy") or {}
    s.strategy_type = stype
    s.bot = create_bot(s.engine, stype, params=params)
    s.sync_base_params()
    if feed_hub:
        await feed_hub.ensure_symbol(symbol, s.feed)
    try:
        await s.feed.fetch_price()
    except Exception as e:
        logger.warning("[%s] sync-strategy price fetch: %s", symbol, e)
    await s.persist()
    price = s.feed.price or s.demo_price
    return {
        "ok": True,
        "symbol": symbol,
        "label": s.label,
        "strategy_type": stype,
        "params": s.bot.get_params(),
        "price": price,
        "source": s.feed.source,
    }


@app.post("/api/sync-markets")
async def api_sync_markets():
    """Hot-add markets after update — без полного перезапуска."""
    added = ensure_all_markets()
    for sym in added:
        s = sessions[sym]
        s.learning_logger = logger_db
        if feed_hub:
            await feed_hub.ensure_symbol(sym, s.feed)
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
        return api_fail("Сумма от $1 до $100,000")
    target = (body.target or "split").lower()
    if target == "symbol":
        if not body.symbol or body.symbol not in sessions:
            return api_fail("Укажи symbol, например BTCUSDT")
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


@app.post("/api/withdraw")
async def api_withdraw(body: WithdrawRequest):
    """Вывод USDT с paper или с биржи (testnet/live)."""
    ensure_all_markets()
    amount = float(body.amount)
    wallet = (body.wallet or "paper").lower()

    if wallet == "exchange":
        if trading_mode.mode == "paper":
            return api_fail("Вывод с биржи — переключись на Testnet или Live")
        result = await exchange_withdraw_usdt(
            live_exchange,
            address=body.address,
            amount=amount,
            network=body.network,
            confirm_live=body.confirm_live,
        )
        if not result.get("ok"):
            return result
        total = total_portfolio()
        note = body.note or f"Биржа → {body.address[:8]}…"
        await logger_db.log_withdrawal(
            amount, "exchange", "", note, total["total_value"], wallet="exchange",
        )
        await broadcast({"type": "withdraw", "amount": amount, "wallet": "exchange", "total": total})
        return {
            **result,
            "withdrawn": amount,
            "total": total,
            "withdrawals": await logger_db.withdrawal_history(10),
            "movements": await logger_db.wallet_movements(15),
        }

    result = await paper_withdraw(
        sessions, amount, target=body.target, symbol=body.symbol,
    )
    if not result.get("ok"):
        return result
    total = total_portfolio()
    target = (body.target or "split").lower()
    note = body.note or result.get("note", "Paper вывод")
    await logger_db.log_withdrawal(
        result["withdrawn"], target, body.symbol or "", note, total["total_value"], wallet="paper",
    )
    await refresh_wallet_bridge(sessions, live_exchange, trading_mode)
    await broadcast({"type": "withdraw", "amount": result["withdrawn"], "wallet": "paper", "total": total})
    return {
        "ok": True,
        "withdrawn": result["withdrawn"],
        "total": total,
        "withdrawals": await logger_db.withdrawal_history(10),
        "movements": await logger_db.wallet_movements(15),
    }


@app.get("/api/withdrawals")
async def api_withdrawals():
    return {"withdrawals": await logger_db.withdrawal_history(30)}


@app.get("/api/wallet/movements")
async def api_wallet_movements():
    return {"movements": await logger_db.wallet_movements(40)}


@app.get("/api/wallet/summary")
async def api_wallet_summary():
    return await wallet_summary(sessions, live_exchange, trading_mode)


@app.get("/api/wallet/deposit-info")
async def api_wallet_deposit_info():
    return await deposit_info(live_exchange)


@app.post("/api/wallet/sync-usdt")
async def api_wallet_sync_usdt(amount: float | None = None):
    """Подтянуть USDT с биржи в paper-кошельки ботов."""
    if trading_mode.mode == "paper":
        return api_fail("Синхр. USDT — переключись на Testnet или Live")
    result = await mirror_usdt_to_paper(sessions, live_exchange, amount=amount)
    if result.get("ok"):
        total = total_portfolio()
        await logger_db.log_deposit(
            result.get("mirrored_usdt", 0),
            "exchange_sync",
            "",
            "USDT биржа → paper",
            total["total_value"],
        )
        await refresh_wallet_bridge(sessions, live_exchange, trading_mode)
        await broadcast({"type": "deposit", "amount": result.get("mirrored_usdt", 0), "total": total})
        result["total"] = total
        result["movements"] = await logger_db.wallet_movements(15)
    return result


@app.post("/api/wallet/bridge")
async def api_wallet_bridge():
    bridge = await refresh_wallet_bridge(sessions, live_exchange, trading_mode)
    summary = await wallet_summary(sessions, live_exchange, trading_mode)
    return {"ok": True, "bridge": bridge, "summary": summary}


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
        return api_fail("unknown symbol")
    s = sessions[symbol]
    s.bot.enabled = not s.bot.enabled
    await s.persist()
    return {"ok": True, "symbol": symbol, "enabled": s.bot.enabled}


@app.post("/api/trade")
async def manual_trade(body: ManualTradeRequest):
    if body.symbol not in sessions:
        return api_fail("unknown symbol")
    if body.side not in ("buy", "sell"):
        return api_fail("side must be buy or sell")
    if body.amount_usd <= 0 or body.amount_usd > 500:
        return api_fail("amount_usd must be 1–500")
    s = sessions[body.symbol]
    trade = await s.manual_trade(body.side, body.amount_usd, body.reason)
    if not trade:
        return api_fail("trade failed — insufficient balance or price")
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
    state["portfolio_peak"] = 0.0
    if shadow_lab:
        shadow_lab.reset_clones()
        shadow_lab.total_shadow_trades = 0
    return {"ok": True, "total": total_portfolio(), "full": full}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    from security import API_TOKEN, token_valid

    if API_TOKEN:
        qs_token = ws.query_params.get("token")
        if not token_valid(qs_token):
            await ws.close(code=1008, reason="auth required")
            return
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
    import uvicorn
    from security import require_exposure_auth

    host = config.BIND_HOST
    require_exposure_auth(host)
    if not config.API_TOKEN and config.EXCHANGE_ENABLED:
        logger.warning(
            "BINANCE_API_KEY задан — если ключи светились в чате, ротируй на testnet.binance.vision"
        )
    if not config.API_TOKEN and host == "127.0.0.1":
        logger.info(
            "Локальный режим без TRADESIM_API_TOKEN — для облака задай токен в .env"
        )
    uvicorn.run("main:app", host=host, port=8765, reload=False)
