"""Real-time BTC/USDT price feed with multi-source fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Awaitable

import httpx

import config

logger = logging.getLogger(__name__)

BINANCE_REST = "https://api.binance.com/api/v3"
BINANCE_US_REST = "https://api.binance.us/api/v3"
BINANCE_WS = "wss://stream.binance.com:9443/ws"
KRAKEN_REST = "https://api.kraken.com/0/public"
KRAKEN_WS = "wss://ws.kraken.com"
COINGECKO_REST = "https://api.coingecko.com/api/v3"


class PriceFeed:
    def __init__(self):
        self.price: float = 0.0
        self.last_update: float = 0.0
        self.source: str = "unknown"
        self._running = False
        self._callbacks: list[Callable[[float, float], Awaitable[None]]] = []

    def on_tick(self, cb: Callable[[float, float], Awaitable[None]]):
        self._callbacks.append(cb)

    async def _notify(self, price: float, ts: float):
        for cb in self._callbacks:
            try:
                await cb(price, ts)
            except Exception:
                logger.exception("tick callback error")

    async def _set_price(self, price: float, source: str):
        self.price = price
        self.last_update = time.time()
        self.source = source
        return price

    async def fetch_price(self) -> float:
        async with httpx.AsyncClient(timeout=10) as client:
            for name, fetcher in (
                ("binance", self._fetch_binance),
                ("binance.us", self._fetch_binance_us),
                ("kraken", self._fetch_kraken),
                ("coingecko", self._fetch_coingecko),
            ):
                try:
                    price = await fetcher(client)
                    if price > 0:
                        return await self._set_price(price, name)
                except Exception as e:
                    logger.debug("%s price failed: %s", name, e)
        raise RuntimeError("All price sources failed")

    async def _fetch_binance(self, client: httpx.AsyncClient) -> float:
        r = await client.get(f"{BINANCE_REST}/ticker/price", params={"symbol": config.SYMBOL})
        r.raise_for_status()
        return float(r.json()["price"])

    async def _fetch_binance_us(self, client: httpx.AsyncClient) -> float:
        r = await client.get(f"{BINANCE_US_REST}/ticker/price", params={"symbol": config.SYMBOL})
        r.raise_for_status()
        return float(r.json()["price"])

    async def _fetch_kraken(self, client: httpx.AsyncClient) -> float:
        r = await client.get(f"{KRAKEN_REST}/Ticker", params={"pair": "XBTUSDT"})
        r.raise_for_status()
        data = r.json()
        pair = list(data["result"].keys())[0]
        return float(data["result"][pair]["c"][0])

    async def _fetch_coingecko(self, client: httpx.AsyncClient) -> float:
        r = await client.get(
            f"{COINGECKO_REST}/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        r.raise_for_status()
        return float(r.json()["bitcoin"]["usd"])

    async def fetch_klines(self, interval: str = "1m", limit: int = 100) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            for name, fetcher in (
                ("binance", self._klines_binance),
                ("binance.us", self._klines_binance_us),
                ("kraken", self._klines_kraken),
            ):
                try:
                    candles = await fetcher(client, interval, limit)
                    if candles:
                        self.source = name
                        return candles
                except Exception as e:
                    logger.debug("%s klines failed: %s", name, e)
        raise RuntimeError("All kline sources failed")

    async def _klines_binance(self, client: httpx.AsyncClient, interval: str, limit: int):
        r = await client.get(
            f"{BINANCE_REST}/klines",
            params={"symbol": config.SYMBOL, "interval": interval, "limit": limit},
        )
        r.raise_for_status()
        return self._parse_binance_klines(r.json())

    async def _klines_binance_us(self, client: httpx.AsyncClient, interval: str, limit: int):
        r = await client.get(
            f"{BINANCE_US_REST}/klines",
            params={"symbol": config.SYMBOL, "interval": interval, "limit": limit},
        )
        r.raise_for_status()
        return self._parse_binance_klines(r.json())

    def _parse_binance_klines(self, rows: list) -> list[dict[str, Any]]:
        candles = []
        for row in rows:
            candles.append({
                "time": int(row[0] // 1000),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        return candles

    async def _klines_kraken(self, client: httpx.AsyncClient, interval: str, limit: int):
        kraken_interval = {"1m": 1, "5m": 5, "15m": 15, "1h": 60}.get(interval, 1)
        r = await client.get(
            f"{KRAKEN_REST}/OHLC",
            params={"pair": "XBTUSDT", "interval": kraken_interval},
        )
        r.raise_for_status()
        data = r.json()
        pair = list(data["result"].keys())[0]
        rows = data["result"][pair][-limit:]
        candles = []
        for row in rows:
            candles.append({
                "time": int(row[0]),
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[6]),
            })
        return candles

    async def run_websocket(self):
        self._running = True
        while self._running:
            connected = False
            for runner in (self._ws_binance, self._ws_kraken, self._poll_loop):
                if not self._running:
                    break
                try:
                    await runner()
                    connected = True
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning("feed runner failed: %s", e)
            if not connected and self._running:
                await asyncio.sleep(5)

    async def _ws_binance(self):
        import websockets
        errors = []
        for base in (BINANCE_WS, "wss://stream.binance.us:9443/ws"):
            url = f"{base}/{config.SYMBOL.lower()}@trade"
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    logger.info("WS connected: %s", url)
                    async for raw in ws:
                        msg = json.loads(raw)
                        price = float(msg["p"])
                        await self._set_price(price, "binance-ws")
                        await self._notify(price, self.last_update)
                    return
            except Exception as e:
                errors.append(str(e))
                logger.debug("binance ws %s failed: %s", base, e)
        raise ConnectionError("; ".join(errors) or "binance ws unavailable")

    async def _ws_kraken(self):
        import websockets
        async with websockets.connect(KRAKEN_WS, ping_interval=20) as ws:
            await ws.send(json.dumps({
                "event": "subscribe",
                "pair": ["XBT/USDT"],
                "subscription": {"name": "trade"},
            }))
            logger.info("Kraken WS connected")
            async for raw in ws:
                msg = json.loads(raw)
                if isinstance(msg, list) and len(msg) >= 4:
                    trades = msg[1]
                    if trades:
                        price = float(trades[-1][0])
                        await self._set_price(price, "kraken-ws")
                        await self._notify(price, self.last_update)

    async def _poll_loop(self):
        logger.info("Using REST polling fallback")
        while self._running:
            price = await self.fetch_price()
            await self._notify(price, self.last_update)
            await asyncio.sleep(5)

    def stop(self):
        self._running = False
