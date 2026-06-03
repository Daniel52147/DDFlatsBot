"""
Otodom parser — __NEXT_DATA__ JSON extraction.
Pass 1: today's new listings (daysSinceCreated=1)
Pass 2: latest sort, multiple pages
Pass 3: price ascending sort for cheap listings
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE     = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa"
BASE_NEW = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?daysSinceCreated=1&by=LATEST&direction=DESC"
BASE_PRICE_ASC = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?by=PRICE&direction=ASC"
BASE_DIST = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa/{district}?by=LATEST&direction=DESC"

WARSAW_DISTRICTS = [
    "mokotow", "wola", "praga-poludnie", "praga-polnoc",
    "ursynow", "bielany", "zoliborz", "ochota",
    "targowek", "bemowo", "ursus", "wawer",
]

_ROOMS_MAP = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "MORE": 6}


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
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


def _parse_item(item: dict) -> dict | None:
    try:
        title = (item.get("title") or "").strip()
        if not title or len(title) < 5:
            return None

        slug   = item.get("slug") or ""
        apt_id = item.get("id")   or ""
        href   = item.get("href") or ""
        if href:
            link = f"https://www.otodom.pl{href}" if href.startswith("/") else href
        elif slug:
            link = f"https://www.otodom.pl/pl/oferta/{slug}"
        elif apt_id:
            link = f"https://www.otodom.pl/pl/oferta/{apt_id}"
        else:
            return None

        # Price — totalPrice is rent+admin fees, rentPrice is rent-only
        price = 0
        for pf in ("totalPrice", "rentPrice", "price"):
            pobj = item.get(pf)
            if pobj:
                price = _price(pobj.get("value") if isinstance(pobj, dict) else pobj)
                if price:
                    break

        # District — from reverseGeocoding.locations (district level) or address
        district = "Warszawa"
        loc = item.get("location") or {}
        if isinstance(loc, dict):
            rev = loc.get("reverseGeocoding") or {}
            if isinstance(rev, dict):
                locs = rev.get("locations") or []
                for level in ("district", "city_or_village"):
                    found = next(
                        (l.get("name") for l in locs
                         if isinstance(l, dict) and l.get("locationLevel") == level),
                        None
                    )
                    if found:
                        district = found
                        break
            if district == "Warszawa":
                addr = loc.get("address") or {}
                if isinstance(addr, dict):
                    d = addr.get("district") or {}
                    c = addr.get("city") or {}
                    district = (
                        (d.get("name") if isinstance(d, dict) else d) or
                        (c.get("name") if isinstance(c, dict) else c) or
                        "Warszawa"
                    )

        images = item.get("images") or []
        image  = ""
        if images and isinstance(images[0], dict):
            image = images[0].get("medium") or images[0].get("small") or ""

        # Rooms — Otodom uses string enum: ONE, TWO, THREE, FOUR, FIVE, MORE
        rooms = None
        r_val = item.get("roomsNumber") or item.get("rooms")
        if r_val:
            if isinstance(r_val, str) and r_val.upper() in _ROOMS_MAP:
                rooms = _ROOMS_MAP[r_val.upper()]
            else:
                try:
                    rooms = int(str(r_val).replace("+", ""))
                except Exception:
                    pass

        area = None
        try:
            a = item.get("areaInSquareMeters") or item.get("area")
            if a:
                area = float(a)
        except Exception:
            pass

        floor = None
        try:
            f = item.get("floorNumber") or item.get("floor")
            if f is not None:
                floor = int(f)
        except Exception:
            pass

        lat, lon = None, None
        if isinstance(loc, dict):
            coords = loc.get("coordinates") or {}
            if isinstance(coords, dict):
                lat = coords.get("latitude")
                lon = coords.get("longitude")

        return {
            "title": title, "price": price, "district": str(district),
            "rooms": rooms, "area": area, "floor": floor, "furnished": 0,
            "link": link, "image": image, "source": "Otodom",
            "lat": lat, "lon": lon,
        }
    except Exception:
        return None


def _extract_next_data(html: str) -> list:
    results = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return results
    try:
        data       = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})
        items = (
            page_props.get("data", {}).get("searchAds", {}).get("items") or
            page_props.get("searchAds", {}).get("items") or
            page_props.get("data", {}).get("listing", {}).get("items") or
            []
        )
        if not items:
            def _find(obj, depth=0):
                if depth > 6:
                    return []
                if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                    if "slug" in obj[0] or "title" in obj[0]:
                        return obj
                if isinstance(obj, dict):
                    for v in obj.values():
                        found = _find(v, depth + 1)
                        if found:
                            return found
                return []
            items = _find(page_props)
        for item in items:
            apt = _parse_item(item)
            if apt:
                results.append(apt)
    except Exception as e:
        print(f"[Otodom] __NEXT_DATA__ error: {e}")
    return results


def parse_otodom(city: str = "Warszawa") -> list:
    """Parse Otodom for the specified city."""
    from config import CITIES
    from database.db import get_conn
    from validation.integration import ValidationPipeline
    
    city_config = CITIES.get(city, CITIES["Warszawa"])
    city_url = city_config.get("url_otodom", "warszawa")
    
    print(f"[Otodom/{city}] Starting parse...")
    
    # Initialize validation pipeline
    conn = get_conn()
    pipeline = ValidationPipeline(conn)
    
    # Build URLs for this city
    base = f"https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/{city_url}"
    base_new = f"{base}?daysSinceCreated=1&by=LATEST&direction=DESC"
    base_price_asc = f"{base}?by=PRICE&direction=ASC"
    
    results = []
    seen    = set()
    session = _session()
    validated_count = 0
    rejected_count = 0

    def add(items):
        nonlocal validated_count, rejected_count
        n = 0
        for apt in items:
            apt["source_city"] = city
            if apt["link"] not in seen:
                seen.add(apt["link"])
                # Validate before adding to results
                validated_apt = pipeline.process_listing(apt, city)
                if validated_apt:
                    results.append(validated_apt)
                    validated_count += 1
                    n += 1
                else:
                    rejected_count += 1
        return n

    # ── Pass 1: today's new listings ─────────────────────────
    for page in range(1, 4):
        url = base_new if page == 1 else f"{base_new}&page={page}"
        try:
            r   = session.get(url, headers={"Accept": "text/html"}, timeout=25)
            print(f"[Otodom/{city}-new] page={page} status={r.status_code}")
            if r.status_code != 200:
                break
            new = add(_extract_next_data(r.text))
            print(f"[Otodom/{city}-new] page={page}: {new} new")
            if new == 0:
                break
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Otodom/{city}-new] page={page} error: {e}")
            break

    # ── Pass 2: latest sort, multiple pages ──────────────────
    for page in range(1, 6):
        url = base if page == 1 else f"{base}?page={page}"
        try:
            r = session.get(url, timeout=25)
            print(f"[Otodom/{city}] page={page} status={r.status_code}")
            if r.status_code != 200:
                break
            new = add(_extract_next_data(r.text))
            print(f"[Otodom/{city}] page={page}: {new} new")
            if new == 0 and page >= 2:
                break
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Otodom/{city}] page={page} error: {e}")
            break

    # ── Pass 3: price ascending ──────────────────────────────
    for page in range(1, 3):
        url = base_price_asc if page == 1 else f"{base_price_asc}&page={page}"
        try:
            r = session.get(url, timeout=25)
            if r.status_code != 200:
                break
            new = add(_extract_next_data(r.text))
            print(f"[Otodom/{city}-price] page={page}: {new} new")
            if new == 0:
                break
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Otodom/{city}-price] page={page} error: {e}")
            break

    conn.close()
    print(f"[Otodom/{city}] Total: {len(results)} (validated: {validated_count}, rejected: {rejected_count})")
    return results

