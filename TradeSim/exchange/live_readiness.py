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


async def _portfolio_drawdown_ok(
    sessions: dict,
    logger_db,
    max_dd_pct: float,
    *,
    portfolio_peak: float = 0.0,
) -> tuple[bool, float, float]:
    """Drawdown from portfolio peak (equity curve + in-memory peak), not single-market max."""
    total = sum(
        s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"]
        for s in sessions.values()
    )
    start = sum(s.engine.start_balance for s in sessions.values())
    peak = max(portfolio_peak, start, total)

    try:
        curve = await logger_db.equity_curve(hours=168)
        if curve:
            peak = max(peak, max(float(p.get("value", 0)) for p in curve))
    except Exception:
        pass

    dd = (peak - total) / peak * 100 if peak > 0 else 0.0
    return dd <= max_dd_pct, round(dd, 2), round(peak, 2)


async def assess_live_readiness(
    sessions: dict,
    exchange,
    logger_db,
    mode_mgr,
    *,
    benchmark: dict[str, Any],
    verify: dict[str, Any] | None = None,
    portfolio_peak: float = 0.0,
) -> dict[str, Any]:
    """Score readiness for Binance LIVE — conservative defaults for first real money."""
    checks: list[dict[str, Any]] = []
    total = sum(
        s.engine.snapshot(s.feed.price or s.demo_price)["portfolio_value"]
        for s in sessions.values()
    )
    start = sum(s.engine.start_balance for s in sessions.values())
    pnl_pct = ((total - start) / start * 100) if start else 0.0

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
    on_testnet_phase = mode_mgr.mode in ("paper", "testnet") or exchange.testnet
    _check(
        checks,
        cid="testnet_env",
        label="EXCHANGE_TESTNET=true в .env",
        ok=exchange.enabled and exchange.testnet,
        detail=(
            "Testnet ключи ✓ — api.testnet.binance.vision"
            if exchange.testnet
            else "Для Testnet: EXCHANGE_TESTNET=true в .env и перезапуск"
        ),
        required=mode_mgr.mode == "testnet",
    )
    _check(
        checks,
        cid="live_env",
        label="Live API (EXCHANGE_TESTNET=false — только перед Live)",
        ok=exchange.enabled and not exchange.testnet,
        detail=(
            "Сейчас testnet ✓ — переключишь на Live в день 7"
            if exchange.testnet
            else "Live требует реальные ключи api.binance.com, не testnet"
        ),
        required=not on_testnet_phase,
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
        label=f"Опыт Testnet ≥ {config.LIVE_MIN_DAYS_TESTNET} дн.",
        ok=testnet_days >= config.LIVE_MIN_DAYS_TESTNET,
        detail=(
            f"Testnet {testnet_days:.1f} дн. — переключись на 🧪 Testnet и торгуй"
            if testnet_days < config.LIVE_MIN_DAYS_TESTNET
            else f"Testnet {testnet_days:.1f} дн. ✓ · сейчас режим {mode_mgr.mode}"
        ),
        required=True,
    )
    if mode_mgr.mode != "testnet" and testnet_days < config.LIVE_MIN_DAYS_TESTNET:
        _check(
            checks,
            cid="testnet_active",
            label="Сейчас режим Testnet (перед Live)",
            ok=False,
            detail=f"Режим: {mode_mgr.mode} — для Live переключись на Testnet",
            required=False,
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

    dd_ok, dd_pct, peak_val = await _portfolio_drawdown_ok(
        sessions, logger_db, config.LIVE_MAX_DRAWDOWN_PCT, portfolio_peak=portfolio_peak,
    )
    _check(
        checks,
        cid="drawdown",
        label=f"Просадка ≤ {config.LIVE_MAX_DRAWDOWN_PCT}%",
        ok=dd_ok,
        detail=f"Просадка портфеля {dd_pct:.1f}% от пика ${peak_val:,.0f}",
    )

    stability_24h = await logger_db.stability_summary(hours=24)
    sync_rate_24h = float(stability_24h.get("success_rate_pct", 100))
    sync_failures_24h = int(stability_24h.get("sync_failures", 0))
    ex_orders_24h = int(stability_24h.get("exchange_orders", 0))
    _check(
        checks,
        cid="sync_stability",
        label="Sync стабильность ≥ 85% (24ч)",
        ok=sync_rate_24h >= 85 or mode_mgr.mode == "paper",
        detail=(
            f"{sync_rate_24h:.0f}% · сбоев {sync_failures_24h} · ордеров {ex_orders_24h} · "
            "🧹 Сброс sync / Micro Testnet → Smoke test"
        ),
        required=mode_mgr.mode in ("testnet", "live"),
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
            "portfolio_value": round(total, 2),
            "drawdown_pct": dd_pct,
        },
        "week_plan": _week_plan(paper_days, testnet_days, trade_count, mode_mgr.mode),
        "summary": (
            "Все проверки пройдены — можно пробовать Live Micro ($10–15), не полный депозит"
            if ready
            else "Доработай пункты ниже перед реальными деньгами"
        ),
        "limits_if_live": {
            "max_order_usd": config.LIVE_MAX_ORDER_USD,
            "max_daily_loss_pct": config.LIVE_MAX_DAILY_LOSS_PCT,
            "max_position_pct": config.LIVE_MAX_POSITION_PCT * 100,
        },
    }


def _week_plan(paper_days: float, testnet_days: float, trades: int, mode: str) -> list[dict[str, str]]:
    """7-day path paper → testnet → live."""
    plan = [
        {
            "day": "1–2",
            "task": "Paper + Paper Learn",
            "action": "git pull → start.bat → Ctrl+Shift+R. Режим 📄 Paper, кнопка 📚 Paper учёба.",
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
