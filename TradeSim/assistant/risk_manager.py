"""Agent 5: portfolio risk and drawdown guard."""

from __future__ import annotations

import config
from typing import Any


class RiskManagerAgent:
    """Keeps paper-trading risk in check across all markets."""

    name = "Риск-менеджер"
    role = "risk_manager"
    emoji = "🛡️"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        per_market = config.BALANCE_PER_MARKET
        warnings = []
        critical = []

        for ctx in contexts:
            pnl = ctx["portfolio"].get("pnl_pct", 0)
            label = ctx["label"]
            if pnl <= -8:
                critical.append(f"{label} {pnl:+.1f}%")
            elif pnl <= -4:
                warnings.append(f"{label} {pnl:+.1f}%")

            pos_value = ctx["portfolio"].get("base", 0) * ctx.get("price", 0)
            pos_pct = pos_value / max(per_market, 1) * 100
            if pos_pct > 85:
                warnings.append(f"{label}: {pos_pct:.0f}% в монете — мало кэша для DIP")

        total_pnl = total.get("pnl_pct", 0)
        if total_pnl <= -5:
            critical.append(f"общий портфель {total_pnl:+.1f}%")

        recommendation = "hold"
        action = "Риск под контролем — лимиты не нарушены."
        if critical:
            recommendation = "reduce_aggression"
            action = (
                f"Просадки: {', '.join(critical)}. "
                "Центральному мозгу: уменьшить DCA и DIP до восстановления."
            )
        elif warnings:
            recommendation = "observe"
            action = f"Внимание: {', '.join(warnings[:4])}. Не усиливаем агрессию."

        summary = (
            f"Проверил риск на {len(contexts)} счетах (по ${per_market:,.0f} каждый). "
            f"Общий P&L: {total_pnl:+.2f}%. Предупреждений: {len(warnings)}, критичных: {len(critical)}."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "warnings": warnings[:6],
            "critical": critical,
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.8 if critical else (0.6 if warnings else 0.4),
        }
