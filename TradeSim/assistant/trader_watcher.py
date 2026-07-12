"""Agent 12: tracks popular crypto traders and copy-trading signals."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Public figures / styles — signals inferred from live market + optional leaderboard
TRACKED_TRADERS = [
    {"id": "cvd", "name": "CVD Trader", "style": "orderflow", "markets": ["BTC", "ETH"]},
    {"id": "planb", "name": "PlanB", "style": "macro_s2f", "markets": ["BTC"]},
    {"id": "ansem", "name": "Ansem", "style": "meme_momentum", "markets": ["SOL", "WIF", "PEPE"]},
    {"id": "hsaka", "name": "Hsaka", "style": "scalp", "markets": ["BTC", "ETH", "SOL"]},
    {"id": "pentoshi", "name": "Pentoshi", "style": "swing", "markets": ["ETH", "LINK", "AVAX"]},
    {"id": "cobie", "name": "Cobie", "style": "contrarian", "markets": ["BTC", "ETH"]},
    {"id": "gainzy", "name": "GCR-style", "style": "macro_contrarian", "markets": ["BTC", "SOL"]},
    {"id": "loomdart", "name": "Loomdart", "style": "nft_defi", "markets": ["ETH", "ARB", "SUI"]},
]


class TraderWatcherAgent:
    """Monitors trader styles vs current market — suggests alignment or caution."""

    name = "Следопыт трейдеров"
    role = "trader_watcher"
    emoji = "👁️"

    def __init__(self):
        self.last_signals: list[dict] = []
        self.last_fetch_ts = 0.0

    async def _fetch_binance_ticker_momentum(self) -> dict[str, float]:
        """24h price change % per USDT pair from public API."""
        out: dict[str, float] = {}
        urls = (
            "https://api.binance.com/api/v3/ticker/24hr",
            "https://api.binance.us/api/v3/ticker/24hr",
        )
        for url in urls:
            try:
                async with httpx.AsyncClient(timeout=12) as client:
                    r = await client.get(url)
                    r.raise_for_status()
                    for row in r.json():
                        sym = row.get("symbol", "")
                        if sym.endswith("USDT"):
                            label = sym.replace("USDT", "")
                            out[label] = float(row.get("priceChangePercent", 0))
                if out:
                    return out
            except Exception as e:
                logger.warning("trader watcher ticker %s: %s", url, e)
        return out

    def _signal_for_trader(self, trader: dict, momentum: dict[str, float], contexts: list[dict]) -> dict:
        markets = trader["markets"]
        changes = [momentum.get(m, 0) for m in markets]
        avg_chg = sum(changes) / len(changes) if changes else 0
        style = trader["style"]

        by_label = {c["label"]: c for c in contexts}
        vs_holds = [by_label[m]["portfolio"].get("vs_hold_pct", 0) for m in markets if m in by_label]
        bot_vs = sum(vs_holds) / len(vs_holds) if vs_holds else 0

        if style in ("meme_momentum", "scalp") and avg_chg > 3:
            bias, action = "bullish", "continue"
            text = f"{trader['name']}: мем/скальп стиль — рынок +{avg_chg:.1f}% 24ч, можно ловить SPIKE"
        elif style in ("macro_s2f", "macro_contrarian") and avg_chg < -2:
            bias, action = "accumulate", "continue"
            text = f"{trader['name']}: macro — просадка {avg_chg:.1f}%, DCA/DIP по стилю"
        elif style == "contrarian" and avg_chg > 8:
            bias, action = "caution", "reduce_aggression"
            text = f"{trader['name']}: contrarian — перегрев +{avg_chg:.1f}%, осторожно с DIP"
        elif style == "swing" and abs(avg_chg) < 1.5:
            bias, action = "neutral", "hold"
            text = f"{trader['name']}: swing — флэт, ждём тренд"
        elif bot_vs < -1 and avg_chg < 0:
            bias, action = "defensive", "pause_dip"
            text = f"{trader['name']}: бот отстаёт ({bot_vs:+.1f}% vs hold) при падении"
        else:
            bias, action = "neutral", "hold"
            text = f"{trader['name']}: {markets} {avg_chg:+.1f}% 24ч — без сильного сигнала"

        return {
            "trader": trader["name"],
            "style": style,
            "markets": markets,
            "momentum_24h": round(avg_chg, 2),
            "bias": bias,
            "action": action,
            "text": text,
        }

    async def analyze(self, contexts: list[dict], total: dict) -> dict[str, Any]:
        momentum = await self._fetch_binance_ticker_momentum()
        self.last_fetch_ts = time.time()

        signals = [
            self._signal_for_trader(t, momentum, contexts)
            for t in TRACKED_TRADERS
        ]
        self.last_signals = signals

        bullish = [s for s in signals if s["bias"] in ("bullish", "accumulate")]
        caution = [s for s in signals if s["bias"] in ("caution", "defensive")]

        if len(caution) >= 3:
            rec = "reduce_aggression"
            summary = f"👁️ {len(caution)} трейдеров за осторожность — снизить агрессию DIP/SPIKE"
        elif len(bullish) >= 4:
            rec = "continue"
            summary = f"👁️ {len(bullish)} трейдеров за накопление — DCA/DIP в плане"
        else:
            rec = "hold"
            summary = f"👁️ Слежу за {len(TRACKED_TRADERS)} трейдерами — смешанные сигналы"

        hot = [s["text"] for s in signals if s["bias"] in ("bullish", "accumulate")][:3]
        warns = [s["text"] for s in signals if s["bias"] in ("caution", "defensive")][:3]

        return {
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "recommendation": rec,
            "confidence": 0.55 + min(0.3, len(bullish) * 0.05),
            "action_for_brain": f"Учесть {len(TRACKED_TRADERS)} публичных стилей трейдинга",
            "signals": signals[:8],
            "hot": hot,
            "warnings": warns,
            "tracked_count": len(TRACKED_TRADERS),
        }
