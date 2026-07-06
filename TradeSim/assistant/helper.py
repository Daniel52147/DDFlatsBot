"""Rule-based trading assistant with chat in Russian."""

from __future__ import annotations

import re
from typing import Any

from simulator.candles import Candle


class TradingAssistant:
    def analyze_candles(self, candles: list[Candle], price: float, sma: float | None) -> dict[str, Any]:
        if len(candles) < 3:
            return {"summary": "Мало данных для анализа.", "signals": []}

        last = candles[-1]
        signals = []
        recent = [c.close for c in candles[-5:]]
        if len(recent) >= 3:
            if recent[-1] > recent[0]:
                signals.append({"text": "краткосрочный тренд вверх 📈"})
            elif recent[-1] < recent[0]:
                signals.append({"text": "краткосрочный тренд вниз 📉"})

        if sma:
            diff = (price - sma) / sma * 100
            if diff < -3:
                signals.append({"text": f"цена ниже SMA на {abs(diff):.1f}% — зона DIP"})
            elif diff > 3:
                signals.append({"text": f"цена выше SMA на {diff:.1f}%"})

        summary = signals[0]["text"] if signals else "рынок спокойный"
        return {"summary": summary, "signals": signals}

    def _fmt_market_line(self, ctx: dict) -> str:
        p = ctx["portfolio"]
        return (
            f"• {ctx['label']}: ${ctx['price']:,.2f} | "
            f"портфель ${p['portfolio_value']:,.2f} ({p['pnl_pct']:+.2f}%) | "
            f"сделок: {ctx['trade_count']}"
        )

    def chat(
        self,
        user_msg: str,
        contexts: list[dict[str, Any]],
        total: dict[str, Any],
    ) -> str:
        msg = user_msg.lower().strip()
        by_label = {c["label"].lower(): c for c in contexts}
        by_name = {c["name"].lower(): c for c in contexts}

        # Greeting
        if any(w in msg for w in ("привет", "здравств", "hello", "hi")):
            return (
                "Привет! Я помощник TradeSim. Слежу за 4 рынками: BTC, ETH, SOL, BNB.\n"
                "Спроси: «как дела?», «что с ETH?», «сколько заработал?», «как идёт обучение?»"
            )

        # Overall status
        if any(w in msg for w in ("как дела", "как идут", "статус", "обстановка", "сводка")):
            lines = [
                f"📊 Общий портфель: ${total['total_value']:,.2f} ({total['pnl_pct']:+.2f}%)",
                "",
            ]
            for ctx in contexts:
                analysis = self.analyze_candles(ctx["candles"], ctx["price"], ctx["sma"])
                lines.append(self._fmt_market_line(ctx))
                lines.append(f"  └ {analysis['summary']}")
            lines.append("")
            lines.append(self._learning_summary(contexts, total))
            return "\n".join(lines)

        # PnL / earnings
        if any(w in msg for w in ("заработ", "прибыл", "убыт", "pnl", "доход", "сколько")):
            best = max(contexts, key=lambda c: c["portfolio"]["pnl_pct"])
            worst = min(contexts, key=lambda c: c["portfolio"]["pnl_pct"])
            return (
                f"💰 Всего: ${total['total_value']:,.2f} из ${total['start_balance']:,.2f} "
                f"({total['pnl_pct']:+.2f}%)\n\n"
                f"Лучший: {best['label']} ({best['portfolio']['pnl_pct']:+.2f}%)\n"
                f"Слабее: {worst['label']} ({worst['portfolio']['pnl_pct']:+.2f}%)\n\n"
                "Помни: это paper trading — деньги виртуальные, котировки настоящие."
            )

        # Learning
        if any(w in msg for w in ("учит", "обучен", "учёб", "учеб", "развива")):
            return self._learning_summary(contexts, total)

        # Specific coin
        for key, ctx in {**by_label, **by_name}.items():
            if key in msg or ctx["symbol"].lower() in msg.replace("/", ""):
                analysis = self.analyze_candles(ctx["candles"], ctx["price"], ctx["sma"])
                st = ctx["strategy"]
                p = ctx["portfolio"]
                lines = [
                    f"📈 {ctx['name']} ({ctx['label']}/USDT)",
                    f"Цена: ${ctx['price']:,.4f}",
                    f"Портфель: ${p['portfolio_value']:,.2f} ({p['pnl_pct']:+.2f}%)",
                    f"vs «купил и держал»: {p.get('vs_hold_pct', 0):+.2f}%",
                    f"📊 {analysis['summary']}",
                    f"🤖 Бот: {'активен' if st.get('enabled') else 'на паузе'}",
                    f"DCA: ${st['params']['dca_amount']} / {st['params']['dca_interval_hours']}ч",
                    f"Сделок: {ctx['trade_count']}",
                ]
                if st.get("next_dca_in_hours") is not None:
                    lines.append(f"След. DCA: ~{st['next_dca_in_hours']} ч.")
                return "\n".join(lines)

        # Trades
        if any(w in msg for w in ("сделк", "торг", "покуп", "купил")):
            total_trades = sum(c["trade_count"] for c in contexts)
            lines = [f"📋 Всего сделок по 4 рынкам: {total_trades}", ""]
            for ctx in contexts:
                if ctx["trade_count"]:
                    lines.append(f"{ctx['label']}: {ctx['trade_count']} сделок")
            if total_trades == 0:
                lines.append("Пока боты копят данные — скоро начнут DCA-покупки.")
            return "\n".join(lines)

        # Advice
        if any(w in msg for w in ("совет", "что дума", "рекоменд", "покупать", "продавать")):
            return (
                "Я не даю финансовых советов «покупай/продавай». Но по paper-счёту:\n"
                + "\n".join(self._fmt_market_line(c) for c in contexts)
                + "\n\nПродолжай paper trading 1–3 месяца, прежде чем думать о реальных деньгах."
            )

        # Default
        return (
            "Не совсем понял вопрос. Попробуй:\n"
            "• «как идут дела?» — сводка по всем рынкам\n"
            "• «что с ETH?» — детали по монете\n"
            "• «сколько заработал?» — общий P&L\n"
            "• «как идёт обучение?» — прогресс ботов"
        )

    def _learning_summary(self, contexts: list[dict], total: dict) -> str:
        total_trades = sum(c["trade_count"] for c in contexts)
        if total_trades < 5:
            return (
                f"🎓 Режим обучения: {total_trades} сделок из 5 нужных для автонастройки. "
                "Боты учатся отдельно в каждой нише (BTC, ETH, SOL, BNB)."
            )
        beating = [c["label"] for c in contexts if c["portfolio"].get("vs_hold_pct", 0) >= 0]
        return (
            f"🎓 Обучение: {total_trades} сделок. "
            f"Опережают «купил и держал»: {', '.join(beating) or 'пока никто'}. "
            f"Общий результат: {total['pnl_pct']:+.2f}%."
        )

    def explain_trade(self, reason: str, price: float, portfolio: dict, label: str = "") -> str:
        prefix = f"[{label}] " if label else ""
        return (
            f"{prefix}Сделка: {reason}. Цена ~${price:,.4f}. "
            f"Портфель: ${portfolio.get('portfolio_value', 0):,.2f} "
            f"({portfolio.get('pnl_pct', 0):+.2f}%)."
        )

    def full_briefing(self, *args, **kwargs) -> str:
        return self.chat("как идут дела", args[0] if args else [], kwargs.get("total", {}))
