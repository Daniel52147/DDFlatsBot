"""Rule-based trading assistant with chat in Russian."""

from __future__ import annotations

from typing import Any

import config
from simulator.candles import Candle


COIN_SYNONYMS = {
    "btc": "BTC", "биток": "BTC", "биткоин": "BTC", "bitcoin": "BTC",
    "eth": "ETH", "эфир": "ETH", "ethereum": "ETH", "эфириум": "ETH",
    "sol": "SOL", "солана": "SOL", "solana": "SOL",
    "bnb": "BNB", "бинанс": "BNB",
    "xrp": "XRP", "рипл": "XRP", "ripple": "XRP",
    "ada": "ADA", "кардано": "ADA", "cardano": "ADA",
    "avax": "AVAX", "авакс": "AVAX", "avalanche": "AVAX",
    "link": "LINK", "чейнлинк": "LINK", "chainlink": "LINK",
    "arb": "ARB", "arbitrum": "ARB", "арбитрум": "ARB",
    "sui": "SUI", "суи": "SUI",
    "near": "NEAR", "ниар": "NEAR",
    "dot": "DOT", "полкадот": "DOT", "polkadot": "DOT",
    "inj": "INJ", "инжектив": "INJ", "injective": "INJ",
    "ton": "TON", "тонкоин": "TON", "toncoin": "TON", "телеграм": "TON",
    "doge": "DOGE", "доги": "DOGE", "догик": "DOGE", "dogecoin": "DOGE",
    "pepe": "PEPE", "пепе": "PEPE",
    "wif": "WIF", "виф": "WIF", "dogwifhat": "WIF", "вирус": "WIF", "хайп": "WIF",
}


