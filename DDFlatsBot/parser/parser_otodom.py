import random
import re
import json
import time
import requests

from config import USER_AGENTS

MAX_BYTES = 3 * 1024 * 1024  # 3MB


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _fetch(url: str, session) -> str:
    # Don't use stream=True — prevents automatic Brotli/gzip decompression
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r.text


def _price(val) -> int:
    if not val:
        return 0
    digits = "".join(c for c in str(val) if c.isdigit())
    return int(digits) if digits else 0


def _extract_next_data(html: str) -> list:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL
    )
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        props = data.get("props", {}).get("pageProps", {})
        # Try multiple known paths
        candidates = [
            props.get("data", {}).get("searchAds", {}).get("items"),
            props.get("listings", {}).get("listing", {}).get("items"),
            props.get("data", {}).get("listing", {}).get("items"),
            props.get("searchAds", {}).get("items"),
            props.get("data", {}).get("searchAds", {}).get("items"),
        ]
        for c in candidates:
            if c:
                return c
        # Deep search for any "items" array with apartment-like objects
        raw = m.group(1)
        items_match = re.search(r'"items":\s*(\[.*?"slug".*?\])', raw, re.DOTALL)
        if items_match:
            try:
                return json.loads(items_match.group(1))
            except Exception:
                pass
        return []
    except Exception:
        return []


def _parse_items(items: list) -> list:
    results = []
    for item in items:
        try:
            title = item.get("title", "").strip()
            if not title:
                continue

            slug = item.get("slug", "")
            apt_id = item.get("id", "")
            if slug:
                link = f"https://www.otodom.pl/pl/oferta/{slug}"
            elif apt_id:
                link = f"https://www.otodom.pl/pl/oferta/ID{apt_id}"
            else:
                continue

            price_obj = (
                item.get("totalPrice") or item.get("rentPrice") or
                item.get("price") or {}
            )
            price = _price(price_obj.get("value") if isinstance(price_obj, dict) else price_obj)

            loc = item.get("location", {})
            addr = loc.get("address", {}) if isinstance(loc, dict) else {}
            district = (
                (addr.get("district") or {}).get("name") or
                (addr.get("city") or {}).get("name") or
                item.get("locationLabel", {}).get("value") or "Warsaw"
            )

            images = item.get("images", [])
            image = ""
            if images:
                img = images[0]
                image = (img.get("medium") or img.get("small") or "") if isinstance(img, dict) else str(img)

            rooms = None
            try:
                rooms_raw = item.get("roomsNumber") or item.get("rooms")
                if rooms_raw:
                    rooms = int(str(rooms_raw).replace("+", "").strip())
            except Exception:
                pass

            area = None
            try:
                area = float(item.get("areaInSquareMeters") or item.get("area") or 0) or None
            except Exception:
                pass

            results.append({
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": area,
                "floor": str(item.get("floorNumber", "")) or None,
                "furnished": 0, "link": link, "image": image, "source": "Otodom",
            })
        except Exception:
            continue
    return results


def _json_ld_fallback(html: str) -> list:
    """Extract listings from JSON-LD structured data."""
    results = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
            if not isinstance(data, dict):
                continue
            items = data.get("itemListElement", [])
            for item in items:
                try:
                    thing = item.get("item", item)
                    name = thing.get("name", "").strip()
                    url = thing.get("url", "")
                    if not name or not url or "otodom.pl" not in url:
                        continue
                    price_spec = thing.get("offers", {})
                    price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                    results.append({
                        "title": name, "price": price, "district": "Warsaw",
                        "rooms": None, "area": None, "floor": None, "furnished": 0,
                        "link": url, "image": "", "source": "Otodom",
                    })
                except Exception:
                    continue
        except Exception:
            continue
    return results


def _slug_fallback(html: str) -> list:
    """Extract slugs + titles + prices directly from raw HTML via regex."""
    results = []
    # Match slugs that look like apartment listings (contain ID)
    slugs = re.findall(r'"slug"\s*:\s*"([^"]+ID\d+[^"]*)"', html)
    if not slugs:
        # Try without ID requirement
        slugs = re.findall(r'"slug"\s*:\s*"(mieszkanie-[^"]{10,80})"', html)

    titles = re.findall(r'"title"\s*:\s*"([^"]{10,120})"', html)
    prices = re.findall(r'"value"\s*:\s*(\d{3,6})\s*,\s*"currency"\s*:\s*"PLN"', html)
    districts = re.findall(r'"district"\s*:\s*\{\s*"name"\s*:\s*"([^"]+)"', html)

    seen = set()
    for i, slug in enumerate(slugs):
        if slug in seen:
            continue
        seen.add(slug)
        title = titles[i] if i < len(titles) else f"Mieszkanie Warszawa #{i+1}"
        price = int(prices[i]) if i < len(prices) else 0
        district = districts[i] if i < len(districts) else "Warsaw"
        results.append({
            "title": title, "price": price, "district": district,
            "rooms": None, "area": None, "floor": None, "furnished": 0,
            "link": f"https://www.otodom.pl/pl/oferta/{slug}",
            "image": "", "source": "Otodom",
        })
    return results


def parse_otodom() -> list:
    results = []
    session = _session()

    urls = [
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=2",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=3",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=4",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=5",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=6",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=7",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=8",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=9",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=10",
    ]

    for url in urls:
        try:
            html = _fetch(url, session)

            # Method 1: __NEXT_DATA__ JSON (structured, best)
            items = _extract_next_data(html)
            if items:
                page_results = _parse_items(items)
                if page_results:
                    results.extend(page_results)
                    print(f"[Otodom] __NEXT_DATA__: {len(page_results)} from {url[-40:]}")
                    time.sleep(random.uniform(1.5, 3))
                    continue

            # Method 2: JSON-LD structured data
            page_results = _json_ld_fallback(html)
            if page_results:
                results.extend(page_results)
                print(f"[Otodom] JSON-LD: {len(page_results)} from {url[-40:]}")
                time.sleep(random.uniform(1.5, 3))
                continue

            # Method 3: slug regex fallback
            page_results = _slug_fallback(html)
            if page_results:
                results.extend(page_results)
                print(f"[Otodom] Slug fallback: {len(page_results)} from {url[-40:]}")
            else:
                print(f"[Otodom] 0 listings on {url} — site may be blocking")

            time.sleep(random.uniform(1.5, 3))
        except Exception as e:
            print(f"[Otodom] Error on {url}: {e}")

    print(f"[Otodom] Total: {len(results)}")
    return results
