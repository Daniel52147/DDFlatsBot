"""
Otodom parser.
Pass 1: today's new listings (__NEXT_DATA__)
Pass 2: regular pages (__NEXT_DATA__ fallback)
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE          = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa"
BASE_NEW      = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?daysSinceCreated=1&by=LATEST&direction=DESC"


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

        # Price — totalPrice is the rent+admin, rentPrice is rent-only
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
                # Prefer district level, fallback to city
                for level in ("district", "city_or_village"):
                    found = next((l.get("name") for l in locs if isinstance(l, dict) and l.get("locationLevel") == level), None)
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

        # Images
        images = item.get("images") or []
        image  = ""
        if images and isinstance(images[0], dict):
            image = images[0].get("medium") or images[0].get("small") or ""

        # Rooms — Otodom uses string enum: ONE, TWO, THREE, FOUR, FIVE, MORE
        _rooms_map = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "MORE": 6}
        rooms = None
        r_val = item.get("roomsNumber") or item.get("rooms")
        if r_val:
            if isinstance(r_val, str) and r_val.upper() in _rooms_map:
                rooms = _rooms_map[r_val.upper()]
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

        return {
            "title": title, "price": price, "district": str(district),
            "rooms": rooms, "area": area, "floor": floor, "furnished": 0,
            "link": link, "image": image, "source": "Otodom",
        }
    except Exception:
        return None


def _fetch_graphql(session, page: int = 1, limit: int = 36) -> list:
    """Call Otodom GraphQL API — same endpoint the browser uses."""
    payload = {
        "operationName": "GetListings",
        "variables": {
            "locale": "pl",
            "page": page,
            "limit": limit,
            "searchingCriteria": {
                "transaction": "RENT",
                "category": "APARTMENT",
                "locations": [{"id": "warszawa", "type": "CITY"}],
                "sortingField": "CREATED_AT",
                "sortingOrder": "DESC",
            },
        },
        "query": _GQL_QUERY,
    }
    try:
        r = session.post(
            GRAPHQL_URL,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": BASE,
                "Origin": "https://www.otodom.pl",
            },
            timeout=20,
        )
        print(f"[Otodom-GQL] page={page} status={r.status_code} size={len(r.text)}")
        if r.status_code != 200:
            return []
        data  = r.json()
        items = (
            data.get("data", {}).get("searchAds", {}).get("items") or []
        )
        results = []
        for item in items:
            apt = _parse_item(item)
            if apt:
                results.append(apt)
        return results
    except Exception as e:
        print(f"[Otodom-GQL] error: {e}")
        return []


def _extract_next_data(html: str) -> list:
    results = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return results
    try:
        data       = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})
        # Primary path: data.searchAds.items
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


def parse_otodom() -> list:
    results = []
    seen    = set()
    session = _session()

    def add(items):
        n = 0
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)
                n += 1
        return n

    # ── Pass 1: today's new listings (__NEXT_DATA__) ─────────
    for page in range(1, 4):
        url = BASE_NEW if page == 1 else f"{BASE_NEW}&page={page}"
        try:
            r   = session.get(url, headers={"Accept": "text/html"}, timeout=25)
            print(f"[Otodom-new] page={page} status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                break
            new = add(_extract_next_data(r.text))
            print(f"[Otodom-new] page={page}: {new} new")
            if new == 0:
                break
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Otodom-new] page={page} error: {e}")
            break

    # ── Pass 2: regular pages ─────────────────────────────────
    for page in range(1, 11):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            r   = session.get(url, headers={"Accept": "text/html"}, timeout=25)
            print(f"[Otodom] page={page} status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                break
            new = add(_extract_next_data(r.text))
            print(f"[Otodom] page={page}: {new} new")
            if new == 0 and page >= 2:
                break
            time.sleep(random.uniform(2.0, 3.0))
        except Exception as e:
            print(f"[Otodom] page={page} error: {e}")
            break

    print(f"[Otodom] Total: {len(results)} listings")
    return results
