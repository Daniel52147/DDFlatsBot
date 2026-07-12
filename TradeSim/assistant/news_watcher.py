"""Agent 2: monitors crypto news RSS and sentiment."""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from simulator.ssl_util import http_verify, enable_insecure_ssl, use_insecure_ssl, is_ssl_verify_error

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]

BULLISH = ("surge", "rally", "record", "approval", "adoption", "inflow", "bull", "рост", "рекорд")
BEARISH = ("crash", "hack", "ban", "lawsuit", "sec", "drop", "fear", "паден", "запрет", "взлом")


class NewsWatcherAgent:
    """Watches headlines and reports mood to the central brain."""

    name = "Новостник"
    role = "news_watcher"
    emoji = "📰"

    def __init__(self):
        self.last_headlines: list[dict] = []
        self.last_fetch_ts = 0.0
        self.last_sentiment = "neutral"

    async def fetch_headlines(self, limit: int = 8) -> list[dict]:
        headlines = []
        verify = http_verify()

        async def _fetch(client: httpx.AsyncClient):
            nonlocal headlines
            for source, url in RSS_FEEDS:
                try:
                    r = await client.get(url, timeout=12)
                    r.raise_for_status()
                    root = ET.fromstring(r.text)
                    for item in root.iter("item"):
                        title_el = item.find("title")
                        if title_el is None or not title_el.text:
                            continue
                        title = title_el.text.strip()
                        headlines.append({"source": source, "title": title, "ts": time.time()})
                        if len(headlines) >= limit:
                            return
                except Exception as e:
                    logger.warning("RSS %s failed: %s", source, e)

        try:
            async with httpx.AsyncClient(verify=verify, follow_redirects=True) as client:
                await _fetch(client)
        except Exception as e:
            if not use_insecure_ssl() and is_ssl_verify_error(str(e)):
                enable_insecure_ssl()
                async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
                    await _fetch(client)

        self.last_headlines = headlines[:limit]
        self.last_fetch_ts = time.time()
        return self.last_headlines

    def _sentiment(self, headlines: list[dict]) -> str:
        if not headlines:
            return "neutral"
        text = " ".join(h["title"].lower() for h in headlines)
        bull = sum(1 for w in BULLISH if w in text)
        bear = sum(1 for w in BEARISH if w in text)
        if bear > bull + 1:
            return "bearish"
        if bull > bear + 1:
            return "bullish"
        return "neutral"

    async def analyze(self, contexts: list[dict], total: dict) -> dict[str, Any]:
        headlines = await self.fetch_headlines()
        sentiment = self._sentiment(headlines)
        self.last_sentiment = sentiment

        coin_mentions = {}
        for ctx in contexts:
            label = ctx["label"].lower()
            coin_mentions[ctx["label"]] = sum(
                1 for h in headlines if label in h["title"].lower()
            )

        warnings = []
        if sentiment == "bearish":
            warnings.append("Негативный фон в заголовках — осторожнее с DIP-покупками.")
        mentioned = [k for k, v in coin_mentions.items() if v > 0]
        if mentioned:
            warnings.append(f"В новостях упоминаются: {', '.join(mentioned)}.")

        recommendation = "hold"
        action = "Новостной фон нейтральный — боты работают по плану."
        if sentiment == "bearish":
            recommendation = "pause_dip"
            action = "Центральному мозгу: при медвежьих новостях не усиливать DIP."
        elif sentiment == "bullish":
            recommendation = "continue"
            action = "Позитивный фон — DCA в норме, DIP только по правилам."

        top_titles = [f"• {h['title'][:80]}" for h in headlines[:4]]
        summary = (
            f"Проверил {len(headlines)} заголовков. Настроение: {sentiment}. "
            f"Источники: CoinDesk, Cointelegraph."
        )

        return {
            "agent": self.role,
            "name": self.name,
            "emoji": self.emoji,
            "summary": summary,
            "sentiment": sentiment,
            "headlines": headlines[:6],
            "warnings": warnings,
            "recommendation": recommendation,
            "action_for_brain": action,
            "confidence": 0.7 if headlines else 0.3,
        }
