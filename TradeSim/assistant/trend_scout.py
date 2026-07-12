"""Agent 6: reads SMA and candle momentum — trend direction per market."""

from __future__ import annotations

from typing import Any


class TrendScoutAgent:
    """Spots uptrends, downtrends and sideways ranges across all markets."""

    name = "Тренд-разведчик"
    role = "trend_scout"
    emoji = "📈"

    def _trend(self, ctx: dict) -> tuple[str, str]:
        price = ctx.get("price", 0)
        sma = ctx.get("sma")
        candles = ctx.get("candles") or []
        label = ctx["label"]

        if not sma or sma <= 0:
            return "unknown", f"{label}: мало данных для тренда"

        diff = (price - sma) / sma * 100
        momentum = 0.0
        if len(candles) >= 5:
            closes = [c.close for c in candles[-5:]]
            if closes[0]:
                momentum = (closes[-1] - closes[0]) / closes[0] * 100

        if diff >= 2 and momentum >= 0.5:
            return "up", f"{label}: восходящий тренд (+{diff:.1f}% к SMA, импульс +{momentum:.1f}%)"
        if diff <= -2 and momentum <= -0.5:
            return "down", f"{label}: нисходящий тренд ({diff:.1f}% к SMA)"
        if abs(diff) < 1 and abs(momentum) < 0.8:
            return "flat", f"{label}: боковик у SMA"
        if diff > 0:
            return "up_weak", f"{label}: слабый рост над SMA (+{diff:.1f}%)"
        return "down_weak", f"{label}: слабое давление ниже SMA ({diff:.1f}%)"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        trends: list[str] = []
        up = down = flat = 0

        for ctx in contexts:
            kind, text = self._trend(ctx)
            trends.append(text)
            if kind in ("up", "up_weak"):
                up += 1
            elif kind in ("down", "down_weak"):
                down += 1
            else:
                flat += 1

        recommendation = "hold"
        action = "Тренды смешанные — DCA по расписанию без усиления."
        if up >= len(contexts) // 2 + 1:
            recommendation = "continue"
            action = "Большинство рынков в росте — DCA и DIP по плану, TP на перегретых."
        elif down >= len(contexts) // 2 + 1:
            recommendation = "reduce_aggression"
            action = "Преобладает давление вниз — не раздувать DIP, ждать стабилизации."

        summary = (
            f"Разведка трендов: ↑{up} · ↓{down} · ↔{flat} из {len(contexts)} рынков. "
            f"Общий P&L: {total.get('pnl_pct', 0):+.2f}%."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "trends": trends[:6],
            "counts": {"up": up, "down": down, "flat": flat},
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.7 if up or down >= 3 else 0.5,
        }
