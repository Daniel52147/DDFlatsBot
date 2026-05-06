"""
Morizon parser — __NEXT_DATA__ + JSON-LD + HTML cards + nieruchomosci-online fallback.
Uses retry with exponential backoff.
"""
import random
import re
import json
import time
from parser._retry import make_session, fetch_with_retry

MORIZON_BASE      = "https://www.morizon.pl/do-wynajecia/mieszkania/warszawa/?sort=newest"
MORIZON_PRICE_ASC = "https://www.morizon.pl/do-wynajecia/mieszkania/warszawa/?sort=price_from_lowest"
NIERUCH_BASE      = "https://www.nieruchomosci-online.pl/szukaj.html"


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


def _parse_next_data(html: str) -> list:
    results = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return results
    try:
        data = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})

        def find_items(obj, depth=0):
            if depth > 6:
                return []
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                if any(k in obj[0] for k in ("slug", "title", "url", "name")):
                    return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    found = find_items(v, depth + 1)
                    if found:
                        return found
            return []

        for item in find_items(page_props):
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("name") or "").strip()
            url   = item.get("url") or item.get("link") or item.get("slug") or ""
            if not title or len(title) < 5 or not url:
                continue
            if not url.startswith("http"):
                url = f"https://www.morizon.pl{url}"
            price    = _price(item.get("price") or item.get("totalPrice") or 0)
            district = str(item.get("district") or item.get("city") or "Warszawa")
            results.append({
                "title": title, "price": price, "district": district,
                "rooms": _rooms(title), "area": _area(title),
                "floor": None, "furnished": 0,
                "link": url, "image": "", "source": "Morizon",
            })
    except Exception as e:
        print(f"[Morizon] __NEXT_DATA__ error: {e}")
    return results


def _parse_json_ld(html: str) -> list:
    results = []
    blocks = re.findall(r'<script[^>]*ld\+json[^>]*>([^<]{10,80000})</script>', html)
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        top = data.get("offers", {})
        if isinstance(top, dict):
            for offer in top.get("offers", []):
                if not isinstance(offer, dict):
                    continue
                name = (offer.get("name") or "").strip()
                url  = offer.get("url") or ""
                if not name or len(name) < 8 or not url:
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
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": _rooms(name), "area": _area(name),
                    "floor": None, "furnished": 0,
                    "link": url, "image": str(image), "source": "Morizon",
                })
        if data.get("@type") == "ItemList":
            for el in data.get("itemListElement", []):
                item = el.get("item", el) if isinstance(el, dict) else {}
                name = (item.get("name") or "").strip()
                url  = item.get("url") or ""
                if not name or len(name) < 8 or not url:
                    continue
                price_spec = item.get("offers") or {}
                price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                results.append({
                    "title": name, "price": price, "district": "Warszawa",
                    "rooms": _rooms(name), "area": _area(name),
                    "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": "Morizon",
                })
    return results


def _parse_html_cards(html: str) -> list:
    results = []
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    for article in articles:
        try:
            url_m = re.search(r'href="(https://www\.morizon\.pl/oferta/[^"]+)"', article)
            if not url_m:
                continue
            url = url_m.group(1).split("?")[0]
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
            lm = re.search(r'class="[^"]*(?:location|address)[^"]*"[^>]*>([^<]{3,60})<', article, re.I)
            if lm:
                district = lm.group(1).strip() or "Warszawa"
            img_m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', article, re.I)
            image = img_m.group(1) if img_m else ""
            results.append({
                "title": title, "price": price, "district": district,
                "rooms": _rooms(title), "area": _area(title),
                "floor": None, "furnished": 0,
                "link": url, "image": image, "source": "Morizon",
            })
        except Exception:
            continue
    return results


def _parse_nieruch(html: str) -> list:
    results = []
    blocks = re.findall(r'<script[^>]*ld\+json[^>]*>([^<]{10,80000})</script>', html)
    for block in blocks:
        try:
            data = json.loads(block)
            if not isinstance(data, dict) or data.get("@type") != "ItemList":
                continue
            for el in data.get("itemListElement", []):
                item = el.get("item", el) if isinstance(el, dict) else {}
                name = (item.get("name") or "").strip()
                url  = item.get("url") or ""
                if not name or len(name) < 8 or not url:
                    continue
                price_spec = item.get("offers") or {}
                price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                addr = item.get("address") or {}
                district = (addr.get("addressLocality") or "Warszawa") if isinstance(addr, dict) else "Warszawa"
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": _rooms(name), "area": _area(name),
                    "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": "Morizon",
                })
        except Exception:
            continue
    return results


def parse_morizon() -> list:
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

    morizon_ok = False
    for base_url in [MORIZON_BASE, MORIZON_PRICE_ASC]:
        session = make_session(referer="https://www.morizon.pl/")
        for page in range(1, 4):
            url = base_url if page == 1 else f"{base_url}&page={page}"
            warmup = "https://www.morizon.pl/" if page == 1 else ""
            status, html = fetch_with_retry(session, url, max_retries=3, backoff_base=3.0, warmup_url=warmup)
            print(f"[Morizon] page={page} status={status} size={len(html)}")
            if status != 200:
                break
            items = _parse_next_data(html) or _parse_json_ld(html) or _parse_html_cards(html)
            new = add(items)
            print(f"[Morizon] page={page}: {new} new")
            if new > 0:
                morizon_ok = True
            elif page >= 2:
                break
            time.sleep(random.uniform(2.0, 3.5))

    if not morizon_ok:
        print("[Morizon] Trying nieruchomosci-online fallback...")
        session2 = make_session(referer="https://www.nieruchomosci-online.pl/")
        for page in range(1, 4):
            params = f"?transaction=2&category=1&city_id=26&page={page}"
            status, html = fetch_with_retry(session2, NIERUCH_BASE + params, max_retries=2)
            print(f"[Nieruch-online] page={page} status={status} size={len(html)}")
            if status != 200:
                break
            items = _parse_nieruch(html)
            new = add(items)
            print(f"[Nieruch-online] page={page}: {new} new")
            if new == 0 and page >= 2:
                break
            time.sleep(random.uniform(2.0, 3.0))

    print(f"[Morizon] Total: {len(results)}")
    return results
