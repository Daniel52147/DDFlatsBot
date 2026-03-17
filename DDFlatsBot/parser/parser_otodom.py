import random
import re
import json
import time
import requests
from config import USER_AGENTS

MAX_BYTES = 512 * 1024  # 512KB


def _h(accept="text/html"):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": accept,
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Referer": "https://www.otodom.pl/",
    }


def _price(val) -> int:
    if not val:
        return 0
    digits = "".join(c for c in str(val) if c.isdigit())
    return int(digits) if digits else 0


def _fetch_html(url: str) -> str:
    r = requests.get(url, headers=_h(), timeout=15, stream=True)
    r.raise_for_status()
    content = b""
    for chunk in r.iter_content(65536):
        content += chunk
        if len(content) >= MAX_BYTES:
            break
    r.close()
    return content.decode("utf-8", "ignore")


def _extract_next_data(html: str) -> list:
    """Extract listings from __NEXT_DATA__ JSON embedded in page."""
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
        # Navigate to listings
        props = data.get("props", {}).get("pageProps", {})
        # Try different paths
        items = (
            props.get("data", {}).get("searchAds", {}).get("items") or
            props.get("listings", {}).get("listing", {}).get("items") or
            props.get("data", {}).get("listing", {}).get("items") or
            []
        )
        return items
    except Exception:
        return []


def _parse_items(items: list) -> list:
    results = []
    for item in items:
        try:
            title = item.get("title", "").strip()
            slug = item.get("slug", "")
            apt_id = item.get("id", "")
            if not title:
                continue
            if slug:
                link = f"https://www.otodom.pl/pl/oferta/{slug}"
            elif apt_id:
                link = f"https://www.otodom.pl/pl/oferta/ID{apt_id}"
            else:
                continue

            # Price
            price_obj = (
                item.get("totalPrice") or item.get("rentPrice") or
                item.get("price") or {}
            )
            if isinstance(price_obj, dict):
                price = _price(price_obj.get("value"))
            else:
                price = _price(price_obj)

            # Location
            loc = item.get("location", {})
            if isinstance(loc, dict):
                addr = loc.get("address", {})
                district = (
                    (addr.get("district") or {}).get("name") or
                    (addr.get("city") or {}).get("name") or
                    item.get("locationLabel", {}).get("value") or "Warsaw"
                )
            else:
                district = "Warsaw"

            # Image
            images = item.get("images", [])
            image = ""
            if images and isinstance(images[0], dict):
                image = images[0].get("medium") or images[0].get("small") or ""
            elif images and isinstance(images[0], str):
                image = images[0]

            # Rooms
            rooms = None
            rooms_raw = item.get("roomsNumber") or item.get("rooms")
            if rooms_raw:
                try:
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
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": area,
                "floor": str(item.get("floorNumber", "")) or None,
                "furnished": 0, "link": link, "image": image,
                "source": "Otodom",
            })
        except Exception:
            continue
    return results


def parse_otodom() -> list:
    results = []

    urls = [
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=2",
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa?page=3",
    ]

    for url in urls:
        try:
            html = _fetch_html(url)
            items = _extract_next_data(html)
            if items:
                page_results = _parse_items(items)
                results.extend(page_results)
                print(f"[Otodom] Page got {len(page_results)} listings")
            else:
                # Fallback: regex extraction from HTML
                slugs = re.findall(r'"slug"\s*:\s*"([a-z0-9\-]+-ID\d+[a-z0-9]*)"', html)
                titles = re.findall(r'"title"\s*:\s*"([^"]{10,120})"', html)
                prices = re.findall(r'"value"\s*:\s*(\d{3,6})\s*,\s*"currency"\s*:\s*"PLN"', html)
                seen_slugs = set()
                for i, slug in enumerate(slugs):
                    if slug in seen_slugs:
                        continue
                    seen_slugs.add(slug)
                    title = titles[i] if i < len(titles) else f"Mieszkanie Warszawa #{i+1}"
                    price = int(prices[i]) if i < len(prices) else 0
                    results.append({
                        "title": title, "price": price, "district": "Warsaw",
                        "rooms": None, "area": None, "floor": None, "furnished": 0,
                        "link": f"https://www.otodom.pl/pl/oferta/{slug}",
                        "image": "", "source": "Otodom",
                    })
                if seen_slugs:
                    print(f"[Otodom] Regex fallback got {len(seen_slugs)} listings")
            time.sleep(random.uniform(2, 3))
        except Exception as e:
            print(f"[Otodom] Error on {url}: {e}")

    print(f"[Otodom] Found {len(results)} listings")
    return results
