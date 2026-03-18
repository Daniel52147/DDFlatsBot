"""
OLX parser — uses OLX mobile/partner API v2 with proper headers.
OLX switched to client-side rendering so HTML scraping returns empty shell.
The v1 API requires auth token on datacenter IPs.
We use the partner API endpoint which is more permissive.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

# OLX API endpoints to try
API_V1 = "https://www.olx.pl/api/v1/offers/"
API_V2 = "https://www.olx.pl/api/v2/offers/"

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


def _is_apartment(title: str, cat_id=None) -> bool:
    t = title.lower()
    for kw in _JUNK_KEYWORDS:
        if kw in t:
            return False
    if cat_id and cat_id not in (15, 16, 1, 3018, 3019, 3020):
        apt_words = ["mieszkanie", "kawalerka", "pokój", "pokoje", "apartament", "wynajem"]
        if not any(w in t for w in apt_words):
            return False
    return True


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


def _parse_offer(o: dict) -> dict | None:
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


def _api_headers(mobile: bool = False) -> dict:
    if mobile:
        return {
            "User-Agent": "OLX/5.153.7 (Android 12; Mobile)",
            "Accept": "application/json",
            "Accept-Language": "pl-PL",
            "x-platform": "android",
        }
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Referer": "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/",
        "Origin": "https://www.olx.pl",
    }


def _fetch_api(url: str, params: dict, mobile: bool = False) -> tuple[list, int, int]:
    """Returns (results, raw_count, status_code)."""
    try:
        r = requests.get(url, params=params, headers=_api_headers(mobile), timeout=20)
        if r.status_code != 200:
            return [], 0, r.status_code
        data = r.json()
        offers = data.get("data", [])
        results = [apt for o in offers if (apt := _parse_offer(o))]
        return results, len(offers), 200
    except Exception as e:
        print(f"[OLX] API error: {e}")
        return [], 0, 0


def _try_api(cat_id: int, cat_name: str) -> tuple[list, bool]:
    """Try fetching category via API. Returns (results, success)."""
    results = []
    seen = set()

    base_params = {
        "limit": 50,
        "category_id": cat_id,
        "region_id": 7,
        "city_id": 39610,
        "sort_by": "created_at:desc",
        "filter_refiners": "spell_checker",
    }

    # Try v1 with normal headers first
    for api_url, mobile in [(API_V1, False), (API_V1, True), (API_V2, False)]:
        params = {**base_params, "offset": 0}
        page_results, raw_count, status = _fetch_api(api_url, params, mobile)
        label = f"{'mobile' if mobile else 'desktop'} {api_url.split('/')[-2]}"
        print(f"[OLX] API {cat_name} {label}: status={status} raw={raw_count}")

        if status == 200 and raw_count > 0:
            # This endpoint works — fetch all pages
            for apt in page_results:
                if apt["link"] not in seen:
                    seen.add(apt["link"])
                    results.append(apt)

            empty = 0
            for offset in range(50, 500, 50):
                params = {**base_params, "offset": offset}
                pr, rc, _ = _fetch_api(api_url, params, mobile)
                if rc == 0:
                    empty += 1
                    if empty >= 2:
                        break
                else:
                    empty = 0
                for apt in pr:
                    if apt["link"] not in seen:
                        seen.add(apt["link"])
                        results.append(apt)
                print(f"[OLX] API {cat_name} offset={offset}: {rc} raw → {len(pr)} Warsaw")
                time.sleep(random.uniform(0.5, 1.0))
            return results, True

        if status in (401, 403):
            print(f"[OLX] API auth blocked ({status}) — trying next")
            continue

        time.sleep(0.5)

    return [], False


def _fetch_olx_json_endpoint(cat_id: int) -> list:
    """
    Try OLX's internal JSON search endpoint used by their SPA.
    This is the XHR call the browser makes after page load.
    """
    results = []
    seen = set()

    # OLX SPA fetches data from this endpoint
    url = "https://www.olx.pl/api/v1/offers/"
    session = requests.Session()
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Referer": "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/",
        "Origin": "https://www.olx.pl",
        "x-requested-with": "XMLHttpRequest",
    })

    # First visit homepage to get cookies
    try:
        session.get("https://www.olx.pl/", timeout=10,
                    headers={"Accept": "text/html", "User-Agent": random.choice(USER_AGENTS)})
        time.sleep(random.uniform(1, 2))
    except Exception:
        pass

    for offset in range(0, 200, 50):
        params = {
            "offset": offset, "limit": 50,
            "category_id": cat_id,
            "region_id": 7, "city_id": 39610,
            "sort_by": "created_at:desc",
        }
        try:
            r = session.get(url, params=params, timeout=20)
            print(f"[OLX] XHR cat={cat_id} offset={offset}: status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                break
            data = r.json()
            offers = data.get("data", [])
            if not offers:
                break
            for o in offers:
                apt = _parse_offer(o)
                if apt and apt["link"] not in seen:
                    seen.add(apt["link"])
                    results.append(apt)
            print(f"[OLX] XHR cat={cat_id} offset={offset}: {len(offers)} raw → {len(results)} total")
            time.sleep(random.uniform(1, 1.5))
        except Exception as e:
            print(f"[OLX] XHR error: {e}")
            break

    return results


def parse_olx() -> list:
    results = []
    seen_links = set()

    def add(items):
        for apt in items:
            if apt["link"] not in seen_links:
                seen_links.add(apt["link"])
                results.append(apt)

    # Try API for mieszkania + pokoje
    for cat_id, cat_name in [(15, "mieszkania"), (16, "pokoje")]:
        api_results, ok = _try_api(cat_id, cat_name)
        if ok:
            add(api_results)
            print(f"[OLX] API {cat_name}: {len(api_results)} listings")
        else:
            print(f"[OLX] API {cat_name} failed — trying XHR session")
            xhr_results = _fetch_olx_json_endpoint(cat_id)
            add(xhr_results)

    print(f"[OLX] Total Warsaw listings: {len(results)}")
    return results
