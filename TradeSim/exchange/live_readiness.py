"""Live trading readiness — gate real money behind checks + 7-day prep plan."""

from __future__ import annotations

import time
from typing import Any

import config


def _days_since(ts: float) -> float:
    if not ts or ts <= 0:
        return 0.0
    return max(0.0, (time.time() - ts) / 86400)


def _earliest_session_age_days(sessions: dict) -> float:
    starts = [getattr(s.engine, "start_ts", 0) for s in sessions.values()]
    starts = [t for t in starts if t and t > 0]
    if not starts:
        return 0.0
    return _days_since(min(starts))


def _check(
    checks: list[dict[str, Any]],
    *,
    cid: str,
    label: str,
    ok: bool,
    detail: str,
    required: bool = True,
) -> None:
    checks.append({
        "id": cid,
        "label": label,
        "ok": bool(ok),
        "detail": detail,
        "required": required,
    })


async def assess_live_readiness(
    sessions: dict,
    exchange,
    logger_db,
    mode_mgr,
    *,
    benchmark: dict[str, Any],
    verify: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score readiness for Binance LIVE — conservative defaults for first real money."""
    checks: list[dict[str, Any]] = []
    total = sum(
        s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"]
        for s in sessions.values()
    )
    start = sum(s.engine.start_balance for s in sessions.values())
    pnl_pct = ((total - start) / start * 100) if start else 0.0

    from main import portfolio_benchmark
    bench = benchmark
    vs_hold = float(bench.get("vs_hold_pct", 0))
    live_pnl = float(bench.get("live_pnl_pct", 0))
    hold_pnl = float(bench.get("hold_pnl_pct", 0))

    trade_count = 0
    try:
        summary = await logger_db.performance_summary()
        trade_count = int(summary.get("trade_count", 0))
    except Exception:
        trade_count = sum(len(s.engine.trades) for s in sessions.values())

    paper_days = _earliest_session_age_days(sessions)
    meta = mode_mgr.milestones()
    testnet_days = _days_since(meta.get("testnet_since", 0))

    if verify is None and exchange.enabled:
        verify = await exchange.verify_connection()
    verify = verify or {"ok": False, "error": "биржа выключена"}

    _check(
        checks,
        cid="api",
        label="API ключи Binance",
        ok=bool(verify.get("ok")),
        detail=verify.get("error") or f"USDT free ${verify.get('usdt_free', 0):.2f}",
    )
    _check(
        checks,
        cid="live_env",
        label="EXCHANGE_TESTNET=false в .env",
        ok=exchange.enabled and not exchange.testnet,
        detail="Live требует реальные ключи api.binance.com, не testnet",
    )
    _check(
        checks,
        cid="paper_days",
        label=f"Paper ≥ {config.LIVE_MIN_DAYS_PAPER} дн.",
        ok=paper_days >= config.LIVE_MIN_DAYS_PAPER,
        detail=f"Сейчас {paper_days:.1f} дн. с первого запуска",
    )
    _check(
        checks,
        cid="testnet_days",
        label=f"Testnet ≥ {config.LIVE_MIN_DAYS_TESTNET} дн.",
        ok=testnet_days >= config.LIVE_MIN_DAYS_TESTNET,
        detail=(
            f"Testnet {testnet_days:.1f} дн. — переключись на 🧪 Testnet и торгуй"
            if testnet_days < config.LIVE_MIN_DAYS_TESTNET
            else f"Testnet {testnet_days:.1f} дн. ✓"
        ),
    )
    _check(
        checks,
        cid="testnet_mode",
        label="Сейчас режим Testnet (не Paper)",
        ok=mode_mgr.mode == "testnet",
        detail=f"Режим: {mode_mgr.mode} — перед Live нужен Testnet",
        required=True,
    )
    _check(
        checks,
        cid="trades",
        label=f"Сделок ≥ {config.LIVE_MIN_TRADES}",
        ok=trade_count >= config.LIVE_MIN_TRADES,
        detail=f"В БД: {trade_count} сделок",
    )
    _check(
        checks,
        cid="pnl",
        label=f"P&L портфеля ≥ {config.LIVE_MIN_PNL_PCT}%",
        ok=pnl_pct >= config.LIVE_MIN_PNL_PCT,
        detail=f"P&L {pnl_pct:+.2f}% · ${total:,.0f}",
    )
    misleading = bool(bench.get("benchmark_misleading"))
    if misleading and vs_hold >= config.LIVE_MIN_VS_HOLD:
        _check(
            checks,
            cid="vs_hold",
            label=f"vs Hold ≥ {config.LIVE_MIN_VS_HOLD}% (честный)",
            ok=False,
            detail=bench.get("benchmark_note") or "vs Hold завышен — смотри P&L",
        )
    else:
        _check(
            checks,
            cid="vs_hold",
            label=f"vs Hold ≥ {config.LIVE_MIN_VS_HOLD}%",
            ok=vs_hold >= config.LIVE_MIN_VS_HOLD,
            detail=(
                f"vs hold {vs_hold:+.1f}% (бот {live_pnl:+.2f}% · hold {hold_pnl:+.2f}%)"
                + (f" · {bench.get('benchmark_note', '')}" if bench.get("benchmark_note") else "")
            ),
        )
    _check(
        checks,
        cid="drawdown",
        label=f"Просадка ≤ {config.LIVE_MAX_DRAWDOWN_PCT}%",
        ok=_portfolio_drawdown_ok(sessions, config.LIVE_MAX_DRAWDOWN_PCT),
        detail="Считается от пика портфеля по рынкам",
    )

    required = [c for c in checks if c.get("required", True)]
    passed = sum(1 for c in required if c["ok"])
    score = round(passed / len(required) * 100) if required else 0
    ready = all(c["ok"] for c in required) if config.LIVE_REQUIRE_READINESS else True

    return {
        "version": config.APP_VERSION,
        "ready_for_live": ready,
        "score_pct": score,
        "passed": passed,
        "total_checks": len(required),
        "checks": checks,
        "stats": {
            "paper_days": round(paper_days, 1),
            "testnet_days": round(testnet_days, 1),
            "trade_count": trade_count,
            "pnl_pct": round(pnl_pct, 2),
            "vs_hold_pct": round(vs_hold, 2),
            "live_pnl_pct": round(live_pnl, 2),
            "hold_pnl_pct": round(hold_pnl, 2),
            "portfolio_usd": round(total, 2),
            "current_mode": mode_mgr.mode,
        },
        "limits_if_live": {
            "max_order_usd": config.LIVE_MAX_ORDER_USD,
            "max_daily_loss_pct": config.LIVE_MAX_DAILY_LOSS_PCT,
            "max_position_pct": config.LIVE_MAX_POSITION_PCT,
        },
        "week_plan": _week_plan(paper_days, testnet_days, trade_count, mode_mgr.mode),
        "bypass": config.LIVE_BYPASS_READINESS,
        "note": (
            "Все проверки пройдены — можно включать Live с малыми лимитами"
            if ready
            else "Доработай пункты ниже перед реальными деньгами"
        ),
    }


def _portfolio_drawdown_ok(sessions: dict, max_dd_pct: float) -> bool:
    peak = 0.0
    for s in sessions.values():
        price = s.feed.price or s.demo_price
        snap = s.engine.snapshot(price)
        start = s.engine.start_balance
        pv = snap["portfolio_value"]
        peak = max(peak, start, pv)
    if peak <= 0:
        return True
    total = sum(
        s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"]
        for s in sessions.values()
    )
    dd = (peak - total) / peak * 100 if peak else 0
    return dd <= max_dd_pct


def _week_plan(paper_days: float, testnet_days: float, trades: int, mode: str) -> list[dict[str, str]]:
    """7-day path paper → testnet → live."""
    plan = [
        {
            "day": "1–2",
            "task": "Paper + v36",
            "action": "git pull → start.bat → Ctrl+Shift+R. Смотри vs Hold и сделки.",
            "done": paper_days >= 1,
        },
        {
            "day": "3–4",
            "task": "Testnet мелкими суммами",
            "action": "🧪 Testnet + EXCHANGE_SYNC_FROM_PAPER=true. Лимит $25/ордер.",
            "done": mode == "testnet" and testnet_days >= 1,
        },
        {
            "day": "5–6",
            "task": "Стабильность",
            "action": f"≥{config.LIVE_MIN_TRADES} сделок, P&L не в глубоком минусе, Profit Focus без массовых пауз.",
            "done": trades >= config.LIVE_MIN_TRADES and testnet_days >= 3,
        },
        {
            "day": "7",
            "task": "Live (если readiness 100%)",
            "action": "EXCHANGE_TESTNET=false, новые ключи Live, начни с $10–25/ордер.",
            "done": False,
        },
    ]
    return plan