class TradingAssistant:
    def _labels(self, contexts: list[dict]) -> str:
        return ", ".join(c["label"] for c in contexts)

    def _volatile_labels(self, contexts: list[dict]) -> str:
        v = [c["label"] for c in contexts if c.get("volatile")]
        return ", ".join(v) if v else "нет"

    def _viral_labels(self, contexts: list[dict]) -> str:
        v = [c["label"] for c in contexts if c.get("viral")]
        return ", ".join(v) if v else "нет"

    def _growth_labels(self, contexts: list[dict]) -> str:
        g = [c["label"] for c in contexts if c.get("growth")]
        return ", ".join(g) if g else "нет"

    def _fmt_price(self, price: float, label: str) -> str:
        if label == "PEPE":
            return f"${price:.8f}"
        if label in ("DOGE",):
            return f"${price:.6f}"
        if label == "BTC":
            return f"${price:,.0f}"
        return f"${price:,.4f}"

    def analyze_candles(self, candles: list[Candle], price: float, sma: float | None) -> dict[str, Any]:
        if len(candles) < 3:
            return {"summary": "Мало данных для анализа.", "signals": []}

        signals = []
        recent = [c.close for c in candles[-5:]]
        if len(recent) >= 3:
            chg = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] else 0
            if chg > 1.5:
                signals.append({"text": f"краткосрочный рост +{chg:.1f}% 📈"})
            elif chg < -1.5:
                signals.append({"text": f"краткосрочное падение {chg:.1f}% 📉"})
            elif abs(chg) < 0.3:
                signals.append({"text": "рынок спокойный — мало движения"})

        if sma:
            diff = (price - sma) / sma * 100
            if diff < -3:
                signals.append({"text": f"цена ниже SMA на {abs(diff):.1f}% — зона DIP"})
            elif diff > 3:
                signals.append({"text": f"цена выше SMA на {diff:.1f}% — тренд вверх"})

        if len(candles) >= 5:
            hi = max(c.high for c in candles[-10:])
            lo = min(c.low for c in candles[-10:])
            avg = sum(c.close for c in candles[-10:]) / min(10, len(candles))
            if avg > 0:
                vol = (hi - lo) / avg * 100
                if vol >= 8:
                    signals.append({"text": f"высокая волатильность {vol:.1f}% — шанс на SPIKE-покупку"})

        summary = signals[0]["text"] if signals else "рынок в боковике"
        return {"summary": summary, "signals": signals}

    def _fmt_market_line(self, ctx: dict) -> str:
        p = ctx["portfolio"]
        vol_tag = " ⚡" if ctx.get("volatile") else ""
        return (
            f"• {ctx['label']}{vol_tag}: {self._fmt_price(ctx['price'], ctx['label'])} | "
            f"портфель ${p['portfolio_value']:,.2f} ({p['pnl_pct']:+.2f}%) | "
            f"сделок: {ctx['trade_count']}"
        )

    def _find_coin(self, msg: str, contexts: list[dict]) -> dict | None:
        by_label = {c["label"].lower(): c for c in contexts}
        by_name = {c["name"].lower(): c for c in contexts}
        norm = msg.replace("/", "").replace("-", " ")
        for alias, label in COIN_SYNONYMS.items():
            if alias in norm:
                for ctx in contexts:
                    if ctx["label"] == label:
                        return ctx
        for key, ctx in {**by_label, **by_name}.items():
            if key in norm or ctx["symbol"].lower() in norm.replace("usdt", ""):
                return ctx
        return None

    def chat(
        self,
        user_msg: str,
        contexts: list[dict[str, Any]],
        total: dict[str, Any],
    ) -> str:
        msg = user_msg.lower().strip()
        labels = self._labels(contexts)
        n = len(contexts)

        if any(w in msg for w in ("привет", "здравств", "hello", "hi", "start")):
            return (
                f"Привет! Я помощник TradeSim — слежу за {n} рынками: {labels}.\n"
                f"Growth-альты: {self._growth_labels(contexts)}.\n"
                f"Волатильные: {self._volatile_labels(contexts)}.\n"
                f"🔥 Вирусный тренд: {self._viral_labels(contexts)}.\n\n"
                "Спроси:\n"
                "• «как дела?» — сводка\n"
                "• «что с DOGE?» — монета\n"
                "• «сколько заработал?» — P&L\n"
                "• «что думает мозг?» — 11 агентов\n"
                "• «аналитика» / «стоп» / «аллокация»\n"
                "• «тренд» / «корреляция» / «коуч прибыли»\n"
                "• «волатильность» / «риск» / «новости»\n"
                "• «что такое DCA?» — объяснение"
            )

        if any(w in msg for w in ("помощ", "help", "команды", "что умеешь", "что можешь")):
            return (
                "📖 Команды помощника:\n"
                f"• Сводка: как дела, статус, обстановка\n"
                f"• Монета: что с BTC/ETH/DOGE/PEPE...\n"
                f"• Деньги: заработал, прибыль, pnl\n"
                f"• Обучение: как идёт обучение, схемы\n"
                f"• Мозг: что думает мозг, агенты (11), вердикт\n"
                f"• Аналитика, стоп-охранник, аллокация\n"
                f"• Новости, волатильность, риск\n"
                f"• Теория: что такое DCA, SMA, DIP, SPIKE\n"
                f"• Сделки: последняя сделка, сколько торгов\n\n"
                f"Рынки ({n}): {labels}"
            )

        if any(w in msg for w in ("stop", "стоп", "stop-loss", "stop loss")):
            return (
                "📘 STOP-LOSS — бот продаёт часть позиции, если цена упала на X% от средней цены входа.\n"
                "Majors: ~12%, мемкоины: 15–18%. Cooldown 12ч между срабатываниями.\n"
                "Стоп-охранник может поставить бота на паузу при глубокой просадке."
            )

        if any(w in msg for w in ("ручн", "manual", "сам куп", "сам прод")):
            return (
                "🖐 Ручные сделки — кнопки «Купить $25» / «Продать $25» под статусом бота.\n"
                "Paper only, лимит $1–500. Сделки помечаются MANUAL и учитываются в аналитике."
            )

        if any(w in msg for w in ("экспорт", "export", "скачать", "json")):
            return "📥 Экспорт сделок — кнопка «Экспорт сделок» внизу страницы (JSON)."

        if any(w in msg for w in ("пополн", "deposit", "закинуть", "внести", "депозит")):
            return (
                "💵 Пополнение paper-счёта:\n"
                "• Кнопка «+ Пополнить» в шапке\n"
                "• На все 17 рынков поровну или на одну монету\n"
                "• Сразу доступно для DCA/DIP ботов и ручных сделок\n"
                "• История — вкладка «Пополнения» в таблицах\n\n"
                "Это виртуальные деньги для обучения, не реальная биржа."
            )

        if any(w in msg for w in ("учится", "обуча", "сам учит", "реально учит", "нейросет", "фейк", "показух")):
            return (
                "🔍 Честный ответ — вкладка «Честный статус» в таблицах.\n\n"
                "✅ Реально учится (эвристики):\n"
                "• Меняет DCA/DIP/TP по результатам vs «купил и держал»\n"
                "• Shadow Lab: 12 клонов тестируют параметры\n"
                "• Всё в SQLite — сделки, автонастройки, мозг\n\n"
                "❌ Не нейросеть и не гарантия прибыли:\n"
                "• 11 агентов = правила Python + ключевые слова\n"
                "• Paper only — нет ордеров на Binance\n\n"
                f"Спроси «лаборатория» или «аналитика» для цифр."
            )

        if any(w in msg for w in ("готов", "readiness", "оценк", "идея", "насколько")):
            return (
                "📋 Оценка TradeSim (beta):\n"
                "• Идея сильная: paper + живые цены + параллельное обучение\n"
                "• Готово ~70%: торговля, 17 рынков, Shadow Lab, аналитика\n"
                "• Нужно: тесты, бэктест, полная история сделок из БД\n"
                "• Для реальных денег — отдельный этап (API ключи биржи)\n\n"
                "Сейчас это лаборатория для экспериментов, не финсовет."
            )

        if any(w in msg for w in ("лаборатор", "shadow", "клон", "mock", "мок", "тенев")):
            n = len(contexts) * config.SHADOW_CLONES_PER_MARKET
            return (
                f"🔬 Shadow Lab — скрытая лаборатория внизу страницы.\n"
                f"• {config.SHADOW_CLONES_PER_MARKET} mock-ботов на каждую монету ({n} всего)\n"
                f"• Те же цены, разные параметры DCA/DIP/TP\n"
                f"• OHLC forward-walk — ускоренное обучение\n"
                f"• Победитель каждые ~{config.SHADOW_EVAL_SEC} сек → живой бот\n\n"
                "Открой панель 🔬 внизу или спроси «как дела?»."
            )

        if any(w in msg for w in ("полный сброс", "full reset", "очистить бд", "базу")):
            return (
                "🗑 Два вида сброса внизу страницы:\n"
                "• «Сброс портфеля» — обнуляет счета, история сделок в SQLite остаётся\n"
                "• «Полный сброс БД» — удаляет всё: сделки, снимки, настройки, мозг"
            )

        if any(w in msg for w in ("dca", "дца", "доллар")) and any(
            w in msg for w in ("что", "как", "объяс", "это")
        ):
            p = contexts[0]["strategy"]["params"] if contexts else {}
            return (
                "📘 DCA (Dollar Cost Averaging) — покупка на фиксированную сумму по расписанию, "
                "чтобы не угадывать дно.\n\n"
                f"Сейчас: ${p.get('dca_amount', 25)} каждые {p.get('dca_interval_hours', 24)} ч. "
                "На волатильных (DOGE, PEPE) сумма меньше, интервал короче — больше шансов поймать скачки.\n\n"
                "DIP — доп. покупка, когда цена ниже SMA. SPIKE — ещё одна покупка при резкой просадке на мемкоинах."
            )

        if any(w in msg for w in ("sma", "сма", "скользящ")):
            return (
                "📘 SMA (Simple Moving Average) — средняя цена за N свечей.\n"
                "Бот сравнивает текущую цену с SMA.\n"
                "Ниже SMA → DIP/SPIKE покупка. Выше SMA → TAKE-PROFIT (фиксация части прибыли)."
            )

        if any(w in msg for w in ("take", "profit", "фикса", "продаж", "продаёт")):
            return (
                "📘 TAKE-PROFIT — бот продаёт часть монет, когда цена сильно выше SMA.\n"
                "Majors: ~10% над SMA, продаёт 15% позиции.\n"
                "DOGE/PEPE: быстрее (6–8%), продаёт 25–30% — фиксирует прибыль на скачках.\n"
                "Это paper trading — учимся входить и выходить."
            )

        if any(w in msg for w in ("кривая", "equity", "график портф", "история портф")):
            return (
                "📈 Кривая капитала — график общего портфеля во времени (панель «Обучение»).\n"
                "Данные из SQLite каждые 5 минут. Спроси «статистика обучения» для цифр."
            )

        if any(w in msg for w in ("статистик", "база данных", "sqlite", "лог")):
            total_trades = sum(c["trade_count"] for c in contexts)
            sells = sum(1 for c in contexts for t in c.get("recent_trades", []) if t.get("side") == "sell")
            return (
                f"📊 Статистика обучения:\n"
                f"• Сделок в памяти: {total_trades}\n"
                f"• Рынков: {len(contexts)}\n"
                f"• Портфель сохраняется в SQLite — перезапуск не сбрасывает прогресс\n"
                f"• Автонастройка после 5+ сделок если отстаём от «держать»\n"
                f"Сброс только кнопкой «Сбросить всё»."
            )

        if any(w in msg for w in ("как дела", "как идут", "статус", "обстановка", "сводка")):
            lines = [
                f"📊 Общий портфель: ${total['total_value']:,.2f} ({total['pnl_pct']:+.2f}%)",
                f"Рынков: {n} · на каждый ~${total.get('start_balance', 10000) / max(n, 1):,.0f}",
                "",
            ]
            for ctx in contexts:
                analysis = self.analyze_candles(ctx["candles"], ctx["price"], ctx["sma"])
                lines.append(self._fmt_market_line(ctx))
                lines.append(f"  └ {analysis['summary']}")
                if ctx.get("volatility_pct"):
                    lines.append(f"  └ волатильность: {ctx['volatility_pct']:.1f}%")
            lines.append("")
            lines.append(self._learning_summary(contexts, total))
            return "\n".join(lines)

        if any(w in msg for w in ("заработ", "прибыл", "убыт", "pnl", "доход")) or (
            "сколько" in msg and any(w in msg for w in ("заработ", "прибыл", "денег", "получ"))
        ):
            best = max(contexts, key=lambda c: c["portfolio"]["pnl_pct"])
            worst = min(contexts, key=lambda c: c["portfolio"]["pnl_pct"])
            volatile_ctx = [c for c in contexts if c.get("volatile")]
            vol_line = ""
            if volatile_ctx:
                vbest = max(volatile_ctx, key=lambda c: c["portfolio"]["pnl_pct"])
                vol_line = f"\nЛучший мемкоин: {vbest['label']} ({vbest['portfolio']['pnl_pct']:+.2f}%)"
            return (
                f"💰 Всего: ${total['total_value']:,.2f} из ${total['start_balance']:,.2f} "
                f"({total['pnl_pct']:+.2f}%)\n\n"
                f"Лучший: {best['label']} ({best['portfolio']['pnl_pct']:+.2f}%)\n"
                f"Слабее: {worst['label']} ({worst['portfolio']['pnl_pct']:+.2f}%){vol_line}\n\n"
                "Paper trading — деньги виртуальные, котировки реальные."
            )

        if any(w in msg for w in ("учит", "обучен", "учёб", "учеб", "развива")):
            return self._learning_summary(contexts, total)

        if any(w in msg for w in ("сравн", "лучше", "хуже", "рейтинг", "топ")):
            ranked = sorted(contexts, key=lambda c: c["portfolio"].get("vs_hold_pct", 0), reverse=True)
            lines = ["🏆 Рейтинг vs «купил и держал»:", ""]
            for i, ctx in enumerate(ranked, 1):
                vh = ctx["portfolio"].get("vs_hold_pct", 0)
                lines.append(f"{i}. {ctx['label']}: {vh:+.2f}%")
            return "\n".join(lines)

        if any(w in msg for w in ("последн", "недавн")) and any(
            w in msg for w in ("сделк", "покуп", "торг")
        ):
            lines = ["📋 Последние сделки:", ""]
            found = False
            for ctx in contexts:
                for t in reversed(ctx.get("recent_trades", [])):
                    found = True
                    d = self._fmt_price(t["price"], ctx["label"])
                    lines.append(f"• [{ctx['label']}] {t['reason']} @ {d}")
            if not found:
                lines.append("Пока нет сделок — боты скоро сделают стартовые DCA.")
            return "\n".join(lines)

        coin = self._find_coin(msg, contexts)
        if coin:
            analysis = self.analyze_candles(coin["candles"], coin["price"], coin["sma"])
            st = coin["strategy"]
            p = coin["portfolio"]
            lines = [
                f"📈 {coin['name']} ({coin['label']}/USDT)"
                + (" ⚡ волатильный" if coin.get("volatile") else ""),
                f"Цена: {self._fmt_price(coin['price'], coin['label'])}",
                f"Портфель: ${p['portfolio_value']:,.2f} ({p['pnl_pct']:+.2f}%)",
                f"vs «купил и держал»: {p.get('vs_hold_pct', 0):+.2f}%",
                f"📊 {analysis['summary']}",
            ]
            if coin.get("volatility_pct"):
                lines.append(f"Волатильность (10 свечей): {coin['volatility_pct']:.1f}%")
            lines += [
                f"🤖 Бот: {'активен' if st.get('enabled') else 'на паузе'}",
                f"DCA: ${st['params']['dca_amount']} / {st['params']['dca_interval_hours']}ч",
                f"DIP порог: {st['params']['dip_threshold_pct']}%",
            ]
            if st["params"].get("spike_threshold_pct"):
                lines.append(
                    f"SPIKE: +${st['params'].get('spike_extra_amount', 0)} "
                    f"при просадке ≥{st['params']['spike_threshold_pct']}%"
                )
            if st["params"].get("take_profit_pct"):
                lines.append(
                    f"TAKE-PROFIT: продажа {int(st['params'].get('take_profit_fraction', 0.15) * 100)}% "
                    f"при +{st['params']['take_profit_pct']}% над SMA"
                )
            if st.get("profit_pct") is not None and st["profit_pct"] > 0:
                lines.append(f"Сейчас над SMA: +{st['profit_pct']}%")
            lines.append(f"Сделок: {coin['trade_count']} · источник: {coin.get('feed_source', '?')}")
            if st.get("next_dca_in_hours") is not None:
                lines.append(f"След. DCA: ~{st['next_dca_in_hours']} ч.")
            for sig in analysis.get("signals", [])[1:3]:
                lines.append(f"  • {sig['text']}")
            return "\n".join(lines)

        if any(w in msg for w in ("сделк", "торг", "покуп", "купил")):
            total_trades = sum(c["trade_count"] for c in contexts)
            lines = [f"📋 Всего сделок по {n} рынкам: {total_trades}", ""]
            for ctx in sorted(contexts, key=lambda c: -c["trade_count"]):
                if ctx["trade_count"]:
                    tag = " ⚡" if ctx.get("volatile") else ""
                    lines.append(f"{ctx['label']}{tag}: {ctx['trade_count']} сделок")
            if total_trades == 0:
                lines.append("Скоро стартовые DCA-покупки на всех рынках.")
            return "\n".join(lines)

        if any(w in msg for w in ("совет", "что дума", "рекоменд", "покупать", "продавать")):
            volatile = [c for c in contexts if c.get("volatile")]
            extra = ""
            if volatile:
                best_v = max(volatile, key=lambda c: c["portfolio"].get("vs_hold_pct", -999))
                extra = (
                    f"\n\nНа волатильных ({self._volatile_labels(contexts)}) бот ловит SPIKE-просадки. "
                    f"Сейчас лучше выглядит {best_v['label']}."
                )
            return (
                "Я не даю финсоветов «покупай/продавай». По paper-счёту:\n"
                + "\n".join(self._fmt_market_line(c) for c in contexts)
                + extra
                + "\n\nPaper trading 1–3 месяца — потом смотри статистику vs hold."
            )

        return (
            "Не совсем понял. Попробуй:\n"
            "• «как идут дела?» — сводка\n"
            "• «что с DOGE?» / «что с PEPE?»\n"
            "• «сколько заработал?» — P&L\n"
            "• «что думает мозг?» — 11 агентов\n"
            "• «аналитика» / «стоп» / «аллокация»\n"
            "• «волатильность» / «риск» / «новости»\n"
            "• «что такое DCA?» — объяснение\n"
            "• «помощь» — все команды"
        )

    def _learning_summary(self, contexts: list[dict], total: dict) -> str:
        total_trades = sum(c["trade_count"] for c in contexts)
        if total_trades < 2:
            return (
                f"🎓 Быстрое обучение: {total_trades}/2 сделок до первой автонастройки. "
                f"Мозг каждые 45 сек, DOGE/PEPE — автонастройка каждые 10 мин."
            )
        beating = [c["label"] for c in contexts if c["portfolio"].get("vs_hold_pct", 0) >= 0]
        volatile = [c["label"] for c in contexts if c.get("volatile")]
        vol_note = ""
        if volatile:
            vbeat = [c["label"] for c in contexts if c.get("volatile") and c["portfolio"].get("vs_hold_pct", 0) >= 0]
            vol_note = f" Мемкоины: {', '.join(vbeat) or 'учатся'}."
        return (
            f"🎓 Быстрое обучение: {total_trades} сделок на {len(contexts)} рынках. "
            f"Опережают hold: {', '.join(beating) or 'пока никто'}. "
            f"P&L: {total['pnl_pct']:+.2f}%.{vol_note} "
            f"Анализ каждой сделки + автонастройка при просадке."
        )

    def explain_trade(self, reason: str, price: float, portfolio: dict, label: str = "") -> str:
        prefix = f"[{label}] " if label else ""
        return (
            f"{prefix}Сделка: {reason}. Цена ~${price:,.6f}. "
            f"Портфель: ${portfolio.get('portfolio_value', 0):,.2f} "
            f"({portfolio.get('pnl_pct', 0):+.2f}%)."
        )

    def full_briefing(self, *args, **kwargs) -> str:
        return self.chat("как идут дела", args[0] if args else [], kwargs.get("total", {}))
