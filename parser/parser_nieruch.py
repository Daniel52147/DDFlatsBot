"""
nieruchomosci-online.pl + domiporta.pl parsers.
These sites don't block Render/datacenter IPs — good OLX replacement.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

NIERUCH_BASE = "https://www.nieruchomosci-online.pl/szukaj.html"
DOMIPORTA_BASE = "https://www.domiporta.pl/mieszkanie/wynajme/mazowieckie/warszawa"


def _session(referer: str):
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _price(val) -> int:
    if not val:
        return 0
    try:
        return int(float(str(val).replace(",", ".")))
    except Exception:
        digits = "".join(c for c in str(val) if c.isdigit())
        return int(digits) if digits else 0


# ── nieruchomosci-online.pl ───────────────────────────────────

def _parse_nieruch_page(html: str, source: str = "Nieruch-online") -> list:
    results = []

    # Try JSON-LD first
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
            if not isinstance(data, dict):
                continue
            if data.get("@type") == "ItemList":
                for el in data.get("itemListElement", []):
                    item = el.get("item", el) if isinstance(el, dict) else {}
                    name = (item.get("name") or "").strip()
                    url = item.get("url") or ""
                    if not name or not url or len(name) < 10:
                        continue
                    price_spec = item.get("offers") or {}
                    price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                    addr = item.get("address") or {}
                    district = (addr.get("addressLocality") or "Warszawa") if isinstance(addr, dict) else "Warszawa"
                    img = item.get("image") or ""
                    if isinstance(img, list):
                        img = img[0] if img else ""
                    results.append({
                        "title": name, "price": price, "district": district,
                        "rooms": None, "area": None, "floor": None, "furnished": 0,
                        "link": url, "image": img, "source": source,
                    })
        except Exception:
            continue

    if results:
        return results

    # HTML card fallback
    cards = re.findall(
        r'<(?:article|li|div)[^>]*class="[^"]*(?:listing|offer|property|item|estate)[^"]*"[^>]*>(.*?)</(?:article|li|div)>',
        html, re.DOTALL | re.IGNORECASE
    )
    for card in cards:
        try:
            url_m = re.search(r'href="(https?://[^"]+nieruchomosci-online[^"]+)"', card)
            if not url_m:
                continue
            url = url_m.group(1)
            title_m = re.search(r'<(?:h2|h3|h4|a)[^>]*>([^<]{10,120})<', card, re.I)
            if not title_m:
                continue
            title = title_m.group(1).strip()
            price = 0
            pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', card, re.I)
            if pm:
                price = _price(pm.group(1))
            results.append({
                "title": title, "price": price, "district": "Warszawa",
                "rooms": None, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": "", "source": source,
            })
        except Exception:
            continue
    return results


def parse_nieruch_online() -> list:
    results = []
    seen = set()
    session = _session("https://www.nieruchomosci-online.pl/")

    params = {
        "transaction": "2",   # wynajem
        "category": "1",      # mieszkania
        "city_id": "26",      # Warszawa
        "sort": "date_desc",
        "page": 1,
    }
    for page in range(1, 6):
        params["page"] = page
        try:
            r = session.get(NIERUCH_BASE, params=params, timeout=25)
            print(f"[Nieruch-online] Page {page} status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                print(f"[Nieruch-online] Blocked (status {r.status_code})")
                break
            page_results = _parse_nieruch_page(r.text, source="Nieruch-online")
            new = 0
            for apt in page_results:
                if apt["link"] not in seen:
                    seen.add(apt["link"])
                    results.append(apt)
                    new += 1
            print(f"[Nieruch-online] Page {page}: {new} listings")
            if new == 0:
                break
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Nieruch-online] Page {page} error: {e}")
            break

    print(f"[Nieruch-online] Found {len(results)} listings")
    return results


# ── domiporta.pl ──────────────────────────────────────────────

def _parse_domiporta_page(html: str) -> list:
    results = []

    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
            if not isinstance(data, dict):
                continue
            if data.get("@type") == "ItemList":
                for el in data.get("itemListElement", []):
                    item = el.get("item", el) if isinstance(el, dict) else {}
                    name = (item.get("name") or "").strip()
                    url = item.get("url") or ""
                    if not name or not url or len(name) < 10:
                        continue
                    price_spec = item.get("offers") or {}
                    price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                    addr = item.get("address") or {}
                    district = (addr.get("addressLocality") or "Warszawa") if isinstance(addr, dict) else "Warszawa"
                    results.append({
                        "title": name, "price": price, "district": district,
                        "rooms": None, "area": None, "floor": None, "furnished": 0,
                        "link": url, "image": "", "source": "Domiporta",
                    })
        except Exception:
            continue

    if results:
        return results

    # HTML fallback
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    for article in articles:
        try:
            url_m = re.search(r'href="(https://www\.domiporta\.pl/[^"]+)"', article)
            if not url_m:
                continue
            url = url_m.group(1)
            title_m = re.search(r'<(?:h2|h3)[^>]*>([^<]{5,120})<', article, re.I)
            if not title_m:
                continue
            title = title_m.group(1).strip()
            price = 0
            pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', article, re.I)
            if pm:
                price = _price(pm.group(1))
            img_m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', article, re.I)
            image = img_m.group(1) if img_m else ""
            results.append({
                "title": title, "price": price, "district": "Warszawa",
                "rooms": None, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": image, "source": "Domiporta",
            })
        except Exception:
            continue
    return results


def parse_domiporta() -> list:
    results = []
    seen = set()
    session = _session("https://www.domiporta.pl/")

    # Sort by newest
    sort_urls = [
        f"{DOMIPORTA_BASE}?sort=DateDesc",
        f"{DOMIPORTA_BASE}?sort=PriceAsc",
    ]

    for base_url in sort_urls:
        for page in range(1, 4):
            url = base_url if page == 1 else f"{base_url}&PageNumber={page}"
            try:
                r = session.get(url, timeout=25)
                print(f"[Domiporta] Page {page} status={r.status_code} size={len(r.text)}")
                if r.status_code != 200:
                    print(f"[Domiporta] Blocked (status {r.status_code})")
                    break
                page_results = _parse_domiporta_page(r.text)
                new = 0
                for apt in page_results:
                    if apt["link"] not in seen:
                        seen.add(apt["link"])
                        results.append(apt)
                        new += 1
                print(f"[Domiporta] Page {page}: {new} listings")
                if new == 0:
                    break
                time.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                print(f"[Domiporta] Page {page} error: {e}")
                break

    print(f"[Domiporta] Found {len(results)} listings")
    return results
