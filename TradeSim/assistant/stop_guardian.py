"""Agent 10: monitors stop-loss triggers and drawdown halts."""

from __future__ import annotations

from typing import Any


class StopGuardianAgent:
    name = "Стоп-охранник"
    role = "stop_guardian"
    emoji = "🛑"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        alerts = []
        halts = []
        stop_count = 0

        for ctx in contexts:
            stats = ctx.get("trade_stats") or {}
            stop_count += stats.get("stop", 0)
            pnl = ctx["portfolio"].get("pnl_pct", 0)
            label = ctx["label"]
            avg = ctx.get("strategy", {}).get("avg_entry") or ctx.get("avg_entry")
            price = ctx.get("price", 0)
            sl_pct = ctx.get("strategy", {}).get("params", {}).get("stop_loss_pct", 12)

            if avg and price and avg > 0:
                unrealized = (price - avg) / avg * 100
                if unrealized <= -sl_pct * 0.9:
                    alerts.append(f"{label}: −{abs(unrealized):.1f}% от входа — близко к STOP")
                elif unrealized <= -sl_pct * 0.6:
                    alerts.append(f"{label}: просадка {unrealized:.1f}% от средней цены")

            if pnl <= -10:
                halts.append(f"{label}: портфель {pnl:+.1f}% — пауза бота")
            elif pnl <= -7:
                alerts.append(f"{label}: глубокая просадка {pnl:+.1f}%")

        total_pnl = total.get("pnl_pct", 0)
        if total_pnl <= -6:
            halts.append(f"Общий портфель {total_pnl:+.1f}%")

        recommendation = "hold"
        action = "Стоп-уровни не нарушены — торговля по правилам."
        if halts:
            recommendation = "pause_dip"
            action = (
                f"Критично: {', '.join(halts[:3])}. "
                "Центральному мозгу: пауза DIP/SPIKE, включить stop-loss."
            )
        elif alerts:
            recommendation = "reduce_aggression"
            action = f"Предупреждения: {', '.join(alerts[:3])}. Не наращивать позиции."

        summary = (
            f"Стоп-контроль: {len(alerts)} предупреждений, {len(halts)} критичных. "
            f"STOP-LOSS срабатываний: {stop_count}. Общий P&L: {total_pnl:+.2f}%."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "alerts": alerts[:5],
            "halts": halts,
            "stop_count": stop_count,
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.85 if halts else (0.65 if alerts else 0.4),
        }
