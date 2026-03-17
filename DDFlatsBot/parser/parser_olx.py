import random
import re
import json
import time
import requests
from config import USER_AGENTS

API_URL = "https://www.olx.pl/api/v1/offers/"
MAX_BYTES = 1024 * 1024  # 1MB

# Warsaw district IDs in OLX API
WARSAW_DISTRICT_IDS = [
    39611, 39612, 39613, 39614, 39615, 39616, 39617, 39618,
    39619, 39620, 39621, 39622, 39623, 39624, 39625,
]


def _h(json_mode=True):
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/",
        "Accept-Language": "pl-PL,pl;q=0.9",
    }
    if json_mode:
        h["Accept"] = "application/json"
    else:
        h["Accept"] = "text/html,application/xhtml+xml"
    return h


def _price(params: list) -> int:
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


def _fetch_json(url, params=None, headers=None, timeout=15) -> dict:
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


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


def _is_apartment(title: str, category: dict) -> bool:
    title_lower = title.lower()
    for kw in _JUNK_KEYWORDS:
        if kw in title_lower:
            return False
    if category:
        cat_id = category.get("id")
        if cat_id and cat_id not in (15, 1, 3018, 3019, 3020):
            apt_words = ["mieszkanie", "kawalerka", "pokój", "apartament", "wynajem"]
            if not any(w in title_lower for w in apt_words):
                return False
    return True


def _parse_offer(o: dict) -> dict | None:
    try:
        p = o.get("params", [])
        title = o.get("title", "").strip()
        link = o.get("url", "")
        if not title or not link:
            return None

        category = o.get("category", {})
        if not _is_apartment(title, category):
            return None

        price = _price(p)
        loc = o.get("location", {})
        city_name = ((loc.get("city") or {}).get("name") or "").strip()
        district_name = ((loc.get("district") or {}).get("name") or "").strip()

        # Strict Warsaw-only filter
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


def _fetch_api_page(offset: int, extra_params: dict = None) -> list:
    """Fetch one page from OLX API, return parsed offers."""
    params = {
        "offset": offset,
        "limit": 50,
        "category_id": 15,
        "region_id": 7,
        "city_id": 39610,
        "sort_by": "created_at:desc",
        "filter_refiners": "spell_checker",
    }
    if extra_params:
        params.update(extra_params)
    try:
        data = _fetch_json(API_URL, params=params, headers=_h(json_mode=True))
        offers = data.get("data", [])
        results = []
        for o in offers:
            apt = _parse_offer(o)
            if apt:
                results.append(apt)
        return results, len(offers)
    except Exception as e:
        print(f"[OLX] API error offset={offset}: {e}")
        return [], 0


def _parse_html_page(url: str) -> list:
    """Parse OLX HTML listing page."""
    results = []
    try:
        r = requests.get(url, headers=_h(json_mode=False), timeout=20)
        r.raise_for_status()
        text = r.text

        # Try __NEXT_DATA__ first
        m = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*"(.*?)";\s*</script>', text)
        if not m:
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', text, re.DOTALL)
        if m:
            try:
                raw = m.group(1)
                data = json.loads(raw)
                # Try to find offers in the JSON
                offers = (
                    data.get("props", {}).get("pageProps", {}).get("offers", []) or
                    data.get("offers", [])
                )
                for o in offers:
                    apt = _parse_offer(o)
                    if apt:
                        results.append(apt)
                if results:
                    return results
            except Exception:
                pass

        # Regex fallback: extract offer links + titles from HTML
        # OLX listing cards have data-cy="l-card"
        cards = re.findall(
            r'data-cy="l-card"[^>]*>.*?href="(https://www\.olx\.pl/d/oferta/[^"]+)".*?'
            r'(?:data-testid="ad-title"[^>]*>|<h[36][^>]*>)\s*([^<]{5,120})',
            text, re.DOTALL
        )
        seen = set()
        for link, title in cards:
            if link in seen:
                continue
            seen.add(link)
            # Check if Warsaw
            if not _is_apartment(title, {}):
                continue
            results.append({
                "title": title.strip(), "price": 0, "district": "Warszawa",
                "rooms": None, "area": None, "floor": None,
                "furnished": 0, "link": link, "image": "", "source": "OLX",
            })

        # Last resort: extract from embedded JSON blobs
        if not results:
            json_blobs = re.findall(r'\{[^{}]*"url"\s*:\s*"https://www\.olx\.pl/d/oferta/[^"]+?"[^{}]*\}', text)
            seen = set()
            for blob in json_blobs[:100]:
                try:
                    o = json.loads(blob)
                    apt = _parse_offer(o)
                    if apt and apt["link"] not in seen:
                        seen.add(apt["link"])
                        results.append(apt)
                except Exception:
                    pass

    except Exception as e:
        print(f"[OLX] HTML error {url}: {e}")
    return results


def parse_olx() -> list:
    results = []
    seen_links = set()

    def add(items):
        for apt in items:
            if apt["link"] not in seen_links:
                seen_links.add(apt["link"])
                results.append(apt)

    # Primary: OLX API with Warsaw city_id
    print("[OLX] Fetching via API (Warsaw city_id=39610)...")
    empty_pages = 0
    for offset in range(0, 500, 50):
        page_results, total_offers = _fetch_api_page(offset)
        if total_offers == 0:
            empty_pages += 1
            if empty_pages >= 2:
                break
        else:
            empty_pages = 0
        add(page_results)
        print(f"[OLX] API offset={offset}: {total_offers} raw → {len(page_results)} Warsaw")
        time.sleep(random.uniform(0.8, 1.5))

    # Fallback: HTML pages if API gave too few results
    if len(results) < 30:
        print("[OLX] API gave few results, trying HTML pages...")
        for page in range(1, 6):
            url = (
                "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/"
                if page == 1
                else f"https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/?page={page}"
            )
            page_results = _parse_html_page(url)
            add(page_results)
            print(f"[OLX] HTML page {page}: {len(page_results)}")
            time.sleep(random.uniform(1, 2))

    print(f"[OLX] Total Warsaw listings: {len(results)}")
    return results
