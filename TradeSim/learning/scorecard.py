"""Paper Learn scorecard — compare live stats to recommended benchmarks."""

from __future__ import annotations

from typing import Any

import config
from learning.paper_learn_mode import is_paper_learn_mode

Grade = str  # bad | warn | ok | good

GRADE_LABELS = {
    "bad": "Плохо",
    "warn": "Слабо",
    "ok": "Нормально",
    "good": "Хорошо",
}


def _grade_trades(count: int) -> Grade:
    if count < 10:
        return "bad"
    if count >= 100:
        return "good"
    if count >= 30:
        return "ok"
    return "warn"


def _grade_pnl(pnl_pct: float) -> Grade:
    if pnl_pct < -5:
        return "bad"
    if pnl_pct > 3:
        return "good"
    if pnl_pct >= -2:
        return "ok"
    return "warn"


def _grade_vs_hold(vs_hold_pct: float) -> Grade:
    if vs_hold_pct < -3:
        return "bad"
    if vs_hold_pct > 2:
        return "good"
    if vs_hold_pct >= 0:
        return "ok"
    return "warn"


def _grade_drawdown(drawdown_pct: float) -> Grade:
    if drawdown_pct > 12:
        return "bad"
    if drawdown_pct < 5:
        return "good"
    if drawdown_pct <= 8:
        return "ok"
    return "warn"


def _grade_readiness(score_pct: float) -> Grade:
    if score_pct < 50:
        return "bad"
    if score_pct >= 100:
        return "good"
    if score_pct >= 60:
        return "ok"
    return "warn"


def _row(
    metric_id: str,
    label: str,
    value: float | int,
    display: str,
    grade: Grade,
    hint: str,
    *,
    priority: bool = False,
) -> dict[str, Any]:
    return {
        "id": metric_id,
        "label": label,
        "value": value,
        "display": display,
        "grade": grade,
        "grade_label": GRADE_LABELS[grade],
        "hint": hint,
        "priority": priority,
    }


def build_scorecard(
    *,
    total: dict[str, Any],
    trade_count: int,
    readiness: dict[str, Any] | None = None,
    trading_mode: str = "paper",
) -> dict[str, Any]:
    """Build traffic-light scorecard for Paper Learn phase."""
    pnl = float(total.get("pnl_pct", 0))
    vs_hold = float(total.get("vs_hold_pct", 0))
    drawdown = float(total.get("drawdown_pct", 0))
    readiness_score = float((readiness or {}).get("score_pct", 0))
    paper_learn = is_paper_learn_mode()

    metrics = [
        _row(
            "trades",
            "Сделок всего",
            trade_count,
            str(trade_count),
            _grade_trades(trade_count),
            "Paper Learn: цель 30+ для тюнинга, 100+ — богатый опыт в БД",
            priority=paper_learn,
        ),
        _row(
            "pnl",
            "P&L портфеля",
            pnl,
            f"{pnl:+.2f}%",
            _grade_pnl(pnl),
            "Главная метрика на Testnet/Live; на Paper Learn вторична",
            priority=not paper_learn,
        ),
        _row(
            "vs_hold",
            "vs Hold",
            vs_hold,
            f"{vs_hold:+.2f}%",
            _grade_vs_hold(vs_hold),
            "Обгоняешь buy-and-hold с момента старта сессии",
            priority=True,
        ),
        _row(
            "drawdown",
            "Просадка",
            drawdown,
            f"{drawdown:.1f}%",
            _grade_drawdown(drawdown),
            "От пика портфеля; Live gate ≤ 8%",
        ),
        _row(
            "readiness",
            "Live readiness",
            readiness_score,
            f"{readiness_score:.0f}%",
            _grade_readiness(readiness_score),
            "100% + Testnet перед реальными деньгами",
        ),
    ]

    grades = [m["grade"] for m in metrics]
    if "bad" in grades:
        overall = "bad"
        summary = "Есть красные зоны — сначала Paper Learn и смотри P&L + vs Hold."
    elif grades.count("good") >= 3:
        overall = "good"
        summary = "Сильные показатели — можно планировать Testnet (🚀 Неделя Testnet)."
    elif "warn" in grades and paper_learn:
        overall = "ok"
        summary = "Учёба идёт — на Paper много сделок важнее красивого P&L."
    else:
        overall = "ok"
        summary = "В пределах нормы — продолжай Paper, копи сделки и смотри vs Hold."

    next_steps: list[str] = []
    if trading_mode == "testnet":
        next_steps.append("Testnet: консервативный режим — меньше DCA, Profit Focus паузит аутсайдеров")
    elif trading_mode == "paper":
        next_steps.append("Оставайся в 📄 Paper + 📚 Paper учёба ещё 1–2 дня")
    if trade_count < 30:
        next_steps.append(f"Нужно ещё ~{max(0, 30 - trade_count)} сделок до порога «нормально»")
    if readiness_score < 100 and trading_mode == "paper":
        next_steps.append("Потом: 🚀 Неделя Testnet (мелкие ордера)")
    if drawdown > 8:
        next_steps.append("Просадка высокая — смотри мемы (PEPE, WIF) и Profit Focus")
    if vs_hold < 0:
        next_steps.append("vs Hold отрицательный — дождись тюнинга (каждые 2 сделки на Paper)")
    if not next_steps:
        next_steps.append("Держи режим Testnet 3+ дня и следи за readiness 100%")

    return {
        "version": config.APP_VERSION,
        "phase": "paper_learn" if paper_learn else trading_mode,
        "paper_learn": paper_learn,
        "overall_grade": overall,
        "overall_label": GRADE_LABELS.get(overall, overall),
        "summary": summary,
        "metrics": metrics,
        "benchmarks": {
            "trades": {"bad": "<10", "ok": "30–100", "good": "100+"},
            "pnl": {"bad": "<−5%", "ok": "−2%…+3%", "good": ">+3%"},
            "vs_hold": {"bad": "<−3%", "ok": "0%…+2%", "good": ">+2%"},
            "drawdown": {"bad": ">12%", "ok": "5–8%", "good": "<5%"},
            "readiness": {"bad": "<50%", "ok": "60–80%", "good": "100%"},
        },
        "next_steps": next_steps[:4],
        "total_value": total.get("total_value"),
        "trading_mode": trading_mode,
    }
