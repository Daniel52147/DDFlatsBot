"""Phased path to real trading — honesty about friction, stability drills."""

from __future__ import annotations

import time
from typing import Any

import config
from learning.live_micro_mode import is_live_micro_active
from learning.paper_learn_mode import is_paper_learn_mode


REALISM_WARNINGS: list[dict[str, str]] = [
    {
        "id": "fees",
        "title": "Комиссии",
        "text": "На мелких ордерах $5–15 комиссия съедает 0.1–0.3% каждый раз. "
        "50 сделок/день = минус даже при «правильном» направлении.",
    },
    {
        "id": "sync",
        "title": "Paper ≠ биржа",
        "text": "Ордер на бирже может пройти, а paper sync — нет. Смотри Reconcile и панель стабильности.",
    },
    {
        "id": "reject",
        "title": "Отклонённые ордера",
        "text": "Binance режет по min notional, LOT_SIZE, недостатку USDT, rate limit, geo-block (451).",
    },
    {
        "id": "latency",
        "title": "Задержки и обрывы",
        "text": "Wi‑Fi, VPN, перезапуск ПК — бот пропускает тики. На Live нужен 24/7 хост или Render.",
    },
    {
        "id": "slippage",
        "title": "Проскальзывание",
        "text": "Paper симулирует slippage, но на Live рынок может исполнить хуже — особенно на мемкоинах.",
    },
    {
        "id": "emotion",
        "title": "Реальные деньги",
        "text": "−3% на $10 000 ощущается иначе, чем на paper. Лимиты и Live Micro существуют именно для этого.",
    },
]


def _days_since(ts: float) -> float:
    if not ts or ts <= 0:
        return 0.0
    return max(0.0, (time.time() - ts) / 86400)


