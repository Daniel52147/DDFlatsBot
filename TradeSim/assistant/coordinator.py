"""Central brain: merges three specialist agents into one decision."""

from __future__ import annotations

import time
from typing import Any

from assistant.news_watcher import NewsWatcherAgent
from assistant.scheme_learner import SchemeLearnerAgent
from assistant.trader_mentor import TraderMentorAgent
from assistant.helper import TradingAssistant


class CentralBrain:
    """
    Shared mind, divided roles:
      🎓 Наставник  — правила профи-трейдеров
      📰 Новостник  — заголовки и настроение рынка
      🧪 Исследователь — новые схемы из paper trading
    """

    def __init__(self):
        self.mentor = TraderMentorAgent()
        self.news = NewsWatcherAgent()
        self.schemer = SchemeLearnerAgent()
        self.talker = TradingAssistant()
        self.last_cycle: dict[str, Any] = {}
        self.last_cycle_ts = 0.0

    async def think(self, contexts: list[dict], total: dict) -> dict[str, Any]:
        """Run all agents and synthesize central decision."""
        mentor = self.mentor.analyze(contexts, total)
        news = await self.news.analyze(contexts, total)
        schemer = self.schemer.analyze(contexts, total)

        votes = {
            "continue": 0,
            "hold": 0,
            "reduce_aggression": 0,
            "pause_dip": 0,
            "experiment": 0,
            "collect_data": 0,
        }
        for report in (mentor, news, schemer):
            rec = report.get("recommendation", "hold")
            votes[rec] = votes.get(rec, 0) + report.get("confidence", 0.5)

        # Central decision logic
        if votes.get("pause_dip", 0) >= 1.2 and votes.get("reduce_aggression", 0) >= 0.5:
            decision = "pause_dip"
            verdict = "⚠️ ОСТОРОЖНО: новости + профи советуют не усиливать покупки на просадке."
        elif votes.get("reduce_aggression", 0) >= 1.0:
            decision = "reduce_aggression"
            verdict = "📉 Снизить агрессию: несколько рынков в просадке."
        elif votes.get("continue", 0) >= 1.0:
            decision = "continue"
            verdict = "✅ Всё в норме — боты учатся по плану."
        elif votes.get("collect_data", 0) >= 0.8:
            decision = "collect_data"
            verdict = "📚 Режим сбора данных — рано для новых схем."
        else:
            decision = "hold"
            verdict = "⏸ Держим курс — ждём больше сигналов."

        brain_summary = self._format_brain_report(mentor, news, schemer, verdict)

        cycle = {
            "ts": time.time(),
            "decision": decision,
            "verdict": verdict,
            "mentor": mentor,
            "news": news,
            "schemer": schemer,
            "votes": votes,
            "summary": brain_summary,
        }
        self.last_cycle = cycle
        self.last_cycle_ts = time.time()
        return cycle

    def _format_brain_report(self, mentor, news, schemer, verdict: str) -> str:
        lines = [
            "🧠 ЦЕНТРАЛЬНЫЙ МОЗГ",
            verdict,
            "",
            f"{mentor['emoji']} {mentor['name']}: {mentor['summary']}",
            f"   → {mentor['action_for_brain']}",
            "",
            f"{news['emoji']} {news['name']}: {news['summary']}",
            f"   → {news['action_for_brain']}",
        ]
        if news.get("headlines"):
            lines.append(f"   Заголовок: {news['headlines'][0]['title'][:70]}...")
        lines += [
            "",
            f"{schemer['emoji']} {schemer['name']}: {schemer['summary']}",
            f"   → {schemer['action_for_brain']}",
        ]
        for item in schemer.get("learned", [])[:2]:
            lines.append(f"   • {item}")
        return "\n".join(lines)

    def apply_decision(self, sessions: dict, decision: str):
        """Adjust bots based on central brain decision."""
        for session in sessions.values():
            p = session.bot.params
            if decision == "pause_dip":
                p["dip_extra_amount"] = max(10.0, p["dip_extra_amount"] * 0.5)
                p["dip_threshold_pct"] = min(8.0, p["dip_threshold_pct"] + 1.0)
            elif decision == "reduce_aggression":
                p["dca_amount"] = max(10.0, p["dca_amount"] * 0.8)
            elif decision == "continue":
                pass  # keep params
            session.bot.update_params(p)

    def chat(self, user_msg: str, contexts: list[dict], total: dict) -> str:
        msg = user_msg.lower().strip()

        if any(w in msg for w in ("мозг", "централ", "агент", "помощник", "команда", "советуют")):
            if self.last_cycle:
                return self.last_cycle.get("summary", "Мозг ещё не думал — подожди минуту.")
            return "Центральный мозг скоро проведёт первый анализ."

        if any(w in msg for w in ("новост", "news", "заголов")):
            n = self.last_cycle.get("news") if self.last_cycle else None
            if n:
                lines = [f"📰 {n['summary']}", ""]
                for h in n.get("headlines", [])[:5]:
                    lines.append(f"• [{h['source']}] {h['title'][:90]}")
                return "\n".join(lines)
            return "Новостник ещё не проверял ленту. Спроси через минуту или «как дела?»."

        if any(w in msg for w in ("профи", "трейдер", "наставник", "учит")):
            m = self.last_cycle.get("mentor") if self.last_cycle else None
            if m:
                lines = [f"🎓 {m['summary']}", ""]
                for i in m.get("insights", [])[:5]:
                    lines.append(f"• [{i['market']}] {i['rule']}: {i['text']}")
                return "\n".join(lines)
            return "Наставник скоро проанализирует рынки."

        if any(w in msg for w in ("схем", "стратег", "исслед", "эксперимент")):
            s = self.last_cycle.get("schemer") if self.last_cycle else None
            if s:
                lines = [f"🧪 {s['summary']}", ""]
                for p in s.get("proposals", []):
                    lines.append(f"• {p['scheme']}: {p['desc']} ({', '.join(p['markets'])})")
                for l in s.get("learned", []):
                    lines.append(f"• {l}")
                return "\n".join(lines)
            return "Исследователь копит данные для новых схем."

        # Fallback to basic chat assistant
        base = self.talker.chat(user_msg, contexts, total)
        if self.last_cycle:
            return base + "\n\n—\n" + self.last_cycle.get("verdict", "")
        return base
