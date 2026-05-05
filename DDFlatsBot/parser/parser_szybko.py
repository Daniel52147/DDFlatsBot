"""
Szybko.pl parser — JSON-LD + HTML cards.
Uses close connection + retry to prevent hangs.
"""
import random
import re
import json
import time
from parser._retry import make_session, fetch_with_retry

SZYBKO_BASE  = "https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa"
SZYBKO_CHEAP = "https://www.szybko.pl/nieruchomosci/wynajem/mieszkania/warszawa?sort=price_asc"


def _price(val) -> int:
    if not val:
        return 0
    try:
        return int(float(str(val).replace(",", ".")))
    except Exception:
        digits = "".join(c for c in str(val) if c.isdigit())
        return int(digits) if digits else 0


def _rooms(text: str):
    m = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', text, re.I)
    return int(m.group(1)) if m else None


def _area(text: str):
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', text, re.I)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            pass
    return None


def _parse_json_ld(html: str) -> list:
    results = []
    for block in re.findall(r'<script[^>]*ld\+json[^>]*>([^<]{10,50000})</script>', html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        items = []
        if data.get("@type") == "ItemList":
            for el in data.get("itemListElement", []):
                items.append(el.get("item", el) if isinstance(el, dict) else {})
        top = data.get("offers", {})
        if isinstance(top, dict):
            items.extend(top.get("offers", []))
        for item in items:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            url  = item.get("url") or ""
            if not name or len(name) < 8 or not url:
                continue
            price_spec = item.get("offers") or {}
            price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else item.get("price", 0))
            addr = item.get("address") or {}
            district = (addr.get("addressLocality") or "Warszawa") if isinstance(addr, dict) else "Warszawa"
            image = item.get("image") or ""
            if isinstance(image, list):
                image = image[0] if image else ""
            results.append({
                "title": name, "price": price, "district": district,
                "rooms": _rooms(name), "area": _area(name),
                "floor": None, "furnished": 0,
                "link": url, "image": str(image), "source": "Szybko",
            })
    return results


def _parse_html_cards(html: str) -> list:
    results = []
    card_re = re.compile(r'<article[^>]*>|<div[^>]+class="[^"]*offer[^"]*"[^>]*>', re.I)
    positions = [m.start() for m in card_re.finditer(html)]
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else pos + 3000
        card = html[pos:end]
        url_m = re.search(r'href="(https://(?:www\.)?szybko\.pl/[^"]{15,})"', card)
        if not url_m:
            continue
        url = url_m.group(1).split("?")[0]
        title_m = (
            re.search(r'<h[23][^>]*>([^<]{8,120})<', card, re.I) or
            re.search(r'title="([^"]{8,120})"', card)
        )
        if not title_m:
            continue
        title = title_m.group(1).strip()
        price = 0
        pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', card, re.I)
        if pm:
            price = _price(pm.group(1).replace(" ", ""))
        district = "Warszawa"
        dm = re.search(r'class="[^"]*(?:location|address|city|district)[^"]*"[^>]*>([^<]{3,50})<', card, re.I)
        if dm:
            district = dm.group(1).strip() or "Warszawa"
        img_m = re.search(r'src="(https://mediaproxy\.szybko\.pl[^"]+)"', card)
        if not img_m:
            img_m = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"', card, re.I)
        image = img_m.group(1) if img_m else ""
        results.append({
            "title": title, "price": price, "district": district,
            "rooms": _rooms(title), "area": _area(title),
            "floor": None, "furnished": 0,
            "link": url, "image": image, "source": "Szybko",
        })
    return results


def parse_szybko() -> list:
    results = []
    seen = set()

    def add(items):
        n = 0
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)
                n += 1
        return n

    for base_url, label in [(SZYBKO_BASE, "newest"), (SZYBKO_CHEAP, "cheapest")]:
        # close=True prevents keep-alive hangs
        session = make_session(referer="https://www.szybko.pl/", close=True)
        for page in range(1, 5):
            url = base_url if page == 1 else f"{base_url}&page={page}"
            status, html = fetch_with_retry(session, url, max_retries=2, timeout=20, backoff_base=2.0)
            print(f"[Szybko-{label}] page={page} status={status} size={len(html)}")
            if status != 200:
                break
            items = _parse_json_ld(html) or _parse_html_cards(html)
            new = add(items)
            print(f"[Szybko-{label}] page={page}: {new} new")
            if new == 0 and page >= 2:
                break
            time.sleep(random.uniform(1.5, 2.5))

    print(f"[Szybko] Total: {len(results)}")
    return results