async def build_live_prep(
    sessions: dict,
    exchange,
    logger_db,
    mode_mgr,
    *,
    readiness: dict[str, Any],
    benchmark: dict[str, Any],
    verify: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Full preparation dashboard: phases, stability, realism, next action."""
    meta = mode_mgr.milestones()
    paper_days = float(readiness.get("stats", {}).get("paper_days", 0))
    testnet_days = float(readiness.get("stats", {}).get("testnet_days", 0))
    trade_count = int(readiness.get("stats", {}).get("trade_count", 0))
    stability = await logger_db.stability_summary(hours=168)
    fee = await logger_db.fee_summary(hours=168)
    hours = 168

    verify = verify or {}
    if exchange.enabled and not verify:
        verify = await exchange.verify_connection()

    sync_rate = stability.get("success_rate_pct", 100.0)
    exchange_orders = stability.get("exchange_orders", 0)
    sync_failures = stability.get("sync_failures", 0)

    phases: list[dict[str, Any]] = [
        {
            "id": "paper",
            "title": "1. Paper — учёба",
            "done": paper_days >= config.LIVE_MIN_DAYS_PAPER and trade_count >= 20,
            "current": mode_mgr.mode == "paper",
            "detail": f"{paper_days:.1f} дн. · {trade_count} сделок · много сделок OK для обучения",
            "action": "📚 Paper учёба · смотри vs Hold и просадку",
        },
        {
            "id": "testnet_discipline",
            "title": "2. Testnet — дисциплина",
            "done": testnet_days >= 1 and mode_mgr.mode in ("testnet", "live"),
            "current": mode_mgr.mode == "testnet",
            "detail": "Conservative: DCA ≥6ч, мелкие ордера, EXCHANGE_SYNC_FROM_PAPER",
            "action": "🚀 Неделя Testnet · депозит $10–50 на faucet",
        },
        {
            "id": "testnet_stability",
            "title": "3. Testnet — стабильность (не P&L!)",
            "done": (
                testnet_days >= config.LIVE_MIN_DAYS_TESTNET
                and exchange_orders >= 5
                and sync_rate >= 85
                and bool(verify.get("ok"))
            ),
            "current": mode_mgr.mode == "testnet" and testnet_days >= 1,
            "detail": (
                f"Ордеров на бирже: {exchange_orders} · sync OK {sync_rate:.0f}% · "
                f"сбоев sync: {sync_failures}"
            ),
            "action": "Цель: ордера исполняются, verify OK, reconcile без красных Δ",
        },
        {
            "id": "live_micro",
            "title": "4. Live Micro — $10–15",
            "done": is_live_micro_active() and mode_mgr.mode == "live",
            "current": is_live_micro_active(),
            "detail": (
                f"Ордер ≤${config.LIVE_MICRO_ORDER_USD} · DCA ≥{config.LIVE_MICRO_DCA_HOURS}ч · "
                f"~{config.LIVE_MICRO_MAX_TRADES_PER_DAY} сделки/день/рынок"
            ),
            "action": "Кнопка «Live Micro» — редкие сделки, комиссии не убивают депозит",
        },
        {
            "id": "live_full",
            "title": "5. Live полный",
            "done": mode_mgr.mode == "live" and readiness.get("ready_for_live") and not is_live_micro_active(),
            "current": mode_mgr.mode == "live" and not is_live_micro_active(),
            "detail": f"Readiness {readiness.get('score_pct', 0)}% · лимит ${config.LIVE_MAX_ORDER_USD}/ордер",
            "action": "Только после 7+ дней testnet и стабильности ≥85%",
        },
    ]

    completed = sum(1 for p in phases if p["done"])
    current_phase = next((p for p in phases if p["current"]), phases[0])
    next_phase = next((p for p in phases if not p["done"]), phases[-1])

    fee_per_day = float(fee.get("total_fees", 0)) / max(hours / 24, 1)
    trades_per_day = float(fee.get("trade_count", 0)) / max(hours / 24, 1)
    fee_warning = trades_per_day > 30 and fee_per_day > 5

    recommended_env = _recommended_env(mode_mgr.mode, sync_rate, is_live_micro_active())

    return {
        "version": config.APP_VERSION,
        "phase_progress": f"{completed}/{len(phases)}",
        "phases": phases,
        "current_phase": current_phase,
        "next_phase": next_phase,
        "realism_warnings": REALISM_WARNINGS,
        "stability": stability,
        "fees_7d": fee,
        "fee_warning": fee_warning,
        "fee_hint": (
            f"⚠ {trades_per_day:.0f} сделок/день · комиссии ${fee_per_day:.2f}/день — "
            "на Live сократи до 2–5 сделок/день"
            if fee_warning
            else "Комиссии в норме для текущего режима"
        ),
        "readiness": {
            "score_pct": readiness.get("score_pct", 0),
            "ready_for_live": readiness.get("ready_for_live", False),
        },
        "verify": verify,
        "recommended_env": recommended_env,
        "summary": _summary(mode_mgr.mode, completed, len(phases), sync_rate, readiness),
    }


def _recommended_env(mode: str, sync_rate: float, micro: bool) -> list[str]:
    lines = [
        "TRADING_MODE_DEFAULT=paper",
        "PAPER_LEARN_ENABLED=true  # только на Paper",
        "EXCHANGE_SYNC_FROM_PAPER=true  # на Testnet/Live",
    ]
    if mode in ("testnet", "live"):
        lines.extend([
            "PAPER_LEARN_ENABLED=false",
            "TRADE_MODE=normal  # не active",
            f"LIVE_MAX_ORDER_USD={config.LIVE_MICRO_ORDER_USD if micro else config.LIVE_MAX_ORDER_USD}",
        ])
    if sync_rate < 85:
        lines.append("# Сначала почини sync — не переходи на Live")
    if micro:
        lines.append("LIVE_MICRO_MODE=true  # через кнопку Live Micro")
    return lines


def _summary(mode: str, done: int, total: int, sync_rate: float, readiness: dict) -> str:
    if mode == "paper":
        return f"Фаза {done}/{total}: учись на Paper. Реальный трейдинг — это комиссии, отказы API и рассинхрон."
    if mode == "testnet" and sync_rate < 85:
        return f"Testnet: проверяй стабильность (sync {sync_rate:.0f}%). Доходность сейчас вторична."
    if readiness.get("ready_for_live"):
        return "Можно пробовать Live Micro ($10) — не крупный депозит, цель: техника, не прибыль."
    return f"Путь к Live: {done}/{total} фаз. Не спеши — paper/testnet дешевле ошибок."
