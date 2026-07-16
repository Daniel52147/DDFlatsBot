"""API authentication and rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Callable

from fastapi import Header, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import config

WRITE_PREFIXES = (
    "/api/deposit",
    "/api/withdraw",
    "/api/live-prep/",
    "/api/wallet/",
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
    "/api/protections/clear",
    "/api/telegram/test",
    "/api/orders/cancel",
    "/api/smoke-test",
)

# Public — token check only, no write side effects
AUTH_CHECK_PATHS = ("/api/auth/verify",)

RATE_LIMITS: dict[str, tuple[int, float]] = {
    "/api/backtest": (10, 60.0),
    "/api/bootstrap": (30, 60.0),
    "/api/assistant/chat": (40, 60.0),
    "/api/export/trades": (20, 60.0),
    "/api/webhook/tradingview": (30, 60.0),
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

# Back-compat for tests patching security.API_TOKEN
API_TOKEN: str = ""


def current_api_token() -> str:
    """Fresh token from config (.env), whitespace stripped."""
    return (getattr(config, "API_TOKEN", "") or "").strip()


def auth_required() -> bool:
    return bool(current_api_token())


def token_valid(token: str | None) -> bool:
    expected = current_api_token()
    if not expected:
        return True
    got = (token or "").strip()
    return bool(got) and got == expected


def ws_token_from_scope(scope: dict) -> str | None:
    query = scope.get("query_string", b"").decode()
    for part in query.split("&"):
        if part.startswith("token="):
            return part[6:]
    return None


def require_exposure_auth(bind_host: str) -> None:
    """Refuse public bind without API token."""
    if bind_host == "0.0.0.0" and not current_api_token():
        raise SystemExit(
            "TRADESIM_API_TOKEN обязателен при TRADESIM_BIND_HOST=0.0.0.0 — "
            "задай токен в .env или слушай 127.0.0.1"
        )


def is_loopback_ip(ip: str | None) -> bool:
    if not ip:
        return False
    ip = ip.strip().lower()
    if ip in ("127.0.0.1", "::1", "localhost"):
        return True
    if ip.startswith("127."):
        return True
    return False


def write_auth_exempt(request: Request) -> bool:
    """PC localhost — кнопки без токена; телефон/LAN — нужен X-API-Token."""
    if not current_api_token():
        return True
    return is_loopback_ip(client_ip(request))


def require_write_auth(x_api_token: str | None = Header(None, alias="X-API-Token")) -> None:
    if not current_api_token():
        return
    if not token_valid(x_api_token):
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
                    if current_api_token() and not write_auth_exempt(request):
                        header = (request.headers.get("x-api-token") or "").strip()
                        if not token_valid(header):
                            return Response(
                                '{"error":"401 — нужен X-API-Token (тот же что TRADESIM_API_TOKEN в .env)"}',
                                status_code=401,
                                media_type="application/json",
                            )
        return await call_next(request)
