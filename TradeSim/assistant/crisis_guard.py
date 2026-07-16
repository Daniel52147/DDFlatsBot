"""Agent: market crisis & playbook — halts, correlation, drawdown."""

from __future__ import annotations

from typing import Any

import config


class CrisisGuardAgent:
    name = "Кризис-страж"
    role = "crisis_guard"
    emoji = "🔥"

    def analyze(
        self,
        contexts: list[dict[str, Any]],
        total: dict[str, Any],
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        meta = meta or {}
        risk = meta.get("risk_gate") or {}
        corr = meta.get("correlation_risk") or {}
        prot = meta.get("protections") or {}
        pnl = float(total.get("pnl_pct", 0))
        scenarios: list[str] = []
        playbook_hints: list[str] = []

        if risk.get("portfolio_halt"):
            scenarios.append("portfolio_halt")
            playbook_hints.append("План Б: /pause all · не усреднять в обвале")
        if risk.get("correlation_block") or corr.get("block_buys"):
            scenarios.append("correlation_dump")
            playbook_hints.append("Всё падает — correlation block, ждать 1–3 дня")
        if prot.get("global_active"):
            scenarios.append("cooldown_period")
            playbook_hints.append("Cooldown — не clear protections")
        paused = prot.get("paused_symbols") or {}
        if paused:
            scenarios.append("stoploss_guard")
            playbook_hints.append(f"StoplossGuard: пауза {list(paused.keys())[:3]}")

        bearish = sum(1 for c in contexts if c.get("portfolio", {}).get("pnl_pct", 0) < -5)
        if bearish >= 4:
            scenarios.append("bear_market_slow")
            playbook_hints.append("Медвежий рынок — Live Micro или testnet")

        if pnl <= -config.LIVE_MAX_DAILY_LOSS_PCT:
            scenarios.append("daily_loss_limit")
        if pnl <= -config.LIVE_MAX_DRAWDOWN_PCT:
            scenarios.append("max_drawdown")

        recommendation = "hold"
        action = "Кризисных сигналов нет — playbook наготове."
        if "max_drawdown" in scenarios or risk.get("portfolio_halt"):
            recommendation = "pause_dip"
            action = "🔥 Просадка портфеля — план А: halt. План Б: /pause all."
        elif "correlation_dump" in scenarios:
            recommendation = "pause_dip"
            action = "🔥 Корреляционный обвал — блок покупок. План Б: не resume all."
        elif "stoploss_guard" in scenarios or prot.get("global_active"):
            recommendation = "reduce_aggression"
            action = "🔥 Серия стопов/cooldown — playbook: ждать, не догонять."
        elif "bear_market_slow" in scenarios:
            recommendation = "reduce_aggression"
            action = "🔥 Много рынков в минусе — conservative, реже DCA."

        summary = (
            f"Кризис-монитор: сценариев {len(scenarios)} · P&L {pnl:+.2f}% · "
            f"halt={bool(risk.get('portfolio_halt'))} · corr_block={bool(risk.get('correlation_block'))}."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "scenarios": scenarios,
            "playbook_hints": playbook_hints[:4],
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.9 if len(scenarios) >= 2 else (0.75 if scenarios else 0.3),
        }
