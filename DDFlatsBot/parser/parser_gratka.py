"""
Gratka parser — uses their internal search API + JSON-LD fallback.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE = "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://gratka.pl/",
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


def _try_api(session) -> list:
    """Try Gratka's internal search API."""
    results = []
    try:
        # Gratka uses a search API endpoint
        api_url = "https://gratka.pl/api/search"
        params = {
            "category": "mieszkania",
            "transaction": "wynajem",
            "location": "warszawa",
            "page": 1,
            "limit": 48,
        }
        r = session.get(api_url, params=params, timeout=20)
        print(f"[Gratka] API status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("items") or data.get("offers") or data.get("data") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or item.get("name") or "").strip()
                url = item.get("url") or item.get("link") or ""
                if not title or not url:
                    continue
                results.append({
                    "title": title,
                    "price": _price(item.get("price") or item.get("totalPrice")),
                    "district": item.get("district") or item.get("city") or "Warszawa",
                    "rooms": None, "area": None, "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": "Gratka",
                })
    except Exception as e:
        print(f"[Gratka] API error: {e}")
    return results


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

        # Pattern: offers.offers list
        top = data.get("offers", {})
        if isinstance(top, dict):
            inner = top.get("offers", [])
            if isinstance(inner, list):
                for offer in inner:
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
                        "link": url, "image": image, "source": "Gratka",
                    })

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
                results.append({
                    "title": name, "price": price, "district": "Warszawa",
                    "rooms": None, "area": None, "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": "Gratka",
                })
    return results


def _parse_html_cards(html: str) -> list:
    """Extract listings from article cards."""
    results = []
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    for article in articles:
        try:
            url_m = re.search(r'href="(https://gratka\.pl/nieruchomosci/[^"]+)"', article)
            if not url_m or url_m.group(1).count("/") < 5:
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
            lm = re.search(r'<[^>]*class="[^"]*location[^"]*"[^>]*>([^<]{3,60})<', article, re.I)
            if lm:
                district = lm.group(1).strip()

            rooms = None
            rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
            if rm:
                rooms = int(rm.group(1))

            results.append({
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": "", "source": "Gratka",
            })
        except Exception:
            continue
    return results


def parse_gratka() -> list:
    results = []
    seen = set()
    session = _session()

    def add(items):
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)

    # Try API first
    api_results = _try_api(session)
    if api_results:
        add(api_results)
        print(f"[Gratka] API: {len(api_results)} listings")
        return results

    # Fallback: scrape pages
    for page in range(1, 6):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            r = session.get(url, timeout=25)
            html = r.text
            print(f"[Gratka] Page {page} status={r.status_code} size={len(html)}")

            page_results = _parse_json_ld(html)
            if page_results:
                add(page_results)
                print(f"[Gratka] Page {page} JSON-LD: {len(page_results)}")
                time.sleep(random.uniform(2, 3))
                continue

            page_results = _parse_html_cards(html)
            if page_results:
                add(page_results)
                print(f"[Gratka] Page {page} HTML: {len(page_results)}")
            else:
                print(f"[Gratka] Page {page}: 0. Snippet: {html[:200].replace(chr(10),' ')}")

            time.sleep(random.uniform(2, 3))
        except Exception as e:
            print(f"[Gratka] Page {page} error: {e}")

    print(f"[Gratka] Found {len(results)} listings")
    return results
