"""Agent 4: tracks price swings — especially on volatile memecoins."""

from __future__ import annotations

from typing import Any


class VolatilityWatcherAgent:
    """Spots sharp moves and tells the brain when to hunt dips or step back."""

    name = "Волатильность"
    role = "volatility_watcher"
    emoji = "⚡"

    def analyze(self, contexts: list[dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
        hot = []
        calm = []
        spikes = []

        for ctx in contexts:
            vol = ctx.get("volatility_pct", 0)
            label = ctx["label"]
            tag = ""
            if ctx.get("viral"):
                tag = " 🔥"
            elif ctx.get("growth"):
                tag = " 📈"
            if ctx.get("volatile") or ctx.get("viral"):
                if vol >= 8:
                    hot.append(f"{label}{tag} ({vol:.1f}% колебания)")
                elif vol >= 4:
                    spikes.append(f"{label}{tag} ({vol:.1f}%)")
                else:
                    calm.append(f"{label}{tag}")
            elif ctx.get("growth") and vol >= 5:
                spikes.append(f"{label}{tag} growth ({vol:.1f}%)")
            elif vol >= 5:
                spikes.append(f"{label} ({vol:.1f}%)")

            dip = ctx.get("strategy", {}).get("dip_pct")
            if dip is not None and dip >= ctx.get("strategy", {}).get("params", {}).get("spike_threshold_pct", 99):
                spikes.append(f"{label}: SPIKE-зона {dip:.1f}% ниже SMA")

        recommendation = "hold"
        action = "Волатильность в норме — базовая стратегия."
        if hot:
            recommendation = "experiment"
            action = (
                f"Горячие монеты: {', '.join(hot)}. "
                "Центральному мозгу: на мемкоинах ловим SPIKE-покупки, но не раздуваем DCA."
            )
        elif spikes:
            recommendation = "continue"
            action = f"Есть движение: {', '.join(spikes[:3])}. DIP/SPIKE по правилам."

        viral_labels = [c["label"] for c in contexts if c.get("viral")]
        growth_labels = [c["label"] for c in contexts if c.get("growth")]
        volatile_labels = [c["label"] for c in contexts if c.get("volatile")]
        summary = (
            f"Слежу за {len(contexts)} рынками. "
            f"Growth: {len(growth_labels)}, волатильные: {len(volatile_labels)}"
            f"{', 🔥 ' + ', '.join(viral_labels) if viral_labels else ''}. "
            f"Горячих: {len(hot)}, сигналов: {len(spikes)}."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "hot": hot,
            "spikes": spikes[:5],
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.75 if hot or spikes else 0.45,
        }
