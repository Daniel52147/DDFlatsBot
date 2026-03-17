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


def parse_otodom() -> list:
    results = []
    seen_links = set()
    session = _session()

    def add(items):
        for apt in items:
            if apt["link"] not in seen_links:
                seen_links.add(apt["link"])
                results.append(apt)

    urls = [
        f"https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page={p}"
        if p > 1 else
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa"
        for p in range(1, 11)
    ]

    for url in urls:
        try:
            html = _fetch(url, session)

            # Method 1: __NEXT_DATA__ deep search
            items = _extract_next_data(html)
            if items:
                page_results = _parse_items(items)
                if page_results:
                    add(page_results)
                    print(f"[Otodom] __NEXT_DATA__: {len(page_results)} from {url[-30:]}")
                    time.sleep(random.uniform(1, 2))
                    continue

            # Method 2: Raw JSON extraction
            page_results = _extract_from_raw_json(html)
            if page_results:
                add(page_results)
                print(f"[Otodom] Raw JSON: {len(page_results)} from {url[-30:]}")
            else:
                print(f"[Otodom] 0 from {url[-30:]} — blocked?")

            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Otodom] Error {url[-30:]}: {e}")

    print(f"[Otodom] Total: {len(results)}")
    return results
