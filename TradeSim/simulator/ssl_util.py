"""SSL helpers for Windows Python (CERTIFICATE_VERIFY_FAILED fix)."""

from __future__ import annotations

import logging
import os
import ssl

logger = logging.getLogger(__name__)

_insecure_ssl = False


def _env_insecure() -> bool:
    return os.environ.get("TRADESIM_INSECURE_SSL", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def use_insecure_ssl() -> bool:
    return _insecure_ssl or _env_insecure()


def enable_insecure_ssl():
    global _insecure_ssl
    if not _insecure_ssl:
        _insecure_ssl = True
        logger.warning(
            "SSL verify disabled for local dev (Windows workaround). "
            "Set TRADESIM_INSECURE_SSL=1 or install: pip install certifi pip-system-certs"
        )


def is_ssl_verify_error(msg: str) -> bool:
    m = msg.upper()
    return "CERTIFICATE_VERIFY_FAILED" in m or "SSL: CERTIFICATE" in m


def http_verify() -> str | bool:
    if use_insecure_ssl():
        return False
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return True


def ssl_context() -> ssl.SSLContext:
    if use_insecure_ssl():
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
