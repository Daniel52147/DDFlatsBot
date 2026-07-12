"""Multiplexed price feed — one WebSocket for all symbols."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import httpx

from simulator.feed import (
    BINANCE_US_WS,
    BINANCE_WS,
    _binance_com_geo_blocked,
    _mark_binance_com_blocked,
)
from simulator.ssl_util import ssl_context

logger = logging.getLogger(__name__)

_klines_cache: dict[tuple[str, str, int], tuple[float, list]] = {}
_KLINES_TTL = 45.0


class FeedHub:
    """Single combined Binance stream → dispatch to all registered feeds."""

    def __init__(self, symbols: list[str]):
        self.symbols = [s.upper() for s in symbols]
        self._feeds: dict[str, list] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._shared_client: httpx.AsyncClient | None = None

    def register(self, symbol: str, feed) -> None:
        sym = symbol.upper()
        self._feeds.setdefault(sym, []).append(feed)

    async def add_symbol(self, symbol: str, feed) -> None:
        """Register feed and hot-add symbol to multiplex WS."""
        sym = symbol.upper()
        if sym not in self.symbols:
            self.symbols.append(sym)
        self.register(sym, feed)
        if self._running:
            await self._restart_multiplex()

    register_symbol = add_symbol  # alias for sync-markets callers

    async def _restart_multiplex(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._running:
            self._task = asyncio.create_task(self._run_multiplex())

    def client(self) -> httpx.AsyncClient:
        if self._shared_client is None or self._shared_client.is_closed:
            self._shared_client = httpx.AsyncClient(timeout=15.0)
        return self._shared_client

    async def close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._shared_client and not self._shared_client.is_closed:
            await self._shared_client.aclose()

    def start(self) -> asyncio.Task:
        self._running = True
        self._task = asyncio.create_task(self._run_multiplex())
        return self._task

    async def _dispatch(self, symbol: str, price: float, source: str) -> None:
        for feed in self._feeds.get(symbol.upper(), []):
            await feed._set_price(price, source)
            await feed._notify(price, feed.last_update)

    async def _run_multiplex(self) -> None:
        import websockets

        streams = "/".join(f"{s.lower()}@trade" for s in self.symbols)
        bases = [BINANCE_US_WS.replace("/ws", ""), BINANCE_WS.replace("/ws", "")]
        if _binance_com_geo_blocked:
            bases = [bases[0], bases[1]]
        else:
            bases = [bases[1], bases[0]]

        while self._running:
            connected = False
            for base in bases:
                url = f"{base}/stream?streams={streams}"
                try:
                    async with websockets.connect(url, ping_interval=20, ssl=ssl_context()) as ws:
                        logger.info("FeedHub: multiplex WS (%d symbols) %s", len(self.symbols), base)
                        connected = True
                        async for raw in ws:
                            if not self._running:
                                break
                            msg = json.loads(raw)
                            data = msg.get("data") or msg
                            sym = (data.get("s") or "").upper()
                            if sym and "p" in data:
                                await self._dispatch(sym, float(data["p"]), "hub-binance-ws")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    err = str(e)
                    if "451" in err:
                        _mark_binance_com_blocked()
                    logger.warning("FeedHub multiplex failed (%s): %s", base, e)
            if self._running and not connected:
                await asyncio.sleep(5)


async def cached_klines(
    feed,
    interval: str = "1m",
    limit: int = 200,
) -> list[dict]:
    """Shared klines cache — avoids 17 parallel identical REST storms on startup."""
    key = (feed.symbol.upper(), interval, limit)
    now = time.time()
    hit = _klines_cache.get(key)
    if hit and now - hit[0] < _KLINES_TTL:
        return hit[1]
    candles = await feed.fetch_klines(interval=interval, limit=limit)
    _klines_cache[key] = (now, candles)
    return candles
