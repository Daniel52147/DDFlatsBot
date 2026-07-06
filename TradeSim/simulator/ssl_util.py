"""SSL helpers for Windows Python (CERTIFICATE_VERIFY_FAILED fix)."""

from __future__ import annotations

import ssl


def ca_bundle() -> str | bool:
    try:
        import certifi
        return certifi.where()
    except ImportError:
        return True


def ssl_context() -> ssl.SSLContext:
    bundle = ca_bundle()
    if isinstance(bundle, str):
        return ssl.create_default_context(cafile=bundle)
    return ssl.create_default_context()


def http_verify() -> str | bool:
    return ca_bundle()
