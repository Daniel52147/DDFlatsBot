"""Agent 7: coaches take-profit timing and realized gains."""

from __future__ import annotations

from typing import Any


class ProfitCoachAgent:
    """Tracks sells, profit zones above SMA and suggests when to lock gains."""

    name = "Коуч прибыли"
    role = "profit_coach"
    emoji = "💰"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        tips: list[str] = []
        ready: list[str] = []
        total_sells = 0
        total_tp_zone = 0

        for ctx in contexts:
            stats = ctx.get("trade_stats") or {}
            sells = stats.get("sell", 0) + stats.get("tp", 0)
            total_sells += sells
            st = ctx.get("strategy") or {}
            profit_pct = st.get("profit_pct") or 0
            tp_thresh = st.get("params", {}).get("take_profit_pct", 8)
            label = ctx["label"]
            pnl = ctx["portfolio"].get("pnl_pct", 0)

            if profit_pct >= tp_thresh * 0.85:
                total_tp_zone += 1
                ready.append(f"{label}: +{profit_pct:.1f}% над SMA — зона TP")
            elif pnl > 2 and sells == 0:
                tips.append(f"{label}: прибыль {pnl:+.1f}%, продаж ещё не было — ждём TP")
            elif sells >= 2:
                tips.append(f"{label}: {sells} фиксаций — хорошая дисциплина выхода")

        recommendation = "collect_data"
        action = "Мало продаж — копим данные для настройки take-profit."
        if total_tp_zone >= 2:
            recommendation = "continue"
            action = f"Зона TP на {total_tp_zone} рынках — бот может фиксировать часть прибыли."
        elif total_sells >= 3:
            recommendation = "continue"
            action = "Фиксации идут — продолжаем учиться на выходах."
        elif total.get("pnl_pct", 0) > 1.5:
            recommendation = "hold"
            action = "Портфель в плюсе — не торопим продажи, ждём сигналов SMA."

        summary = (
            f"Коучинг прибыли: {total_sells} продаж, {total_tp_zone} рынков в зоне TP. "
            f"Портфель {total.get('pnl_pct', 0):+.2f}%."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "tips": tips[:5],
            "ready": ready[:4],
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.65 if total_tp_zone or total_sells else 0.4,
        }
