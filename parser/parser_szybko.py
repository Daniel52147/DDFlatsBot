"""
Szybko.pl parser — Polish real estate aggregator, datacenter-friendly.
Uses JSON-LD + HTML card fallback. Replaces broken OLX.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

SZYBKO_BASE = "https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.szybko.pl/",
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


def _parse_json_ld(html: str) -> list:
    results = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        # ItemList pattern
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
                image = item.get("image") or ""
                if isinstance(image, list):
                    image = image[0] if image else ""
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": None, "area": None, "floor": None, "furnished": 0,
                    "link": url, "image": image, "source": "Szybko",
                })

        # offers.offers pattern
        top = data.get("offers", {})
        if isinstance(top, dict):
            for offer in top.get("offers", []):
                if not isinstance(offer, dict):
                    continue
                name = (offer.get("name") or "").strip()
                url = offer.get("url") or ""
                if not name or not url or len(name) < 10:
                    continue
                price = _price(offer.get("price", 0))
                image = offer.get("image") or ""
                if isinstance(image, list):
                    image = image[0] if image else ""
                district = "Warszawa"
                io = offer.get("itemOffered") or {}
                if isinstance(io, dict):
                    addr = io.get("address") or {}
                    if isinstance(addr, dict):
                        district = addr.get("addressLocality") or "Warszawa"
                rooms = None
                rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', name, re.I)
                if rm:
                    rooms = int(rm.group(1))
                area = None
                am = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', name)
                if am:
                    try:
                        area = float(am.group(1).replace(",", "."))
                    except Exception:
                        pass
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": rooms, "area": area, "floor": None, "furnished": 0,
                    "link": url, "image": image, "source": "Szybko",
                })
    return results


def _parse_html_cards(html: str) -> list:
    results = []
    # Try article tags first
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    if not articles:
        # Fallback: div with offer/listing class
        articles = re.findall(
            r'<div[^>]*class="[^"]*(?:offer|listing|property|item)[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL | re.IGNORECASE
        )
    for article in articles:
        try:
            url_m = re.search(r'href="(https://(?:www\.)?szybko\.pl/[^"]{10,})"', article)
            if not url_m:
                continue
            url = url_m.group(1)
            title_m = (
                re.search(r'<(?:h2|h3)[^>]*>([^<]{5,120})<', article, re.I) or
                re.search(r'title="([^"]{10,120})"', article)
            )
            if not title_m:
                continue
            title = title_m.group(1).strip()
            price = 0
            pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', article, re.I)
            if pm:
                price = _price(pm.group(1))
            district = "Warszawa"
            lm = re.search(r'<[^>]*class="[^"]*(?:location|address|city)[^"]*"[^>]*>([^<]{3,60})<', article, re.I)
            if lm:
                district = lm.group(1).strip()
            rooms = None
            rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
            if rm:
                rooms = int(rm.group(1))
            # Image
            img_m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', article, re.I)
            image = img_m.group(1) if img_m else ""
            results.append({
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": image, "source": "Szybko",
            })
        except Exception:
            continue
    return results


def parse_szybko() -> list:
    results = []
    seen = set()
    session = _session()

    for page in range(1, 6):
        url = SZYBKO_BASE if page == 1 else f"{SZYBKO_BASE}?page={page}"
        try:
            r = session.get(url, timeout=25)
            html = r.text
            print(f"[Szybko] Page {page} status={r.status_code} size={len(html)}")

            if r.status_code == 404:
                print(f"[Szybko] 404 — site may have changed URL structure")
                break
            if r.status_code != 200:
                print(f"[Szybko] Blocked (status {r.status_code})")
                break

            page_results = _parse_json_ld(html)
            if not page_results:
                page_results = _parse_html_cards(html)

            new = 0
            for apt in page_results:
                if apt["link"] not in seen:
                    seen.add(apt["link"])
                    results.append(apt)
                    new += 1

            print(f"[Szybko] Page {page}: {new} listings")
            if new == 0 and page >= 2:
                break

            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Szybko] Page {page} error: {e}")
            break

    print(f"[Szybko] Found {len(results)} listings")
    return results
