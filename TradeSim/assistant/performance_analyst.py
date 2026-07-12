"""Agent 9: aggregates win rate, drawdown and trade quality metrics."""

from __future__ import annotations

from typing import Any


class PerformanceAnalystAgent:
    name = "Аналитик"
    role = "performance_analyst"
    emoji = "📊"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        highlights = []
        total_trades = 0
        total_sells = 0
        beating = 0

        for ctx in contexts:
            stats = ctx.get("trade_stats") or {}
            tc = ctx.get("trade_count", 0)
            total_trades += tc
            total_sells += stats.get("sell", 0) + stats.get("tp", 0) + stats.get("stop", 0)
            vs = ctx["portfolio"].get("vs_hold_pct", 0)
            if vs >= 0:
                beating += 1
            if tc >= 3:
                highlights.append(
                    f"{ctx['label']}: {tc} сделок, vs hold {vs:+.2f}%, "
                    f"TP={stats.get('tp', 0)} STOP={stats.get('stop', 0)}"
                )

        pnl = total.get("pnl_pct", 0)
        sell_ratio = total_sells / max(total_trades, 1) * 100

        recommendation = "collect_data"
        action = "Мало сделок для статистики — продолжаем paper trading."
        if total_trades >= 8 and beating >= len(contexts) // 2:
            recommendation = "continue"
            action = f"Статистика зелёная: {beating}/{len(contexts)} рынков опережают hold."
        elif total_trades >= 6 and beating < 2:
            recommendation = "reduce_aggression"
            action = "Большинство рынков отстаёт — аналитик советует снизить агрессию."

        summary = (
            f"Метрики: {total_trades} сделок, {sell_ratio:.0f}% продаж, "
            f"опережают hold: {beating}/{len(contexts)}, P&L {pnl:+.2f}%."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "highlights": highlights[:5],
            "metrics": {
                "total_trades": total_trades,
                "sell_ratio_pct": round(sell_ratio, 1),
                "beating_hold": beating,
            },
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.65 if total_trades >= 5 else 0.4,
        }
