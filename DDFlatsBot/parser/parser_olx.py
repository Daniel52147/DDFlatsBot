"""
OLX parser — primary HTML via __NEXT_DATA__, fallback to API.
OLX API now requires auth token on some Render IPs, so HTML is primary.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

API_URL = "https://www.olx.pl/api/v1/offers/"

_JUNK_KEYWORDS = [
    "osuszacz", "klimatyzator", "agregat", "laweta", "przyczepa",
    "rower", "samochód", "auto ", "skuter", "motor", "kamera",
    "telewizor", "lodówka", "pralka", "zmywarka", "meble",
    "garaż", "parking", "miejsce postojowe", "komórka lokatorska",
    "działka", "dom na sprzedaż", "lokal użytkowy", "biuro",
    "magazyn", "hala", "grunt", "sprzedam", "na sprzedaż",
    "na doby", "na godziny", "noclegi", "na tydzień",
    "krótkoterminow", "dobowy", "/doby", "godz/", "osuszanie",
]

_WARSAW_CITIES = {"warszawa", "warsaw"}


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.olx.pl/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
    })
    return s


def _price_from_params(params: list) -> int:
    for p in params:
        if p.get("key") == "price":
            try:
                return int(str(p["value"]["value"]).replace(" ", "").replace("\xa0", ""))
            except Exception:
                pass
    return 0


def _param(params: list, key: str):
    for p in params:
        if p.get("key") == key:
            v = p.get("value", {})
            return (v.get("label") or v.get("key")) if isinstance(v, dict) else v
    return None


def _price_from_str(val) -> int:
    if not val:
        return 0
    try:
        return int(float(str(val).replace(" ", "").replace("\xa0", "").replace(",", ".")))
    except Exception:
        digits = "".join(c for c in str(val) if c.isdigit())
        return int(digits) if digits else 0


def _is_apartment(title: str, category_id=None) -> bool:
    title_lower = title.lower()
    for kw in _JUNK_KEYWORDS:
        if kw in title_lower:
            return False
    if category_id and category_id not in (15, 16, 1, 3018, 3019, 3020):
        apt_words = ["mieszkanie", "kawalerka", "pokój", "pokoje", "apartament", "wynajem"]
        if not any(w in title_lower for w in apt_words):
            return False
    return True


def _parse_offer_api(o: dict) -> dict | None:
    """Parse one offer from OLX API response."""
    try:
        p = o.get("params", [])
        title = o.get("title", "").strip()
        link = o.get("url", "")
        if not title or not link:
            return None
        cat_id = (o.get("category") or {}).get("id")
        if not _is_apartment(title, cat_id):
            return None
        price = _price_from_params(p)
        loc = o.get("location", {})
        city_name = ((loc.get("city") or {}).get("name") or "").strip()
        district_name = ((loc.get("district") or {}).get("name") or "").strip()
        if city_name and city_name.lower() not in _WARSAW_CITIES:
            return None
        district = district_name or city_name or "Warszawa"
        photos = o.get("photos", [])
        image = ""
        if photos:
            image = photos[0].get("link", "").replace("{width}", "400").replace("{height}", "300")
        rooms = None
        area = None
        rooms_raw = _param(p, "rooms")
        area_raw = _param(p, "m")
        if rooms_raw:
            try:
                rooms = int(str(rooms_raw).replace("+", "").strip())
            except Exception:
                pass
        if area_raw:
            try:
                area = float(str(area_raw).replace(",", ".").strip())
            except Exception:
                pass
        return {
            "title": title, "price": price, "district": district,
            "rooms": rooms, "area": area, "floor": None,
            "furnished": 0, "link": link, "image": image, "source": "OLX",
        }
    except Exception:
        return None


def _parse_offer_next(item: dict) -> dict | None:
    """Parse one offer from __NEXT_DATA__ JSON structure."""
    try:
        title = (item.get("title") or "").strip()
        link = item.get("url") or item.get("href") or ""
        if not title or not link:
            return None
        if not link.startswith("http"):
            link = "https://www.olx.pl" + link
        # Only OLX links
        if "olx.pl" not in link:
            return None
        cat_id = None
        cat = item.get("category") or {}
        if isinstance(cat, dict):
            cat_id = cat.get("id")
        if not _is_apartment(title, cat_id):
            return None

        # Price — multiple possible locations
        price = 0
        price_obj = item.get("price") or {}
        if isinstance(price_obj, dict):
            price = _price_from_str(
                price_obj.get("regularPrice", {}).get("value") or
                price_obj.get("value") or
                price_obj.get("amount") or 0
            )
        elif price_obj:
            price = _price_from_str(price_obj)

        # Location
        loc = item.get("location") or {}
        city_name = ""
        district_name = ""
        if isinstance(loc, dict):
            city_obj = loc.get("cityName") or loc.get("city") or {}
            city_name = (city_obj if isinstance(city_obj, str) else city_obj.get("name", "")).strip()
            dist_obj = loc.get("districtName") or loc.get("district") or {}
            district_name = (dist_obj if isinstance(dist_obj, str) else dist_obj.get("name", "")).strip()

        if city_name and city_name.lower() not in _WARSAW_CITIES:
            return None

        district = district_name or city_name or "Warszawa"

        # Image
        photos = item.get("photos") or item.get("images") or []
        image = ""
        if photos and isinstance(photos[0], dict):
            image = (photos[0].get("link") or photos[0].get("url") or
                     photos[0].get("medium") or "")
            if image and "{width}" in image:
                image = image.replace("{width}", "400").replace("{height}", "300")
        elif photos and isinstance(photos[0], str):
            image = photos[0]

        # Rooms / area from params list
        rooms = None
        area = None
        params_list = item.get("params") or []
        if params_list:
            rooms_raw = _param(params_list, "rooms")
            area_raw = _param(params_list, "m")
            if rooms_raw:
                try:
                    rooms = int(str(rooms_raw).replace("+", "").strip())
                except Exception:
                    pass
            if area_raw:
                try:
                    area = float(str(area_raw).replace(",", ".").strip())
                except Exception:
                    pass

        return {
            "title": title, "price": price, "district": district,
            "rooms": rooms, "area": area, "floor": None,
            "furnished": 0, "link": link, "image": image, "source": "OLX",
        }
    except Exception:
        return None


def _extract_next_data(html: str) -> list:
    """Extract listings from __NEXT_DATA__ JSON embedded in OLX HTML."""
    results = []

    # Try __NEXT_DATA__ script tag
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return results

    try:
        data = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})

        # OLX stores listings in multiple possible paths
        listings = (
            page_props.get("ads", {}).get("ads") or
            page_props.get("listing", {}).get("listing", {}).get("ads") or
            page_props.get("data", {}).get("ads") or
            page_props.get("offers") or
            []
        )

        if not listings:
            # Deep search for any list with "url" and "title" keys
            def find_ads(obj, depth=0):
                if depth > 7:
                    return []
                if isinstance(obj, list) and len(obj) >= 3:
                    if isinstance(obj[0], dict) and (
                        "url" in obj[0] or "title" in obj[0] or "href" in obj[0]
                    ):
                        return obj
                if isinstance(obj, dict):
                    for v in obj.values():
                        found = find_ads(v, depth + 1)
                        if found:
                            return found
                return []
            listings = find_ads(page_props)

        for item in listings:
            if not isinstance(item, dict):
                continue
            apt = _parse_offer_next(item)
            if apt:
                results.append(apt)

    except Exception as e:
        print(f"[OLX] __NEXT_DATA__ parse error: {e}")

    return results


def _fetch_html_page(session, url: str, page_num: int) -> list:
    """Fetch one OLX HTML page and extract listings."""
    try:
        r = session.get(url, timeout=25)
        size = len(r.text)
        print(f"[OLX] HTML page {page_num} status={r.status_code} size={size}")
        if r.status_code != 200:
            print(f"[OLX] HTML page {page_num} blocked")
            return []
        results = _extract_next_data(r.text)
        if not results:
            # Regex fallback: grab offer links from HTML
            links = re.findall(
                r'href="(https://www\.olx\.pl/d/oferta/[^"?#]+)"',
                r.text
            )
            seen = set()
            for link in links:
                if link in seen:
                    continue
                seen.add(link)
                # Try to get title from nearby HTML
                results.append({
                    "title": "Mieszkanie Warszawa",
                    "price": 0, "district": "Warszawa",
                    "rooms": None, "area": None, "floor": None,
                    "furnished": 0, "link": link, "image": "", "source": "OLX",
                })
        print(f"[OLX] HTML page {page_num}: {len(results)} listings")
        return results
    except Exception as e:
        print(f"[OLX] HTML page {page_num} error: {e}")
        return []


def _fetch_api_page(offset: int, cat_id: int = 15) -> tuple:
    """Fetch one page from OLX API. Returns (results, raw_count)."""
    params = {
        "offset": offset,
        "limit": 50,
        "category_id": cat_id,
        "region_id": 7,
        "city_id": 39610,
        "sort_by": "created_at:desc",
        "filter_refiners": "spell_checker",
    }
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Referer": "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/",
        "Accept-Language": "pl-PL,pl;q=0.9",
    }
    try:
        r = requests.get(API_URL, params=params, headers=headers, timeout=15)
        if r.status_code == 401 or r.status_code == 403:
            print(f"[OLX] API auth required (status {r.status_code}) — skipping API")
            return [], -1  # -1 = auth error, stop trying
        r.raise_for_status()
        data = r.json()
        offers = data.get("data", [])
        results = [apt for o in offers if (apt := _parse_offer_api(o))]
        return results, len(offers)
    except Exception as e:
        print(f"[OLX] API error offset={offset}: {e}")
        return [], 0


def parse_olx() -> list:
    results = []
    seen_links = set()

    def add(items):
        for apt in items:
            if apt["link"] not in seen_links:
                seen_links.add(apt["link"])
                results.append(apt)

    # 1. Try API first (fast, structured data)
    api_works = True
    for cat_id, cat_name in [(15, "mieszkania"), (16, "pokoje")]:
        if not api_works:
            break
        print(f"[OLX] API: {cat_name} (cat={cat_id})...")
        empty_pages = 0
        for offset in range(0, 500, 50):
            page_results, raw_count = _fetch_api_page(offset, cat_id)
            if raw_count == -1:
                api_works = False
                print("[OLX] API blocked — switching to HTML")
                break
            if raw_count == 0:
                empty_pages += 1
                if empty_pages >= 2:
                    break
            else:
                empty_pages = 0
            add(page_results)
            print(f"[OLX] API {cat_name} offset={offset}: {raw_count} raw → {len(page_results)} Warsaw")
            time.sleep(random.uniform(0.5, 1.0))

    # 2. HTML fallback — always run if API gave < 30 results
    if len(results) < 30:
        print("[OLX] Fetching via HTML pages...")
        session = _session()

        # Warm up with homepage first (sets cookies)
        try:
            session.get("https://www.olx.pl/", timeout=10)
            time.sleep(random.uniform(1, 2))
        except Exception:
            pass

        urls = [
            "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/",
            "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?page=2",
            "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?page=3",
            "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?page=4",
            "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?page=5",
            # Also fetch pokoje (rooms)
            "https://www.olx.pl/nieruchomosci/pokoje/wynajem/warszawa/",
            "https://www.olx.pl/nieruchomosci/pokoje/wynajem/warszawa/?page=2",
        ]
        for i, url in enumerate(urls, 1):
            page_results = _fetch_html_page(session, url, i)
            add(page_results)
            time.sleep(random.uniform(1.5, 2.5))

    print(f"[OLX] Total Warsaw listings: {len(results)}")
    return results
