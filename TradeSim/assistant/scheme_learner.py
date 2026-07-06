"""Agent 3: discovers and tests new micro-schemes from paper trading data."""

from __future__ import annotations

from typing import Any


class SchemeLearnerAgent:
    """Tests new parameter combos and proposes schemes to the central brain."""

    name = "Исследователь"
    role = "scheme_learner"
    emoji = "🧪"

    SCHEMES = [
        {
            "id": "deep_dip",
            "name": "Глубокий DIP",
            "desc": "Покупать только при просадке >5% от SMA",
            "condition": lambda ctx: ctx.get("sma") and ctx["price"] < ctx["sma"] * 0.95,
        },
        {
            "id": "momentum",
            "name": "Моментум DCA",
            "desc": "DCA только когда цена выше SMA (тренд вверх)",
            "condition": lambda ctx: ctx.get("sma") and ctx["price"] > ctx["sma"],
        },
        {
            "id": "quiet_market",
            "name": "Тихий рынок",
            "desc": "Увеличить DCA когда волатильность низкая (цена ~SMA)",
            "condition": lambda ctx: ctx.get("sma") and abs(ctx["price"] - ctx["sma"]) / ctx["sma"] < 0.01,
        },
    ]

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        proposals = []
        for scheme in self.SCHEMES:
            matches = [ctx["label"] for ctx in contexts if scheme["condition"](ctx)]
            if matches:
                proposals.append({
                    "scheme": scheme["name"],
                    "id": scheme["id"],
                    "desc": scheme["desc"],
                    "markets": matches,
                    "status": "active_signal",
                })

        # Learn from performance: which market beats hold?
        performers = sorted(
            contexts,
            key=lambda c: c["portfolio"].get("vs_hold_pct", -999),
            reverse=True,
        )
        best = performers[0] if performers else None
        worst = performers[-1] if performers else None

        learned = []
        if best and best["portfolio"].get("vs_hold_pct", 0) > 0:
            learned.append(
                f"{best['label']} опережает «держать» на {best['portfolio']['vs_hold_pct']:+.2f}% "
                f"— схема DCA+DIP здесь работает."
            )
        if worst and worst["portfolio"].get("vs_hold_pct", 0) < -1:
            learned.append(
                f"{worst['label']} отстаёт на {abs(worst['portfolio']['vs_hold_pct']):.2f}% "
                f"— тестируем более глубокий порог DIP."
            )

        total_trades = sum(c["trade_count"] for c in contexts)
        recommendation = "experiment"
        if total_trades < 5:
            action = "Мало данных — копим сделки для теста новых схем."
            recommendation = "collect_data"
        elif proposals:
            action = f"Активны схемы: {', '.join(p['scheme'] for p in proposals)}. Передаю центральному мозгу."
        else:
            action = "Явных сигналов нет — держим базовую стратегию."
            recommendation = "hold"

        summary = (
            f"Протестировал {len(self.SCHEMES)} схем на {len(contexts)} рынках. "
            f"Активных сигналов: {len(proposals)}. Сделок для обучения: {total_trades}."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "proposals": proposals,
            "learned": learned,
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": min(0.85, 0.3 + total_trades * 0.05),
        }
