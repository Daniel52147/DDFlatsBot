"""API authentication and rate limiting."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Callable

from fastapi import Header, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import config

# Set TRADESIM_API_TOKEN in env to protect write endpoints when exposed beyond localhost.
API_TOKEN: str = os.environ.get("TRADESIM_API_TOKEN", getattr(config, "API_TOKEN", ""))

WRITE_PREFIXES = (
    "/api/deposit",
    "/api/reset",
    "/api/trade",
    "/api/exchange/",
    "/api/shadow-lab/reset",
    "/api/shadow-lab/apply",
    "/api/strategy/switch",
    "/api/strategy/preset",
    "/api/strategy/active",
    "/api/strategy/paper-learn",
    "/api/trading-mode",
    "/api/week-prep/start",
    "/api/sync-markets",
    "/api/market/sync-strategy",
    "/api/bot/toggle",
    "/api/backtest",
    "/api/assistant/chat",
)

RATE_LIMITS: dict[str, tuple[int, float]] = {
    "/api/backtest": (10, 60.0),
    "/api/bootstrap": (30, 60.0),
    "/api/assistant/chat": (40, 60.0),
    "/api/export/trades": (20, 60.0),
    "default": (120, 60.0),
}


class RateLimiter:
    def __init__(self):
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, path: str) -> bool:
        limit, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
        now = time.time()
        bucket = self._hits[key]
        bucket[:] = [t for t in bucket if now - t < window]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


rate_limiter = RateLimiter()


def auth_required() -> bool:
    return bool(API_TOKEN)


def token_valid(token: str | None) -> bool:
    if not API_TOKEN:
        return True
    return bool(token) and token == API_TOKEN


def ws_token_from_scope(scope: dict) -> str | None:
    query = scope.get("query_string", b"").decode()
    for part in query.split("&"):
        if part.startswith("token="):
            return part[6:]
    return None


def require_exposure_auth(bind_host: str) -> None:
    """Refuse public bind without API token."""
    if bind_host == "0.0.0.0" and not API_TOKEN:
        raise SystemExit(
            "TRADESIM_API_TOKEN обязателен при TRADESIM_BIND_HOST=0.0.0.0 — "
            "задай токен в .env или слушай 127.0.0.1"
        )


def require_write_auth(x_api_token: str | None = Header(None, alias="X-API-Token")) -> None:
    if not API_TOKEN:
        return
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Нужен заголовок X-API-Token")


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path.startswith("/api/"):
            ip = client_ip(request)
            if not rate_limiter.allow(f"{ip}:{path}", path):
                return Response(
                    '{"error":"rate limit — подожди минуту"}',
                    status_code=429,
                    media_type="application/json",
                )
            if request.method in ("POST", "PUT", "DELETE", "PATCH"):
                if any(path.startswith(p) for p in WRITE_PREFIXES):
                    if API_TOKEN and request.headers.get("x-api-token") != API_TOKEN:
                        return Response(
                            '{"error":"401 — нужен X-API-Token"}',
                            status_code=401,
                            media_type="application/json",
                        )
        return await call_next(request)
