"""
Shared retry + session utilities for all parsers.
"""
import random
import time
import requests
from config import USER_AGENTS

# Realistic browser headers that rotate per request
_ACCEPT_LANGS = [
    "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "pl-PL,pl;q=0.9,en;q=0.8",
    "pl,en-US;q=0.9,en;q=0.8",
]

_ACCEPT_ENCODINGS = [
    "gzip, deflate, br",
    "gzip, deflate",
    "gzip, deflate, br, zstd",
]


def make_session(referer: str = "", close: bool = False) -> requests.Session:
    """Create a session with realistic browser headers."""
    s = requests.Session()
    # Rotate between different browser fingerprints
    ua = random.choice(USER_AGENTS)
    # Detect browser type from UA for consistent headers
    is_firefox = "Firefox" in ua
    is_safari  = "Safari" in ua and "Chrome" not in ua

    if is_firefox:
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        sec_ch  = {}
    elif is_safari:
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        sec_ch  = {}
    else:  # Chrome
        accept = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
        sec_ch  = {
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
        }

    headers = {
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": random.choice(_ACCEPT_LANGS),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "close" if close else "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none" if not referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "DNT": "1",
    }
    headers.update(sec_ch)
    if referer:
        headers["Referer"] = referer

    s.headers.update(headers)
    return s


def fetch_with_retry(
    session: requests.Session,
    url: str,
    max_retries: int = 3,
    timeout: int = 25,
    backoff_base: float = 2.0,
    max_size: int = 400_000,
    warmup_url: str = "",
) -> tuple[int, str]:
    """
    Fetch URL with exponential backoff retry.
    warmup_url: if set, visit this URL first to warm up the session (simulate real navigation).
    Returns (status_code, html_text).
    """
    # Warm up session — visit homepage first like a real browser
    if warmup_url:
        try:
            session.get(warmup_url, timeout=10)
            time.sleep(random.uniform(0.5, 1.5))
            # Update Referer to look like we navigated from homepage
            session.headers["Referer"] = warmup_url
            session.headers["Sec-Fetch-Site"] = "same-origin"
        except Exception:
            pass

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                session.headers["User-Agent"] = random.choice(USER_AGENTS)
                wait = backoff_base ** attempt + random.uniform(0.5, 1.5)
                print(f"[Retry] attempt={attempt+1} url={url[:60]} wait={wait:.1f}s")
                time.sleep(wait)

            r = session.get(url, timeout=timeout)

            if r.status_code == 200:
                return 200, r.text[:max_size]

            if r.status_code in (403, 429, 503):
                wait = backoff_base ** (attempt + 1) + random.uniform(1.0, 3.0)
                print(f"[Retry] {r.status_code} on {url[:60]} — waiting {wait:.1f}s")
                time.sleep(wait)
                continue

            return r.status_code, ""

        except requests.exceptions.Timeout:
            print(f"[Retry] Timeout on {url[:60]} attempt={attempt+1}")
        except requests.exceptions.ConnectionError as e:
            print(f"[Retry] ConnectionError on {url[:60]}: {e}")
        except Exception as e:
            print(f"[Retry] Error on {url[:60]}: {e}")

    return 0, ""
