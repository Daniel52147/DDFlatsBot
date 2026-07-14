"""LAN IP detection for phone / Telegram dashboard links."""

from __future__ import annotations

import socket


def detect_lan_ipv4() -> str | None:
    """Best-effort local network IPv4 (Wi‑Fi / Ethernet)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    try:
        host = socket.gethostname()
        ip = socket.gethostbyname(host)
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return None


def dashboard_url(
    *,
    public_url: str = "",
    port: int = 8765,
    prefer_lan: bool = True,
) -> str:
    """URL for Telegram /open — LAN IP on home Wi‑Fi, not 127.0.0.1."""
    if public_url:
        return public_url.rstrip("/")
    if prefer_lan:
        lan = detect_lan_ipv4()
        if lan:
            return f"http://{lan}:{port}"
    return f"http://127.0.0.1:{port}"
