"""
Otodom parser — extracts listings from __NEXT_DATA__ embedded JSON.
No external API needed, works without Cloudflare bypass.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE = "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
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

        slug = item.get("slug") or ""
        apt_id = item.get("id") or ""
        if slug:
            link = f"https://www.otodom.pl/pl/oferta/{slug}"
        elif apt_id:
            link = f"https://www.otodom.pl/pl/oferta/{apt_id}"
        else:
            return None

        # Price extraction
        price = 0
        for pf in ("totalPrice", "rentPrice", "price"):
            pobj = item.get(pf)
            if pobj:
                price = _price(pobj.get("value") if isinstance(pobj, dict) else pobj)
                if price:
                    break

        # Location
        loc = item.get("location") or {}
        addr = loc.get("address") or {} if isinstance(loc, dict) else {}
        district = "Warszawa"
        if isinstance(addr, dict):
            d = addr.get("district") or {}
            c = addr.get("city") or {}
            district = (
                (d.get("name") if isinstance(d, dict) else d) or
                (c.get("name") if isinstance(c, dict) else c) or
                "Warszawa"
            )

        # Image
        images = item.get("images") or []
        image = ""
        if images and isinstance(images[0], dict):
            image = (images[0].get("medium") or images[0].get("small") or
                     images[0].get("large") or "")

        # Rooms
        rooms = None
        try:
            r = item.get("roomsNumber") or item.get("rooms")
            if r:
                rooms = int(str(r).replace("+", ""))
        except Exception:
            pass

        # Area
        area = None
        try:
            a = item.get("areaInSquareMeters") or item.get("area")
            if a:
                area = float(a)
        except Exception:
            pass

        return {
            "title": title, "price": price, "district": str(district),
            "rooms": rooms, "area": area, "floor": None, "furnished": 0,
            "link": link, "image": image, "source": "Otodom",
        }
    except Exception:
        return None


def _extract_from_next_data(html: str) -> list:
    """Extract listings from __NEXT_DATA__ JSON embedded in HTML."""
    results = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return results
    try:
        data = json.loads(m.group(1))
        # Navigate the nested structure
        page_props = data.get("props", {}).get("pageProps", {})

        # Try multiple known paths
        items = (
            page_props.get("data", {}).get("searchAds", {}).get("items") or
            page_props.get("listings", {}).get("listing", {}).get("items") or
            page_props.get("data", {}).get("listing", {}).get("items") or
            page_props.get("searchAds", {}).get("items") or
            []
        )

        if not items:
            # Try to find any list of items with "slug" or "title" keys
            def find_items(obj, depth=0):
                if depth > 6:
                    return []
                if isinstance(obj, list) and len(obj) > 0:
                    if isinstance(obj[0], dict) and ("slug" in obj[0] or "title" in obj[0]):
                        return obj
                if isinstance(obj, dict):
                    for v in obj.values():
                        found = find_items(v, depth + 1)
                        if found:
                            return found
                return []
            items = find_items(page_props)

        for item in items:
            apt = _parse_item(item)
            if apt:
                results.append(apt)
    except Exception as e:
        print(f"[Otodom] __NEXT_DATA__ parse error: {e}")
    return results


def parse_otodom() -> list:
    results = []
    seen = set()
    session = _session()

    for page in range(1, 6):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            r = session.get(url, timeout=25)
            print(f"[Otodom] Page {page} status={r.status_code} size={len(r.text)}")

            if r.status_code != 200:
                print(f"[Otodom] Blocked on page {page}, stopping")
                break

            page_results = _extract_from_next_data(r.text)
            new = 0
            for apt in page_results:
                if apt["link"] not in seen:
                    seen.add(apt["link"])
                    results.append(apt)
                    new += 1

            print(f"[Otodom] Page {page}: {new} listings")
            if new == 0:
                # Log snippet to diagnose
                snippet = r.text[:300].replace("\n", " ")
                print(f"[Otodom] Page {page} snippet: {snippet}")
                if page >= 2:
                    break  # Only stop after 2 consecutive empty pages

            time.sleep(random.uniform(2, 3))
        except Exception as e:
            print(f"[Otodom] Page {page} error: {e}")
            break

    print(f"[Otodom] Found {len(results)} listings")
    return results
