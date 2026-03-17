import random
import re
import json
import time
import requests
from config import USER_AGENTS

MAX_BYTES = 4 * 1024 * 1024  # 4MB


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    return s


def _fetch(url: str, session) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def _price(val) -> int:
    if not val:
        return 0
    digits = "".join(c for c in str(val) if c.isdigit())
    return int(digits) if digits else 0


def _deep_find_items(obj, depth=0):
    """Recursively search for listing items array in nested JSON."""
    if depth > 8:
        return None
    if isinstance(obj, list) and len(obj) > 3:
        # Check if looks like apartment listings
        if isinstance(obj[0], dict) and any(
            k in obj[0] for k in ("slug", "title", "id", "areaInSquareMeters")
        ):
            return obj
    if isinstance(obj, dict):
        # Priority keys
        for key in ("items", "listings", "offers", "searchAds", "data"):
            val = obj.get(key)
            if val:
                result = _deep_find_items(val, depth + 1)
                if result:
                    return result
        # Search all keys
        for val in obj.values():
            if isinstance(val, (dict, list)):
                result = _deep_find_items(val, depth + 1)
                if result:
                    return result
    return None


def _extract_next_data(html: str) -> list:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        items = _deep_find_items(data)
        return items or []
    except Exception:
        return []


def _parse_items(items: list) -> list:
    results = []
    for item in items:
        try:
            title = item.get("title", "").strip()
            if not title or len(title) < 5:
                continue

            slug = item.get("slug", "")
            apt_id = item.get("id", "")
            if slug:
                link = f"https://www.otodom.pl/pl/oferta/{slug}"
            elif apt_id:
                link = f"https://www.otodom.pl/pl/oferta/ID{apt_id}"
            else:
                continue

            # Price — try multiple fields
            price = 0
            for price_field in ("totalPrice", "rentPrice", "price"):
                pobj = item.get(price_field)
                if pobj:
                    price = _price(pobj.get("value") if isinstance(pobj, dict) else pobj)
                    if price:
                        break

            # District
            loc = item.get("location", {})
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            district = (
                (addr.get("district") or {}).get("name") or
                (addr.get("city") or {}).get("name") or
                item.get("locationLabel", {}).get("value") or
                "Warszawa"
            )
            if isinstance(district, dict):
                district = district.get("name", "Warszawa")

            # Image
            images = item.get("images", [])
            image = ""
            if images:
                img = images[0]
                image = (img.get("medium") or img.get("small") or img.get("large") or "") if isinstance(img, dict) else str(img)

            # Rooms
            rooms = None
            try:
                rooms_raw = item.get("roomsNumber") or item.get("rooms")
                if rooms_raw:
                    rooms = int(str(rooms_raw).replace("+", "").strip())
            except Exception:
                pass

            # Area
            area = None
            try:
                area = float(item.get("areaInSquareMeters") or item.get("area") or 0) or None
            except Exception:
                pass

            results.append({
                "title": title, "price": price, "district": str(district),
                "rooms": rooms, "area": area,
                "floor": str(item.get("floorNumber", "")) or None,
                "furnished": 0, "link": link, "image": image, "source": "Otodom",
            })
        except Exception:
            continue
    return results


def _extract_from_raw_json(html: str) -> list:
    """Extract listing data directly from raw HTML using targeted regex."""
    results = []

    # Find all JSON objects that look like apartment listings
    # Otodom embeds data as: {"id":...,"slug":"...","title":"...","totalPrice":{"value":...}}
    pattern = re.compile(
        r'\{"id"\s*:\s*\d+\s*,.*?"slug"\s*:\s*"([^"]+)".*?"title"\s*:\s*"([^"]+)"',
        re.DOTALL
    )

    # Extract price separately
    price_pattern = re.compile(r'"totalPrice"\s*:\s*\{"value"\s*:\s*(\d+)')
    district_pattern = re.compile(r'"district"\s*:\s*\{"[^"]*"\s*:\s*"[^"]*"\s*,\s*"name"\s*:\s*"([^"]+)"')

    seen = set()
    for m in pattern.finditer(html):
        slug = m.group(1)
        title = m.group(2)
        if slug in seen or len(title) < 5:
            continue
        seen.add(slug)

        # Get surrounding context for price/district
        start = max(0, m.start() - 100)
        end = min(len(html), m.end() + 500)
        ctx = html[start:end]

        price = 0
        pm = price_pattern.search(ctx)
        if pm:
            price = int(pm.group(1))

        district = "Warszawa"
        dm = district_pattern.search(ctx)
        if dm:
            district = dm.group(1)

        results.append({
            "title": title, "price": price, "district": district,
            "rooms": None, "area": None, "floor": None, "furnished": 0,
            "link": f"https://www.otodom.pl/pl/oferta/{slug}",
            "image": "", "source": "Otodom",
        })

    return results


def _fetch_api(page: int, session) -> list:
    """Use Otodom's internal GraphQL/REST API — bypasses bot detection."""
    try:
        url = (
            f"https://www.otodom.pl/api/offers/"
            f"?limit=36&page={page}"
            f"&category=mieszkania&offerType=wynajem"
            f"&locations[0][regionId]=7&locations[0][cityId]=26"  # Warszawa
        )
        r = session.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items") or data.get("data") or []
            if items:
                return _parse_items(items)
    except Exception as e:
        print(f"[Otodom] API error page {page}: {e}")
    return []


def parse_otodom() -> list:
    results = []
    seen_links = set()
    session = _session()
    # Add extra headers to look more like a real browser
    session.headers.update({
        "Referer": "https://www.otodom.pl/",
        "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Upgrade-Insecure-Requests": "1",
    })

    def add(items):
        for apt in items:
            if apt["link"] not in seen_links:
                seen_links.add(apt["link"])
                results.append(apt)

    for page in range(1, 6):
        url = (
            "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa"
            if page == 1 else
            f"https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page={page}"
        )
        try:
            html = _fetch(url, session)
            print(f"[Otodom] Page {page} HTML size: {len(html)}")

            # Method 1: __NEXT_DATA__ deep search
            items = _extract_next_data(html)
            if items:
                page_results = _parse_items(items)
                if page_results:
                    add(page_results)
                    print(f"[Otodom] Page {page} __NEXT_DATA__: {len(page_results)}")
                    time.sleep(random.uniform(2, 3))
                    continue

            # Method 2: Raw JSON extraction
            page_results = _extract_from_raw_json(html)
            if page_results:
                add(page_results)
                print(f"[Otodom] Page {page} Raw JSON: {len(page_results)}")
            else:
                # Log first 500 chars to diagnose blocking
                snippet = html[:500].replace("\n", " ")
                print(f"[Otodom] Page {page}: 0 results. HTML snippet: {snippet[:200]}")

            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"[Otodom] Page {page} error: {e}")

    print(f"[Otodom] Total: {len(results)}")
    return results
