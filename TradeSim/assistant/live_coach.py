"""Agent: Live path coach — readiness, phases, testnet discipline."""

from __future__ import annotations

import os
from typing import Any

import config


class LiveCoachAgent:
    name = "Live-наставник"
    role = "live_coach"
    emoji = "🚀"

    def analyze(
        self,
        contexts: list[dict[str, Any]],
        total: dict[str, Any],
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = meta or {}
        readiness = meta.get("live_readiness") or {}
        prep = meta.get("live_prep") or {}
        mode = meta.get("trading_mode", "paper")
        score = float(readiness.get("score_pct", 0))
        ready = bool(readiness.get("ready_for_live"))
        checks = readiness.get("checks") or []
        failed = [c for c in checks if c.get("required") and not c.get("ok")]
        stability = prep.get("stability") or {}
        exchange_orders = int(stability.get("exchange_orders", 0))
        sync_rate = float(stability.get("success_rate_pct", 100))
        phases = prep.get("phase_progress", "?")
        lessons: list[str] = []

        testnet_env = os.environ.get("EXCHANGE_TESTNET", "true").lower() in ("1", "true", "yes")
        if mode == "testnet" and not testnet_env:
            lessons.append("EXCHANGE_TESTNET=false в .env — исправь на true")
        if mode in ("testnet", "live") and exchange_orders < 5:
            lessons.append(f"Ордеров на бирже: {exchange_orders} — нужно ≥5 для фазы стабильности")
        if sync_rate < 85:
            lessons.append(f"Sync {sync_rate:.0f}% — почини перед Live")
        skip_ids = {"live_env"} if mode == "testnet" and testnet_env else set()
        for c in failed[:4]:
            if c.get("id") in skip_ids:
                continue
            lessons.append(f"❌ {c.get('label', '')}: {c.get('detail', '')[:80]}")

        recommendation = "hold"
        action = f"Путь к Live: {phases}. Readiness {score:.0f}%. Режим {mode} — учимся, не спешим."
        if ready and mode == "testnet" and exchange_orders >= 5:
            recommendation = "continue"
            action = (
                f"Readiness {score:.0f}% — можно пробовать Live Micro ($10). "
                "Сначала smoke test, не крупный депозит."
            )
        elif mode == "live" and not ready:
            recommendation = "reduce_aggression"
            action = (
                f"⚠️ Live при readiness {score:.0f}% — снизить до Live Micro или testnet. "
                + (failed[0].get("detail", "") if failed else "")
            )
        elif mode == "testnet" and exchange_orders == 0:
            recommendation = "collect_data"
            action = "Testnet без ордеров на бирже — сделай 2–5 сделок по $10, sync-paper, smoke test."
        elif score < 50:
            recommendation = "collect_data"
            action = "Рано для Live — paper/testnet дисциплина, EXCHANGE_SYNC_FROM_PAPER=true."

        summary = (
            f"Live-путь: {phases} · readiness {score:.0f}% · режим {mode} · "
            f"биржа {exchange_orders} ордеров · sync {sync_rate:.0f}%."
        )
        if lessons:
            summary += f" Уроков: {len(lessons)}."

        conf = 0.85 if (mode == "live" and not ready) else (0.7 if lessons else 0.55)

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "lessons": lessons[:6],
            "readiness_pct": round(score, 1),
            "ready_for_live": ready,
            "phase_progress": phases,
            "exchange_orders": exchange_orders,
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": conf,
        }
