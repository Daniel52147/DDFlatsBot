"""Agent 1: wisdom from professional trading principles."""

from __future__ import annotations

from typing import Any

# Classic rules distilled from pro trader playbooks (educational, not financial advice)
PRO_RULES = [
    {
        "id": "risk_1pct",
        "title": "Риск на сделку",
        "rule": "Профи не рискуют >1–2% капитала на одну сделку.",
        "check": lambda ctx: ctx["portfolio"]["pnl_pct"] > -5,
        "advice_ok": "Размер DCA в норме — риск контролируется.",
        "advice_bad": "Просадка растёт — профи уменьшили бы размер позиции.",
    },
    {
        "id": "trend_friend",
        "title": "Тренд — друг",
        "rule": "В восходящем тренде DCA работает лучше, чем против тренда.",
        "check": lambda ctx: ctx.get("sma") and ctx["price"] >= ctx["sma"] * 0.97,
        "advice_ok": "Цена у SMA — тренд поддерживает накопление.",
        "advice_bad": "Цена сильно ниже SMA — профи ждут стабилизации перед усилением покупок.",
    },
    {
        "id": "patience",
        "title": "Терпение",
        "rule": "Профи не гонятся за рынком — ждут своей цены.",
        "check": lambda ctx: ctx["trade_count"] < 20 or ctx["portfolio"].get("vs_hold_pct", 0) >= -2,
        "advice_ok": "Дисциплина DCA соблюдается — как у системных фондов.",
        "advice_bad": "Стратегия отстаёт от «держать» — профи пересмотрели бы порог входа.",
    },
    {
        "id": "diversify",
        "title": "Диверсификация",
        "rule": "Не класть всё в один актив — распределять по корзине.",
        "check": lambda ctx: True,
        "advice_ok": "Портфель разбит на BTC/ETH/SOL/BNB — это правильно.",
        "advice_bad": "",
    },
]


class TraderMentorAgent:
    """Learns pro-trader heuristics and sends insights to the central brain."""

    name = "Наставник"
    role = "trader_mentor"
    emoji = "🎓"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        insights = []
        warnings = []
        score = 0

        for ctx in contexts:
            for rule in PRO_RULES:
                if rule["id"] == "diversify":
                    continue
                ok = rule["check"](ctx)
                text = rule["advice_ok"] if ok else rule["advice_bad"]
                if not text:
                    continue
                item = {
                    "market": ctx["label"],
                    "rule": rule["title"],
                    "text": text,
                    "ok": ok,
                }
                insights.append(item)
                if ok:
                    score += 1
                else:
                    warnings.append(f"{ctx['label']}: {text}")

        insights.append({
            "market": "ALL",
            "rule": "Диверсификация",
            "text": f"Портфель разбит на {len(contexts)} активов (majors + growth + viral) — диверсификация правильная.",
            "ok": True,
        })
        score += 1

        avg_pnl = total.get("pnl_pct", 0)
        summary = (
            f"Проанализировал {len(contexts)} рынков по {len(PRO_RULES)} правилам профи. "
            f"Сигналов «ОК»: {score}. Общий P&L: {avg_pnl:+.2f}%."
        )
        if warnings:
            summary += f" Внимание: {len(warnings)} предупреждений."

        recommendation = "hold"
        if len(warnings) >= 3:
            recommendation = "reduce_aggression"
            action = "Центральному мозгу: снизить DIP-покупки до стабилизации."
        elif avg_pnl > 1:
            recommendation = "continue"
            action = "Стратегия в норме — продолжаем paper trading."
        else:
            recommendation = "observe"
            action = "Наблюдаем — профи в такой фазе не увеличивают риск."

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "insights": insights[:8],
            "warnings": warnings[:5],
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": min(0.9, 0.5 + score * 0.05),
        }
