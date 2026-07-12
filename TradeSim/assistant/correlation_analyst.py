"""Agent 8: compares markets — leaders, laggards and move together."""

from __future__ import annotations

from typing import Any


class CorrelationAnalystAgent:
    """Finds which coins move in sync and which diverge from the pack."""

    name = "Корреляция"
    role = "correlation_analyst"
    emoji = "🔗"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        if len(contexts) < 2:
            return self._empty()

        pairs: list[str] = []
        leaders: list[str] = []
        laggards: list[str] = []

        ranked = sorted(
            contexts,
            key=lambda c: c["portfolio"].get("vs_hold_pct", 0),
            reverse=True,
        )
        best = ranked[0]
        worst = ranked[-1]
        spread = best["portfolio"].get("vs_hold_pct", 0) - worst["portfolio"].get("vs_hold_pct", 0)

        for ctx in ranked[:2]:
            vh = ctx["portfolio"].get("vs_hold_pct", 0)
            leaders.append(f"{ctx['label']}: {vh:+.2f}% vs hold")
        for ctx in ranked[-2:]:
            vh = ctx["portfolio"].get("vs_hold_pct", 0)
            laggards.append(f"{ctx['label']}: {vh:+.2f}% vs hold")

        # Simple co-movement: same sign of short momentum
        for i, a in enumerate(contexts):
            for b in contexts[i + 1:]:
                ma = self._momentum(a)
                mb = self._momentum(b)
                if ma is None or mb is None:
                    continue
                if ma * mb > 0 and abs(ma) > 0.5 and abs(mb) > 0.5:
                    pairs.append(f"{a['label']} ↔ {b['label']} (движутся вместе)")
                elif ma * mb < 0 and abs(ma) > 1 and abs(mb) > 1:
                    pairs.append(f"{a['label']} ≠ {b['label']} (расхождение)")

        recommendation = "hold"
        action = "Корзина сбалансирована — диверсификация работает."
        if spread >= 4:
            recommendation = "observe"
            action = (
                f"Разброс vs hold {spread:.1f} п.п. — лидер {best['label']}, "
                f"отстаёт {worst['label']}. Не перекладывать всё в один актив."
            )
        elif len(pairs) >= 3:
            recommendation = "reduce_aggression"
            action = "Много синхронных движений — при общем падении риск коррелирован."

        summary = (
            f"Связи рынков: лидер {best['label']}, аутсайдер {worst['label']}. "
            f"Разброс {spread:.1f} п.п. · пар в движении: {len(pairs)}."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "pairs": pairs[:5],
            "leaders": leaders,
            "laggards": laggards,
            "spread_pp": round(spread, 2),
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.6 if pairs or spread >= 3 else 0.45,
        }

    def _momentum(self, ctx: dict) -> float | None:
        candles = ctx.get("candles") or []
        if len(candles) < 4:
            return None
        closes = [c.close for c in candles[-4:]]
        if not closes[0]:
            return None
        return (closes[-1] - closes[0]) / closes[0] * 100

    def _empty(self) -> dict[str, Any]:
        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": "Недостаточно рынков для корреляционного анализа.",
            "pairs": [],
            "leaders": [],
            "laggards": [],
            "recommendation": "hold",
            "action_for_brain": "Ждём данных.",
            "confidence": 0.3,
        }
