"""Real-time crypto price feed with multi-source fallback (per symbol)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Awaitable

import httpx

import config
from simulator.ssl_util import (
    enable_insecure_ssl,
    http_verify,
    is_ssl_verify_error,
    ssl_context,
    use_insecure_ssl,
)

logger = logging.getLogger(__name__)

BINANCE_REST = "https://api.binance.com/api/v3"
BINANCE_US_REST = "https://api.binance.us/api/v3"
BINANCE_WS = "wss://stream.binance.com:9443/ws"
BINANCE_US_WS = "wss://stream.binance.us:9443/ws"
KRAKEN_REST = "https://api.kraken.com/0/public"
KRAKEN_WS = "wss://ws.kraken.com"
COINGECKO_REST = "https://api.coingecko.com/api/v3"
BYBIT_REST = "https://api.bybit.com/v5/market"

# Per-symbol aliases for sources that do not use Binance-style tickers.
_ASSET: dict[str, dict[str, str]] = {
    "BTCUSDT": {"kraken": "XBTUSDT", "kraken_ws": "XBT/USDT", "coingecko": "bitcoin"},
    "ETHUSDT": {"kraken": "ETHUSDT", "kraken_ws": "ETH/USDT", "coingecko": "ethereum"},
    "SOLUSDT": {"kraken": "SOLUSDT", "kraken_ws": "SOL/USDT", "coingecko": "solana"},
    "BNBUSDT": {"kraken": "BNBUSDT", "kraken_ws": "BNB/USDT", "coingecko": "binancecoin"},
    "DOGEUSDT": {"coingecko": "dogecoin"},
    "PEPEUSDT": {"coingecko": "pepe"},
    "XRPUSDT": {"coingecko": "ripple"},
    "ADAUSDT": {"coingecko": "cardano"},
    "AVAXUSDT": {"coingecko": "avalanche-2"},
    "LINKUSDT": {"coingecko": "chainlink"},
    "ARBUSDT": {"coingecko": "arbitrum"},
    "SUIUSDT": {"coingecko": "sui"},
    "NEARUSDT": {"coingecko": "near"},
    "DOTUSDT": {"coingecko": "polkadot"},
    "INJUSDT": {"coingecko": "injective-protocol"},
    "TONUSDT": {"coingecko": "the-open-network"},
    "WIFUSDT": {"coingecko": "dogwifcoin"},
}

# api.binance.com returns HTTP 451 from some regions (e.g. Cursor Cloud VM).
_binance_com_geo_blocked = False
_binance_com_blocked_logged = False


def _mark_binance_com_blocked() -> None:
    global _binance_com_geo_blocked, _binance_com_blocked_logged
    _binance_com_geo_blocked = True
    if not _binance_com_blocked_logged:
        _binance_com_blocked_logged = True
        logger.info(
            "api.binance.com geo-blocked (HTTP 451); skipping it — "
            "using binance.us, bybit, kraken, coingecko"
        )


def _is_binance_geo_block(response: httpx.Response) -> bool:
    return response.status_code == 451


class BinanceGeoBlocked(Exception):
    """api.binance.com unavailable in this region (HTTP 451)."""


class PriceFeed:
    def __init__(self, symbol: str | None = None):
        self.symbol = symbol or config.SYMBOL
        self.price: float = 0.0
        self.last_update: float = 0.0
        self.source: str = "unknown"
        self._running = False
        self._callbacks: list[Callable[[float, float], Awaitable[None]]] = []

    def _asset(self, key: str) -> str:
        try:
            return _ASSET[self.symbol][key]
        except KeyError as e:
            raise RuntimeError(f"unsupported symbol for {key}: {self.symbol}") from e

    def _has_kraken(self) -> bool:
        return self.symbol in _ASSET and "kraken" in _ASSET[self.symbol]

    def on_tick(self, cb: Callable[[float, float], Awaitable[None]]):
        self._callbacks.append(cb)

    def _client(self, timeout: float = 15) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=http_verify(),
        )

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
        try:
            return await self._fetch_price_once()
        except RuntimeError as e:
            if not use_insecure_ssl() and is_ssl_verify_error(str(e)):
                enable_insecure_ssl()
                logger.info("Retrying price fetch without SSL verify...")
                return await self._fetch_price_once()
            raise

    async def _fetch_price_once(self) -> float:
        async with self._client(timeout=15) as client:
            errors: list[str] = []
            for name, fetcher in self._price_sources():
                try:
                    price = await fetcher(client)
                    if price > 0:
                        return await self._set_price(price, name)
                except BinanceGeoBlocked:
                    errors.append(f"{name}: geo-blocked")
                except Exception as e:
                    errors.append(f"{name}: {e}")
                    logger.warning("price source %s failed: %s", name, e)
        raise RuntimeError("All price sources failed: " + "; ".join(errors))

    def _price_sources(self):
        sources = [
            ("binance", self._fetch_binance),
            ("binance.us", self._fetch_binance_us),
            ("bybit", self._fetch_bybit),
        ]
        if self._has_kraken():
            sources.append(("kraken", self._fetch_kraken))
        sources.append(("coingecko", self._fetch_coingecko))
        if _binance_com_geo_blocked:
            sources = [s for s in sources if s[0] != "binance"]
        return sources

    def _kline_sources(self):
        sources = [
            ("binance", self._klines_binance),
            ("binance.us", self._klines_binance_us),
            ("bybit", self._klines_bybit),
        ]
        if self._has_kraken():
            sources.append(("kraken", self._klines_kraken))
        sources.append(("coingecko", self._klines_coingecko))
        if _binance_com_geo_blocked:
            sources = [s for s in sources if s[0] != "binance"]
        return sources

    async def _fetch_binance(self, client: httpx.AsyncClient) -> float:
        if _binance_com_geo_blocked:
            raise BinanceGeoBlocked()
        r = await client.get(f"{BINANCE_REST}/ticker/price", params={"symbol": self.symbol})
        if _is_binance_geo_block(r):
            _mark_binance_com_blocked()
            raise BinanceGeoBlocked()
        r.raise_for_status()
        return float(r.json()["price"])

    async def _fetch_binance_us(self, client: httpx.AsyncClient) -> float:
        r = await client.get(f"{BINANCE_US_REST}/ticker/price", params={"symbol": self.symbol})
        r.raise_for_status()
        return float(r.json()["price"])

    async def _fetch_kraken(self, client: httpx.AsyncClient) -> float:
        pair = self._asset("kraken")
        r = await client.get(f"{KRAKEN_REST}/Ticker", params={"pair": pair})
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        pair_key = self._kraken_pair_key(data["result"])
        return float(data["result"][pair_key]["c"][0])

    async def _fetch_bybit(self, client: httpx.AsyncClient) -> float:
        r = await client.get(
            f"{BYBIT_REST}/tickers",
            params={"category": "spot", "symbol": self.symbol},
        )
        r.raise_for_status()
        data = r.json()
        if data.get("retCode") != 0:
            raise RuntimeError(data.get("retMsg", "bybit error"))
        return float(data["result"]["list"][0]["lastPrice"])

    async def _fetch_coingecko(self, client: httpx.AsyncClient) -> float:
        coin_id = self._asset("coingecko")
        r = await client.get(
            f"{COINGECKO_REST}/simple/price",
            params={"ids": coin_id, "vs_currencies": "usd"},
        )
        r.raise_for_status()
        return float(r.json()[coin_id]["usd"])

    @staticmethod
    def _kraken_pair_key(result: dict) -> str:
        for key in result:
            if key != "last":
                return key
        raise RuntimeError("kraken pair not found")

    async def fetch_klines(self, interval: str = "1m", limit: int = 100) -> list[dict[str, Any]]:
        errors: list[str] = []
        for attempt in range(2):
            async with self._client(timeout=20) as client:
                for name, fetcher in self._kline_sources():
                    try:
                        candles = await fetcher(client, interval, limit)
                        if candles:
                            self.source = name
                            logger.info("Loaded %s candles from %s", len(candles), name)
                            return candles
                    except BinanceGeoBlocked:
                        errors.append(f"{name}: geo-blocked")
                    except Exception as e:
                        errors.append(f"{name}: {e}")
                        logger.warning("kline source %s failed: %s", name, e)

            err_text = "; ".join(errors)
            if attempt == 0 and not use_insecure_ssl() and is_ssl_verify_error(err_text):
                enable_insecure_ssl()
                logger.info("Retrying klines fetch without SSL verify...")
                errors.clear()
                continue
            break

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

    async def fetch_klines_since(
        self,
        interval: str = "1m",
        since_ts: int | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch candles from since_ts (seconds) — fills gaps after downtime."""
        if since_ts is None:
            return await self.fetch_klines(interval=interval, limit=limit)
        errors: list[str] = []
        since_ms = int(since_ts) * 1000
        for attempt in range(2):
            async with self._client(timeout=25) as client:
                if not _binance_com_geo_blocked:
                    try:
                        r = await client.get(
                            f"{BINANCE_REST}/klines",
                            params={
                                "symbol": self.symbol,
                                "interval": interval,
                                "startTime": since_ms,
                                "limit": min(limit, 1000),
                            },
                        )
                        if _is_binance_geo_block(r):
                            _mark_binance_com_blocked()
                        else:
                            r.raise_for_status()
                            candles = self._parse_binance_klines(r.json())
                            if candles:
                                self.source = "binance-gap"
                                return candles
                    except BinanceGeoBlocked:
                        errors.append("binance: geo-blocked")
                    except Exception as e:
                        errors.append(f"binance: {e}")
                try:
                    r = await client.get(
                        f"{BINANCE_US_REST}/klines",
                        params={
                            "symbol": self.symbol,
                            "interval": interval,
                            "startTime": since_ms,
                            "limit": min(limit, 1000),
                        },
                    )
                    r.raise_for_status()
                    candles = self._parse_binance_klines(r.json())
                    if candles:
                        self.source = "binance.us-gap"
                        return candles
                except Exception as e:
                    errors.append(f"binance.us: {e}")
            if attempt == 0 and not use_insecure_ssl() and is_ssl_verify_error("; ".join(errors)):
                enable_insecure_ssl()
                errors.clear()
                continue
            break
        full = await self.fetch_klines(interval=interval, limit=limit)
        return [c for c in full if c["time"] >= since_ts]

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
        if _binance_com_geo_blocked:
            raise BinanceGeoBlocked()
        r = await client.get(
            f"{BINANCE_REST}/klines",
            params={"symbol": self.symbol, "interval": interval, "limit": limit},
        )
        if _is_binance_geo_block(r):
            _mark_binance_com_blocked()
            raise BinanceGeoBlocked()
        r.raise_for_status()
        return self._parse_binance_klines(r.json())

    async def _klines_binance_us(self, client: httpx.AsyncClient, interval: str, limit: int):
        r = await client.get(
            f"{BINANCE_US_REST}/klines",
            params={"symbol": self.symbol, "interval": interval, "limit": limit},
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
        pair = self._asset("kraken")
        r = await client.get(
            f"{KRAKEN_REST}/OHLC",
            params={"pair": pair, "interval": kraken_interval},
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
                "symbol": self.symbol,
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
        coin_id = self._asset("coingecko")
        days = 1 if interval in ("1m", "5m") else 7
        r = await client.get(
            f"{COINGECKO_REST}/coins/{coin_id}/market_chart",
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
        bases = [BINANCE_US_WS, BINANCE_WS] if _binance_com_geo_blocked else [BINANCE_WS, BINANCE_US_WS]
        for base in bases:
            url = f"{base}/{self.symbol.lower()}@trade"
            try:
                async with websockets.connect(url, ping_interval=20, ssl=ssl_context()) as ws:
                    logger.info("WS connected: %s", url)
                    async for raw in ws:
                        msg = json.loads(raw)
                        price = float(msg["p"])
                        await self._set_price(price, "binance-ws")
                        await self._notify(price, self.last_update)
                    return
            except Exception as e:
                err = str(e)
                if "451" in err or "Unavailable For Legal Reasons" in err:
                    _mark_binance_com_blocked()
                errors.append(err)
                logger.debug("binance ws %s failed: %s", base, e)
        raise ConnectionError("; ".join(errors) or "binance ws unavailable")

    async def _ws_kraken(self):
        import websockets
        pair = self._asset("kraken_ws")
        async with websockets.connect(KRAKEN_WS, ping_interval=20, ssl=ssl_context()) as ws:
            await ws.send(json.dumps({
                "event": "subscribe",
                "pair": [pair],
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
        async with websockets.connect(url, ping_interval=20, ssl=ssl_context()) as ws:
            await ws.send(json.dumps({
                "op": "subscribe",
                "args": [f"publicTrade.{self.symbol}"],
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
