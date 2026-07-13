"""Agent 11: suggests capital allocation across markets."""

from __future__ import annotations

from typing import Any

import config


class PortfolioAllocatorAgent:
    name = "Аллокатор"
    role = "portfolio_allocator"
    emoji = "⚖️"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        per_market = config.BALANCE_PER_MARKET
        suggestions = []
        overweight = []
        underused = []

        ranked = sorted(
            contexts,
            key=lambda c: c["portfolio"].get("vs_hold_pct", 0),
            reverse=True,
        )

        for ctx in contexts:
            pv = ctx["portfolio"].get("portfolio_value", per_market)
            coin_value = ctx["portfolio"].get("base", 0) * ctx.get("price", 0)
            alloc_pct = coin_value / max(pv, 1) * 100
            label = ctx["label"]
            vs = ctx["portfolio"].get("vs_hold_pct", 0)

            if alloc_pct > 80 and vs < 0:
                overweight.append(f"{label}: {alloc_pct:.0f}% в монете, отстаёт от hold")
            elif alloc_pct < 30 and vs > 1:
                underused.append(f"{label}: мало в монете ({alloc_pct:.0f}%), но стратегия лидирует")

        best = ranked[0] if ranked else None
        worst = ranked[-1] if ranked else None
        if best and worst and best["label"] != worst["label"]:
            spread = best["portfolio"].get("vs_hold_pct", 0) - worst["portfolio"].get("vs_hold_pct", 0)
            if spread >= 3:
                suggestions.append(
                    f"Лидер {best['label']} (+{best['portfolio'].get('vs_hold_pct', 0):.1f}% vs hold) "
                    f"опережает {worst['label']} на {spread:.1f} п.п."
                )

        majors = [c for c in contexts if not c.get("volatile")]
        memes = [c for c in contexts if c.get("volatile")]
        if memes:
            meme_pnl = sum(c["portfolio"].get("pnl_pct", 0) for c in memes) / len(memes)
            major_pnl = sum(c["portfolio"].get("pnl_pct", 0) for c in majors) / max(len(majors), 1)
            if meme_pnl > major_pnl + 2:
                suggestions.append("Мемкоины сильнее majors — не перегружать волатильную корзину")
            elif major_pnl > meme_pnl + 2:
                suggestions.append("Majors стабильнее — мемкоины держать в рамках лимитов")

        recommendation = "hold"
        action = "Аллокация сбалансирована — по ~$1,667 на рынок."
        if overweight:
            recommendation = "reduce_aggression"
            action = f"Перегруз: {', '.join(overweight[:2])}. Не добавлять DIP на просадочных."
        elif underused and best:
            recommendation = "continue"
            action = f"Есть запас кэша на {best['label']} — DCA/DIP по плану."

        summary = (
            f"Аллокация {len(contexts)} рынков по ${per_market:,.0f}. "
            f"Перегружены: {len(overweight)}, недоиспользованы: {len(underused)}."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "suggestions": suggestions[:4],
            "overweight": overweight[:3],
            "underused": underused[:3],
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.6 if suggestions or overweight else 0.45,
        }
