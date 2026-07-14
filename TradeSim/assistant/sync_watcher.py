"""Agent: exchange ↔ paper sync and reconcile watchdog."""

from __future__ import annotations

from typing import Any


class SyncWatcherAgent:
    name = "Синхронизатор"
    role = "sync_watcher"
    emoji = "🔗"

    def analyze(
        self,
        contexts: list[dict[str, Any]],
        total: dict[str, Any],
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = meta or {}
        prep = meta.get("live_prep") or {}
        stability = prep.get("stability") or {}
        sync_rate = float(stability.get("success_rate_pct", 100))
        sync_failures = int(stability.get("sync_failures", 0))
        exchange_orders = int(stability.get("exchange_orders", 0))
        reconcile = meta.get("reconcile") or {}
        bad = reconcile.get("markets") or reconcile.get("symbols") or []
        if isinstance(bad, dict):
            bad_list = [
                {"symbol": k, **(v if isinstance(v, dict) else {"delta": v})}
                for k, v in bad.items()
                if isinstance(v, dict) and abs(float(v.get("base_delta", v.get("delta", 0)) or 0)) > 0.01
            ]
        else:
            bad_list = [m for m in bad if abs(float(m.get("base_delta", m.get("delta", 0)) or 0)) > 0.01]

        warnings: list[str] = []
        critical: list[str] = []
        if sync_rate < 85:
            critical.append(f"sync success {sync_rate:.0f}% < 85%")
        if sync_failures > 3:
            warnings.append(f"сбоев sync: {sync_failures}")
        for m in bad_list[:4]:
            sym = m.get("symbol", m.get("label", "?"))
            delta = float(m.get("base_delta", m.get("delta", 0)) or 0)
            if abs(delta) > 0.1:
                critical.append(f"{sym}: Δ base {delta:+.4f}")
            elif abs(delta) > 0.01:
                warnings.append(f"{sym}: Δ {delta:+.4f}")

        recommendation = "hold"
        action = "Paper и биржа в норме — sync стабилен."
        if critical:
            recommendation = "reduce_aggression"
            action = (
                f"Reconcile/sync критично: {', '.join(critical[:3])}. "
                "Пауза новых ордеров · sync-paper-all · не Live."
            )
        elif warnings:
            recommendation = "observe"
            action = f"Расхождения: {', '.join(warnings[:3])}. POST sync-paper-all."

        summary = (
            f"Sync {sync_rate:.0f}% · сбоев {sync_failures} · ордеров биржи {exchange_orders} · "
            f"reconcile Δ: {len(bad_list)} рынков."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "warnings": warnings,
            "critical": critical,
            "sync_rate_pct": sync_rate,
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.8 if critical else (0.55 if warnings else 0.35),
        }
