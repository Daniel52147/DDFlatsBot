"""Rule-based trading assistant: candles, patterns, bot explanations."""

from __future__ import annotations

import time
from typing import Any

from simulator.candles import Candle


class TradingAssistant:
  """Explains market context and bot decisions in plain Russian."""

  def analyze_candles(self, candles: list[Candle], price: float, sma: float | None) -> dict[str, Any]:
    if len(candles) < 3:
      return {"summary": "Мало данных для анализа свечей.", "signals": []}

    last = candles[-1]
    prev = candles[-2]
    signals = []

    # Trend: last 5 closes
    recent = [c.close for c in candles[-5:]]
    if len(recent) >= 3:
      if recent[-1] > recent[0]:
        signals.append({"type": "trend", "text": "Краткосрочный тренд вверх 📈"})
      elif recent[-1] < recent[0]:
        signals.append({"type": "trend", "text": "Краткосрочный тренд вниз 📉"})

    # Candle body
    body = abs(last.close - last.open)
    full_range = last.high - last.low or 0.0001
    body_ratio = body / full_range
    if body_ratio < 0.2:
      signals.append({"type": "pattern", "text": "Доджи-подобная свеча — рынок неопределён"})
    elif last.close > last.open and body_ratio > 0.6:
      signals.append({"type": "pattern", "text": "Сильная бычья свеча"})
    elif last.close < last.open and body_ratio > 0.6:
      signals.append({"type": "pattern", "text": "Сильная медвежья свеча"})

    # SMA context
    if sma:
      diff = (price - sma) / sma * 100
      if diff < -3:
        signals.append({"type": "sma", "text": f"Цена ниже SMA на {abs(diff):.1f}% — зона для DIP-покупок"})
      elif diff > 3:
        signals.append({"type": "sma", "text": f"Цена выше SMA на {diff:.1f}% — перегрев, DCA осторожнее"})

    # Streak
    greens = sum(1 for c in candles[-4:] if c.close >= c.open)
    if greens >= 3:
      signals.append({"type": "streak", "text": f"{greens} зелёных свечи подряд — импульс вверх"})
    reds = sum(1 for c in candles[-4:] if c.close < c.open)
    if reds >= 3:
      signals.append({"type": "streak", "text": f"{reds} красных свечи подряд — давление продавцов"})

    summary = signals[0]["text"] if signals else "Рынок спокойный, явных сигналов нет."
    return {"summary": summary, "signals": signals, "price": price, "sma": sma}

  def explain_trade(self, reason: str, price: float, portfolio: dict) -> str:
    return (
      f"Сделка: {reason}. Цена ~${price:,.2f}. "
      f"Портфель: ${portfolio.get('portfolio_value', 0):,.2f} "
      f"({portfolio.get('pnl_pct', 0):+.2f}% от старта)."
    )

  def learning_tip(self, trade_count: int, vs_hold: float | None, params: dict) -> str:
    if trade_count < 3:
      return (
        "🎓 Режим обучения: бот копит данные. Сейчас идёт paper trading — "
        "деньги виртуальные, котировки настоящие. Нужно минимум 5 сделок для первой автонастройки."
      )
    if vs_hold is not None and vs_hold < 0:
      return (
        f"🎓 Бот пока отстаёт от «купил и держал» на {abs(vs_hold):.2f}%. "
        f"Система может снизить порог DIP (сейчас {params.get('dip_threshold_pct')}%) "
        "чтобы покупать на более глубоких просадках."
      )
    if vs_hold is not None and vs_hold >= 0:
      return (
        f"🎓 Бот опережает «купил и держал» на {vs_hold:+.2f}% — стратегия в норме. "
        "Продолжаем paper trading перед реальными деньгами."
      )
    return "🎓 Собираем статистику для обучения в нише BTC/USDT DCA+DIP."

  def greet(self) -> str:
    return (
      "Привет! Я помощник TradeSim. Слежу за свечами BTC/USDT, объясняю решения бота "
      "и подсказываю, как идёт обучение на виртуальном счёте."
    )

  def full_briefing(
    self,
    candles: list[Candle],
    price: float,
    sma: float | None,
    portfolio: dict,
    strategy_status: dict,
    trade_count: int,
  ) -> str:
    analysis = self.analyze_candles(candles, price, sma)
    tip = self.learning_tip(trade_count, portfolio.get("vs_hold_pct"), strategy_status.get("params", {}))
    lines = [
      self.greet(),
      "",
      f"💰 BTC: ${price:,.2f} | Портфель: ${portfolio.get('portfolio_value', 0):,.2f} ({portfolio.get('pnl_pct', 0):+.2f}%)",
      f"📊 {analysis['summary']}",
    ]
    for s in analysis["signals"][1:3]:
      lines.append(f"   • {s['text']}")
    lines.append("")
    lines.append(tip)
    if strategy_status.get("next_dca_in_hours") is not None:
      lines.append(f"⏱ Следующая плановая DCA через ~{strategy_status['next_dca_in_hours']} ч.")
    return "\n".join(lines)
