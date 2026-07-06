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
BYBIT_REST = "https://api.bybit.com/v5/market"


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
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            errors: list[str] = []
            for name, fetcher in (
                ("binance", self._fetch_binance),
                ("binance.us", self._fetch_binance_us),
                ("bybit", self._fetch_bybit),
                ("kraken", self._fetch_kraken),
                ("coingecko", self._fetch_coingecko),
            ):
                try:
                    price = await fetcher(client)
                    if price > 0:
                        return await self._set_price(price, name)
                except Exception as e:
                    errors.append(f"{name}: {e}")
                    logger.warning("price source %s failed: %s", name, e)
        raise RuntimeError("All price sources failed: " + "; ".join(errors))

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
        if data.get("error"):
            raise RuntimeError(data["error"])
        pair = self._kraken_pair_key(data["result"])
        return float(data["result"][pair]["c"][0])

    async def _fetch_bybit(self, client: httpx.AsyncClient) -> float:
        r = await client.get(
            f"{BYBIT_REST}/tickers",
            params={"category": "spot", "symbol": config.SYMBOL},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("retCode") != 0:
            raise RuntimeError(data.get("retMsg", "bybit error"))
        return float(data["result"]["list"][0]["lastPrice"])

    async def _fetch_coingecko(self, client: httpx.AsyncClient) -> float:
        r = await client.get(
            f"{COINGECKO_REST}/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
        )
        r.raise_for_status()
        return float(r.json()["bitcoin"]["usd"])

    @staticmethod
    def _kraken_pair_key(result: dict) -> str:
        for key in result:
            if key != "last":
                return key
        raise RuntimeError("kraken pair not found")

    async def fetch_klines(self, interval: str = "1m", limit: int = 100) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            errors: list[str] = []
            for name, fetcher in (
                ("binance", self._klines_binance),
                ("binance.us", self._klines_binance_us),
                ("bybit", self._klines_bybit),
                ("kraken", self._klines_kraken),
                ("coingecko", self._klines_coingecko),
            ):
                try:
                    candles = await fetcher(client, interval, limit)
                    if candles:
                        self.source = name
                        logger.info("Loaded %s candles from %s", len(candles), name)
                        return candles
                except Exception as e:
                    errors.append(f"{name}: {e}")
                    logger.warning("kline source %s failed: %s", name, e)

        try:
            price = await self.fetch_price()
            candles = self._synthetic_candles(price, limit)
            self.source = "synthetic"
            logger.warning(
                "All kline APIs failed (%s). Using synthetic candles from live price.",
                "; ".join(errors),
            )
            return candles
        except Exception as e:
            raise RuntimeError("All kline sources failed: " + "; ".join(errors)) from e

    def _synthetic_candles(self, price: float, limit: int) -> list[dict[str, Any]]:
        now = int(time.time())
        step = 60
        out = []
        for i in range(limit):
            t = now - (limit - i) * step
            p = price * (1 - 0.0001 * (limit - i))
            out.append({
                "time": t,
                "open": p,
                "high": p * 1.0002,
                "low": p * 0.9998,
                "close": p,
                "volume": 0.0,
            })
        out[-1]["close"] = price
        out[-1]["high"] = price
        out[-1]["low"] = price
        out[-1]["open"] = price
        return out

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
        if data.get("error"):
            raise RuntimeError(data["error"])
        pair = self._kraken_pair_key(data["result"])
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

    async def _klines_bybit(self, client: httpx.AsyncClient, interval: str, limit: int):
        bybit_interval = {"1m": "1", "5m": "5", "15m": "15", "1h": "60"}.get(interval, "1")
        r = await client.get(
            f"{BYBIT_REST}/kline",
            params={
                "category": "spot",
                "symbol": config.SYMBOL,
                "interval": bybit_interval,
                "limit": min(limit, 1000),
            },
        )
        r.raise_for_status()
        data = r.json()
        if data.get("retCode") != 0:
            raise RuntimeError(data.get("retMsg", "bybit kline error"))
        rows = list(reversed(data["result"]["list"]))
        candles = []
        for row in rows:
            candles.append({
                "time": int(row[0]) // 1000,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            })
        return candles

    async def _klines_coingecko(self, client: httpx.AsyncClient, interval: str, limit: int):
        days = 1 if interval in ("1m", "5m") else 7
        r = await client.get(
            f"{COINGECKO_REST}/coins/bitcoin/market_chart",
            params={"vs_currency": "usd", "days": str(days)},
        )
        r.raise_for_status()
        prices = r.json().get("prices", [])
        if len(prices) < 10:
            raise RuntimeError("coingecko returned too few points")
        # Group into ~1m buckets from tick data
        bucket_sec = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(interval, 60)
        buckets: dict[int, list[float]] = {}
        for ts_ms, price in prices:
            bucket = int(ts_ms // 1000 // bucket_sec) * bucket_sec
            buckets.setdefault(bucket, []).append(float(price))
        candles = []
        for t in sorted(buckets.keys())[-limit:]:
            pts = buckets[t]
            candles.append({
                "time": t,
                "open": pts[0],
                "high": max(pts),
                "low": min(pts),
                "close": pts[-1],
                "volume": 0.0,
            })
        return candles

    async def run_websocket(self):
        self._running = True
        while self._running:
            connected = False
            for runner in (self._ws_binance, self._ws_bybit, self._ws_kraken, self._poll_loop):
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
                if isinstance(msg, list) and len(msg) >= 4 and isinstance(msg[1], list):
                    trades = msg[1]
                    if trades:
                        price = float(trades[-1][0])
                        await self._set_price(price, "kraken-ws")
                        await self._notify(price, self.last_update)

    async def _ws_bybit(self):
        import websockets
        url = "wss://stream.bybit.com/v5/public/spot"
        async with websockets.connect(url, ping_interval=20) as ws:
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": [f"publicTrade.{config.SYMBOL}"],
            }))
            logger.info("Bybit WS connected")
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("topic", "").startswith("publicTrade") and msg.get("data"):
                    price = float(msg["data"][0]["p"])
                    await self._set_price(price, "bybit-ws")
                    await self._notify(price, self.last_update)

    async def _poll_loop(self):
        logger.info("Using REST polling fallback")
        while self._running:
            price = await self.fetch_price()
            await self._notify(price, self.last_update)
            await asyncio.sleep(5)

    def stop(self):
        self._running = False
