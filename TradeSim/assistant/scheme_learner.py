"""Agent 3: discovers schemes and learns from live trade stats."""

from __future__ import annotations

from typing import Any


class SchemeLearnerAgent:
    """Tests schemes and recommends experiments from real paper-trading data."""

    name = "Исследователь"
    role = "scheme_learner"
    emoji = "🧪"

    SCHEMES = [
        {
            "id": "meme_volatility",
            "name": "Мемкоин-скачок",
            "desc": "SPIKE при просадке >10% на волатильных",
            "condition": lambda ctx: (
                ctx.get("volatile")
                and ctx.get("sma")
                and ctx["price"] < ctx["sma"] * 0.9
            ),
        },
        {
            "id": "deep_dip",
            "name": "Глубокий DIP",
            "desc": "Покупка при просадке >5% от SMA",
            "condition": lambda ctx: ctx.get("sma") and ctx["price"] < ctx["sma"] * 0.95,
        },
        {
            "id": "momentum",
            "name": "Моментум",
            "desc": "Цена выше SMA — тренд вверх, фиксируем TP",
            "condition": lambda ctx: ctx.get("sma") and ctx["price"] > ctx["sma"] * 1.03,
        },
        {
            "id": "quiet_market",
            "name": "Тихий рынок",
            "desc": "Низкая волатильность — умеренный DCA",
            "condition": lambda ctx: (
                ctx.get("sma")
                and abs(ctx["price"] - ctx["sma"]) / ctx["sma"] < 0.01
            ),
        },
        {
            "id": "spike_working",
            "name": "SPIKE работает",
            "desc": "Много SPIKE-сделок и vs hold в плюсе",
            "condition": lambda ctx: (
                ctx.get("trade_stats", {}).get("spike", 0) >= 2
                and ctx["portfolio"].get("vs_hold_pct", 0) >= 0
            ),
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

        performers = sorted(
            contexts,
            key=lambda c: c["portfolio"].get("vs_hold_pct", -999),
            reverse=True,
        )
        best = performers[0] if performers else None
        worst = performers[-1] if performers else None

        learned = []
        if best and best["portfolio"].get("vs_hold_pct", 0) > 0:
            st = best.get("trade_stats", {})
            hint = ""
            if st.get("spike", 0) >= 2:
                hint = " (SPIKE-сделки помогают)"
            elif st.get("tp", 0) >= 1:
                hint = " (take-profit сработал)"
            learned.append(
                f"{best['label']} +{best['portfolio']['vs_hold_pct']:.2f}% vs hold{hint}."
            )
        if worst and worst["portfolio"].get("vs_hold_pct", 0) < -0.5:
            learned.append(
                f"{worst['label']} отстаёт {worst['portfolio']['vs_hold_pct']:.2f}% "
                f"— ускоренная автонастройка уже идёт."
            )

        total_trades = sum(c["trade_count"] for c in contexts)
        min_data = 2 if any(c.get("volatile") for c in contexts) else 3

        recommendation = "experiment"
        if total_trades < min_data:
            action = f"Копим данные ({total_trades}/{min_data} сделок) — быстрый режим обучения."
            recommendation = "collect_data"
        elif proposals:
            action = (
                f"Схемы: {', '.join(p['scheme'] for p in proposals)}. "
                "Мозг применяет микро-настройки каждые 45 сек."
            )
        else:
            action = "Паттернов нет — анализируем каждую сделку."
            recommendation = "hold"

        summary = (
            f"Протестировал {len(self.SCHEMES)} схем. Сигналов: {len(proposals)}. "
            f"Сделок: {total_trades}. Режим: быстрое обучение."
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
            "confidence": min(0.9, 0.4 + total_trades * 0.08),
        }
