"""Central brain: merges specialist agents into one decision."""

from __future__ import annotations

import time
from typing import Any

from assistant.correlation_analyst import CorrelationAnalystAgent
from assistant.performance_analyst import PerformanceAnalystAgent
from assistant.portfolio_allocator import PortfolioAllocatorAgent
from assistant.stop_guardian import StopGuardianAgent
from assistant.news_watcher import NewsWatcherAgent
from assistant.profit_coach import ProfitCoachAgent
from assistant.risk_manager import RiskManagerAgent
from assistant.scheme_learner import SchemeLearnerAgent
from assistant.trader_mentor import TraderMentorAgent
from assistant.trend_scout import TrendScoutAgent
from assistant.trader_watcher import TraderWatcherAgent
from assistant.volatility_watcher import VolatilityWatcherAgent
from assistant.helper import TradingAssistant


class CentralBrain:
    """
    Shared mind, divided roles:
      🎓 Наставник  — правила профи-трейдеров
      📰 Новостник  — заголовки и настроение рынка
      🧪 Исследователь — новые схемы из paper trading
      ⚡ Волатильность — резкие движения (DOGE, PEPE)
      🛡️ Риск-менеджер — просадки и лимиты
      📈 Тренд-разведчик — SMA и направление рынка
      💰 Коуч прибыли — take-profit и фиксация
      🔗 Корреляция — связи между монетами
      📊 Аналитик — метрики и win rate
      🛑 Стоп-охранник — stop-loss и паузы
      ⚖️ Аллокатор — распределение капитала
    """

    def __init__(self):
        self.mentor = TraderMentorAgent()
        self.news = NewsWatcherAgent()
        self.schemer = SchemeLearnerAgent()
        self.volatility = VolatilityWatcherAgent()
        self.risk = RiskManagerAgent()
        self.trend = TrendScoutAgent()
        self.profit = ProfitCoachAgent()
        self.correlation = CorrelationAnalystAgent()
        self.analyst = PerformanceAnalystAgent()
        self.guardian = StopGuardianAgent()
        self.allocator = PortfolioAllocatorAgent()
        self.trader_watcher = TraderWatcherAgent()
        self.talker = TradingAssistant()
        self.last_cycle: dict[str, Any] = {}
        self.last_cycle_ts = 0.0
        self.last_applied_decision: str | None = None

    async def think(self, contexts: list[dict], total: dict) -> dict[str, Any]:
        """Run all agents and synthesize central decision."""
        mentor = self.mentor.analyze(contexts, total)
        news = await self.news.analyze(contexts, total)
        schemer = self.schemer.analyze(contexts, total)
        volatility = self.volatility.analyze(contexts, total)
        risk = self.risk.analyze(contexts, total)
        trend = self.trend.analyze(contexts, total)
        profit = self.profit.analyze(contexts, total)
        correlation = self.correlation.analyze(contexts, total)
        analyst = self.analyst.analyze(contexts, total)
        guardian = self.guardian.analyze(contexts, total)
        allocator = self.allocator.analyze(contexts, total)
        trader_watch = await self.trader_watcher.analyze(contexts, total)

        votes = {
            "continue": 0.0,
            "hold": 0.0,
            "observe": 0.0,
            "reduce_aggression": 0.0,
            "pause_dip": 0.0,
            "experiment": 0.0,
            "collect_data": 0.0,
        }
        reports = (
            mentor, news, schemer, volatility, risk, trend, profit, correlation,
            analyst, guardian, allocator, trader_watch,
        )
        for report in reports:
            rec = report.get("recommendation", "hold")
            if rec == "observe":
                rec = "hold"
            votes[rec] = votes.get(rec, 0) + report.get("confidence", 0.5)

        if guardian.get("halts") and len(guardian["halts"]) >= 2:
            decision = "emergency_halt"
            verdict = f"🛑 СТОП: {guardian['halts'][0]} — пауза просадочных ботов."
        elif votes.get("pause_dip", 0) >= 1.2 and votes.get("reduce_aggression", 0) >= 0.5:
            decision = "pause_dip"
            verdict = "⚠️ ОСТОРОЖНО: новости + риск — не усиливать покупки на просадке."
        elif votes.get("reduce_aggression", 0) >= 1.0:
            decision = "reduce_aggression"
            verdict = "📉 Снизить агрессию: просадки или перегрев риска."
        elif votes.get("experiment", 0) >= 0.9 and votes.get("continue", 0) >= 0.5:
            decision = "experiment"
            verdict = "⚡ Эксперимент: волатильные монеты — ловим SPIKE, но с лимитами."
        elif votes.get("continue", 0) >= 1.0:
            decision = "continue"
            verdict = "✅ Всё в норме — боты учатся по плану."
        elif votes.get("collect_data", 0) >= 0.8:
            decision = "collect_data"
            verdict = "📚 Режим сбора данных — рано для новых схем."
        else:
            decision = "hold"
            verdict = "⏸ Держим курс — ждём больше сигналов."

        brain_summary = self._format_brain_report(
            mentor, news, schemer, volatility, risk, trend, profit, correlation,
            analyst, guardian, allocator, trader_watch, verdict,
        )

        cycle = {
            "ts": time.time(),
            "decision": decision,
            "verdict": verdict,
            "mentor": mentor,
            "news": news,
            "schemer": schemer,
            "volatility": volatility,
            "risk": risk,
            "trend": trend,
            "profit": profit,
            "correlation": correlation,
            "analyst": analyst,
            "guardian": guardian,
            "allocator": allocator,
            "trader_watcher": trader_watch,
            "votes": votes,
            "summary": brain_summary,
        }
        self.last_cycle = cycle
        self.last_cycle_ts = time.time()
        return cycle

    def _format_brain_report(
        self, mentor, news, schemer, volatility, risk, trend, profit, correlation,
        analyst, guardian, allocator, trader_watch, verdict: str,
    ) -> str:
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
            "",
            f"{volatility['emoji']} {volatility['name']}: {volatility['summary']}",
            f"   → {volatility['action_for_brain']}",
            "",
            f"{risk['emoji']} {risk['name']}: {risk['summary']}",
            f"   → {risk['action_for_brain']}",
            "",
            f"{trend['emoji']} {trend['name']}: {trend['summary']}",
            f"   → {trend['action_for_brain']}",
            "",
            f"{profit['emoji']} {profit['name']}: {profit['summary']}",
            f"   → {profit['action_for_brain']}",
            "",
            f"{correlation['emoji']} {correlation['name']}: {correlation['summary']}",
            f"   → {correlation['action_for_brain']}",
            "",
            f"{analyst['emoji']} {analyst['name']}: {analyst['summary']}",
            f"   → {analyst['action_for_brain']}",
            "",
            f"{guardian['emoji']} {guardian['name']}: {guardian['summary']}",
            f"   → {guardian['action_for_brain']}",
            "",
            f"{allocator['emoji']} {allocator['name']}: {allocator['summary']}",
            f"   → {allocator['action_for_brain']}",
            "",
            f"{trader_watch['emoji']} {trader_watch['name']}: {trader_watch['summary']}",
            f"   → {trader_watch['action_for_brain']}",
        ]
        for item in schemer.get("learned", [])[:2]:
            lines.append(f"   • {item}")
        return "\n".join(lines)

    def apply_decision(self, sessions: dict, decision: str):
        """Adjust bots when central decision changes (clamped, no drift)."""
        if decision == self.last_applied_decision:
            return
        self.last_applied_decision = decision

        if decision in ("continue", "hold", "collect_data"):
            return

        for session in sessions.values():
            p = dict(session.bot.get_params())
            if decision == "pause_dip":
                p["dip_extra_amount"] = p.get("dip_extra_amount", 0) * 0.5
                p["dip_threshold_pct"] = p.get("dip_threshold_pct", 3) + 1.0
                if p.get("spike_extra_amount"):
                    p["spike_extra_amount"] *= 0.5
            elif decision == "reduce_aggression":
                p["dca_amount"] = p.get("dca_amount", 25) * 0.85
                p["dip_extra_amount"] = p.get("dip_extra_amount", 0) * 0.85
            elif decision == "emergency_halt":
                pnl = session.engine.snapshot(session.feed.price or session.demo_price).get("pnl_pct", 0)
                if pnl <= -8:
                    session.bot.enabled = False
                p["dip_extra_amount"] = p.get("dip_extra_amount", 0) * 0.3
                p["dca_amount"] = p.get("dca_amount", 25) * 0.7
            elif decision == "experiment" and session.volatile:
                p["dip_threshold_pct"] = max(3.0, p.get("dip_threshold_pct", 5) - 0.5)

            session.set_params_bounded(p)

    def apply_learning_boost(self, sessions: dict, contexts: list[dict]):
        """Micro-tune each market every brain cycle from live stats."""
        for ctx in contexts:
            sym = ctx.get("symbol")
            if sym not in sessions:
                continue
            session = sessions[sym]
            vs = ctx["portfolio"].get("vs_hold_pct", 0)
            pnl = ctx["portfolio"].get("pnl_pct", 0)
            vol = ctx.get("volatility_pct", 0)
            stats = ctx.get("trade_stats", {})
            deltas: dict[str, float] = {}

            if ctx.get("volatile") and vs < -0.5 and vol >= 6:
                deltas["dip_threshold_pct"] = -0.2
                if vol >= 10:
                    deltas["spike_threshold_pct"] = -0.5
            if vs > 1.2 and stats.get("tp", 0) < stats.get("buy", 1) // 3:
                deltas["take_profit_pct"] = -0.4
            if vs > 2:
                deltas["take_profit_fraction"] = 0.02
            if stats.get("spike", 0) >= 2 and vs >= 0:
                deltas["spike_extra_amount"] = 2

            if deltas:
                _, msg = session.optimizer.apply_deltas(deltas)
                session.bot.update_params(session.optimizer.get_params())
                session.sync_base_params()

    def apply_schemer_hints(self, sessions: dict, schemer: dict):
        """Turn active scheme signals into bounded param tweaks."""
        by_label = {s.label: s for s in sessions.values()}
        for proposal in schemer.get("proposals", []):
            pid = proposal.get("id")
            for label in proposal.get("markets", []):
                session = by_label.get(label)
                if not session:
                    continue
                p = dict(session.bot.get_params())
                if pid == "deep_dip" and session.volatile:
                    p["spike_threshold_pct"] = max(4, p.get("spike_threshold_pct", 10) - 0.5)
                elif pid == "meme_volatility":
                    p["dip_threshold_pct"] = max(2, p.get("dip_threshold_pct", 5) - 0.3)
                    p["spike_extra_amount"] = min(80, p.get("spike_extra_amount", 30) + 2)
                elif pid == "quiet_market":
                    p["dca_amount"] = min(80, p.get("dca_amount", 25) + 2)
                session.set_params_bounded(p)
                session.sync_base_params()

    def chat(self, user_msg: str, contexts: list[dict], total: dict) -> str:
        msg = user_msg.lower().strip()

        if any(w in msg for w in ("мозг", "централ", "агент", "помощник", "команда", "советуют", "вердикт")):
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

        if any(w in msg for w in ("профи", "трейдер", "наставник")):
            m = self.last_cycle.get("mentor") if self.last_cycle else None
            if m:
                lines = [f"🎓 {m['summary']}", ""]
                for i in m.get("insights", [])[:5]:
                    lines.append(f"• [{i['market']}] {i['rule']}: {i['text']}")
                return "\n".join(lines)
            return "Наставник скоро проанализирует рынки."

        if any(w in msg for w in ("vs hold", "vs_hold", "холд", "hold", "бенчмарк", "benchmark", "альфа")):
            bench = total.get("benchmark") or {}
            alpha_line = (
                f"Бот опережает hold на {bench.get('vs_hold_pct', 0):+.2f} п.п."
                if bench.get("vs_hold_pct", 0) >= 0
                else f"Бот отстаёт от hold на {bench.get('vs_hold_pct', 0):+.2f} п.п."
            )
            return (
                f"📊 Портфель vs buy-and-hold:\n"
                f"• Живой: {total.get('pnl_pct', 0):+.2f}% ({total.get('total_value', 0):,.0f}$)\n"
                f"• Hold: {bench.get('hold_pnl_pct', 0):+.2f}% ({bench.get('hold_value', 0):,.0f}$)\n"
                f"• Alpha: {bench.get('vs_hold_pct', 0):+.2f}% ({bench.get('alpha_usd', 0):+,.2f}$)\n"
                f"{alpha_line}"
            )

        if any(w in msg for w in ("grid", "momentum", "rsi", "scalp", "скальп", "сетк")):
            from simulator.strategies import STRATEGY_META
            lines = ["🎯 Стратегии TradeSim v17:", ""]
            for key, meta in STRATEGY_META.items():
                users = [c["label"] for c in contexts if c.get("strategy_type") == key]
                who = f" → {', '.join(users)}" if users else ""
                lines.append(f"{meta['emoji']} **{meta['name']}** ({key}){who}")
                lines.append(f"   {meta['desc']}")
            return "\n".join(lines)

        if any(w in msg for w in ("fee", "комисс", "комса")):
            return "💸 Комиссии: вкладка «Отчёт» или GET /api/fees — сумма fee по всем сделкам из SQLite."

        if any(w in msg for w in ("отчёт", "отчет", "daily", "день")):
            return "📋 Дневной отчёт: GET /api/daily-report — P&L, топ монет, сделки за 24ч, решения мозга."

        if any(w in msg for w in ("схем", "стратег", "исслед", "эксперимент")) and "grid" not in msg and "momentum" not in msg:
            s = self.last_cycle.get("schemer") if self.last_cycle else None
            if s:
                lines = [f"🧪 {s['summary']}", ""]
                for p in s.get("proposals", []):
                    lines.append(f"• {p['scheme']}: {p['desc']} ({', '.join(p['markets'])})")
                for l in s.get("learned", []):
                    lines.append(f"• {l}")
                return "\n".join(lines)
            return "Исследователь копит данные для новых схем."

        if any(w in msg for w in ("волат", "мем", "pepe", "doge", "скачк", "резк")):
            v = self.last_cycle.get("volatility") if self.last_cycle else None
            if v:
                lines = [f"⚡ {v['summary']}", ""]
                for h in v.get("hot", []):
                    lines.append(f"🔥 {h}")
                for s in v.get("spikes", []):
                    lines.append(f"📊 {s}")
                return "\n".join(lines) if len(lines) > 1 else v["summary"]
            volatile = [c["label"] for c in contexts if c.get("volatile")]
            return f"Волатильные рынки: {', '.join(volatile) or 'нет'}. Мозг обновит анализ через ~2 мин."

        if any(w in msg for w in ("риск", "просад", "drawdown", "опасн", "лимит")):
            r = self.last_cycle.get("risk") if self.last_cycle else None
            if r:
                lines = [f"🛡️ {r['summary']}", ""]
                for w in r.get("critical", []):
                    lines.append(f"🚨 {w}")
                for w in r.get("warnings", []):
                    lines.append(f"⚠️ {w}")
                return "\n".join(lines) if len(lines) > 1 else r["summary"]
            return "Риск-менеджер скоро проверит просадки по всем счетам."

        if any(w in msg for w in ("тренд", "trend", "направлен", "развед")):
            t = self.last_cycle.get("trend") if self.last_cycle else None
            if t:
                lines = [f"📈 {t['summary']}", ""]
                for item in t.get("trends", [])[:6]:
                    lines.append(f"• {item}")
                return "\n".join(lines)
            return "Тренд-разведчик скоро просканирует SMA по всем рынкам."

        if any(w in msg for w in ("коуч", "фикса", "take", "profit coach")) or (
            "прибыл" in msg and any(w in msg for w in ("коуч", "совет", "фикс"))
        ):
            p = self.last_cycle.get("profit") if self.last_cycle else None
            if p:
                lines = [f"💰 {p['summary']}", ""]
                for item in p.get("ready", []):
                    lines.append(f"🎯 {item}")
                for item in p.get("tips", [])[:4]:
                    lines.append(f"• {item}")
                return "\n".join(lines) if len(lines) > 1 else p["summary"]
            return "Коуч прибыли ждёт данных о продажах и зонах TP."

        if any(w in msg for w in ("коррел", "correlation", "связ", "лидер", "аутсайдер")):
            c = self.last_cycle.get("correlation") if self.last_cycle else None
            if c:
                lines = [f"🔗 {c['summary']}", ""]
                for item in c.get("pairs", [])[:5]:
                    lines.append(f"• {item}")
                for item in c.get("leaders", [])[:2]:
                    lines.append(f"🏆 {item}")
                return "\n".join(lines) if len(lines) > 1 else c["summary"]
            return "Аналитик корреляции сравнит движения монет через минуту."

        if any(w in msg for w in ("аналит", "метрик", "статистик", "win rate")):
            a = self.last_cycle.get("analyst") if self.last_cycle else None
            if a:
                lines = [f"📊 {a['summary']}", ""]
                for h in a.get("highlights", [])[:5]:
                    lines.append(f"• {h}")
                return "\n".join(lines) if len(lines) > 1 else a["summary"]
            return "Аналитик собирает метрики по сделкам."

        if any(w in msg for w in ("стоп", "stop", "охранник", "halt")):
            g = self.last_cycle.get("guardian") if self.last_cycle else None
            if g:
                lines = [f"🛑 {g['summary']}", ""]
                for h in g.get("halts", []):
                    lines.append(f"🚨 {h}")
                for a in g.get("alerts", [])[:4]:
                    lines.append(f"⚠️ {a}")
                return "\n".join(lines) if len(lines) > 1 else g["summary"]
            return "Стоп-охранник следит за просадками и stop-loss."

        if any(w in msg for w in ("аллок", "распредел", "баланс", "allocator")):
            al = self.last_cycle.get("allocator") if self.last_cycle else None
            if al:
                lines = [f"⚖️ {al['summary']}", ""]
                for s in al.get("suggestions", [])[:4]:
                    lines.append(f"• {s}")
                return "\n".join(lines) if len(lines) > 1 else al["summary"]
            return "Аллокатор проверит распределение по рынкам."

        if any(w in msg for w in ("трейдер", "следопыт", "копитрейд", "copy", "ansem", "planb")):
            tw = self.last_cycle.get("trader_watcher") if self.last_cycle else None
            if tw:
                lines = [f"👁️ {tw['summary']}", ""]
                for s in tw.get("hot", [])[:3]:
                    lines.append(f"🟢 {s}")
                for s in tw.get("warnings", [])[:3]:
                    lines.append(f"🔴 {s}")
                return "\n".join(lines) if len(lines) > 1 else tw["summary"]
            return "Следопыт мониторит 8 публичных стилей топ-трейдеров — спроси через минуту."

        if any(w in msg for w in ("бэктест", "backtest", "история свеч")):
            return (
                "⏱ Бэктест: вкладка «Бэктест» под графиком или POST /api/backtest "
                f"с {{\"symbol\": \"{contexts[0]['symbol'] if contexts else 'BTCUSDT'}\", \"limit\": 500}}. "
                "Прогон за минуты по OHLC — та же логика что live + Shadow Lab."
            )

        if any(w in msg for w in ("биржа", "binance", "api ключ", "реальн")):
            return (
                "🏦 Реальная биржа: задай BINANCE_API_KEY + BINANCE_API_SECRET в env, "
                "EXCHANGE_ENABLED=true в config. Сейчас paper по умолчанию. "
                "GET /api/exchange/status · риск-лимиты: max ордер, дневная просадка."
            )

        base = self.talker.chat(user_msg, contexts, total)
        if self.last_cycle:
            return base + "\n\n—\n" + self.last_cycle.get("verdict", "")
        return base
