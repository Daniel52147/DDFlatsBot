"""
OLX parser — uses OLX public JSON API v1 as primary source.
API endpoint: https://www.olx.pl/api/v1/offers/
Falls back to HTML parsing if API fails.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE_URL   = "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/"
SORT_NEW   = f"{BASE_URL}?search%5Border%5D=created_at%3Adesc"
SORT_PRICE = f"{BASE_URL}?search%5Border%5D=filter_float_price%3Aasc"

# OLX JSON API
OLX_API = "https://www.olx.pl/api/v1/offers/"
OLX_API_PARAMS = {
    "offset": 0,
    "limit": 50,
    "category_id": 15,          # mieszkania
    "region_id": 7,             # mazowieckie
    "city_id": 39610,           # Warszawa
    "filter_refiners": "spell_checker",
    "sl": "18b6e5e5e4ax1b2c3d4e",
    "sort_by": "created_at:desc",
}


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": "https://www.olx.pl/",
        "Connection": "close",
    })
    return s


def _html_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": "https://www.olx.pl/",
        "Connection": "close",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _price(val) -> int:
    if not val:
        return 0
    cleaned = re.sub(r'[^\d.,]', '', str(val).replace('\xa0', '').replace(' ', ''))
    try:
        return int(float(cleaned.replace(',', '.')))
    except Exception:
        digits = re.sub(r'\D', '', str(val))
        return int(digits) if digits else 0


def _rooms_from_title(title: str):
    rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
    return int(rm.group(1)) if rm else None


def _area_from_title(title: str):
    am = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', title, re.I)
    if am:
        try:
            return float(am.group(1).replace(',', '.'))
        except Exception:
            pass
    return None


# ── OLX JSON API ──────────────────────────────────────────────

def _parse_api_offer(offer: dict) -> dict | None:
    """Parse a single offer from OLX API response."""
    try:
        title = (offer.get("title") or "").strip()
        if not title or len(title) < 5:
            return None

        url = offer.get("url") or ""
        if not url:
            return None

        # Price
        price = 0
        price_obj = offer.get("price") or {}
        if isinstance(price_obj, dict):
            price = _price(price_obj.get("value", 0))

        # District from location
        district = "Warszawa"
        loc = offer.get("location") or {}
        if isinstance(loc, dict):
            city_name = loc.get("city", {}).get("name", "") if isinstance(loc.get("city"), dict) else ""
            district_name = loc.get("district", {}).get("name", "") if isinstance(loc.get("district"), dict) else ""
            district = district_name or city_name or "Warszawa"

        # Image — first photo
        photos = offer.get("photos") or []
        image = ""
        if photos and isinstance(photos[0], dict):
            image = photos[0].get("link", "").replace("{width}", "400").replace("{height}", "300")

        # Params — rooms, area, floor
        rooms = None
        area = None
        floor = None
        for param in (offer.get("params") or []):
            key = param.get("key", "")
            val = param.get("value", {})
            label = val.get("label", "") if isinstance(val, dict) else str(val)
            if key == "rooms":
                try:
                    rooms = int(re.search(r'\d+', label).group())
                except Exception:
                    pass
            elif key == "m":
                try:
                    area = float(re.sub(r'[^\d.,]', '', label).replace(',', '.'))
                except Exception:
                    pass
            elif key == "floor_select":
                floor = label

        # Fallback rooms/area from title
        if not rooms:
            rooms = _rooms_from_title(title)
        if not area:
            area = _area_from_title(title)

        return {
            "title": title,
            "price": price,
            "district": district,
            "rooms": rooms,
            "area": area,
            "floor": floor,
            "furnished": 0,
            "link": url,
            "image": image,
            "source": "OLX",
        }
    except Exception:
        return None


def _fetch_api(session, offset: int = 0, sort: str = "created_at:desc") -> list:
    """Fetch offers from OLX JSON API."""
    params = {**OLX_API_PARAMS, "offset": offset, "sort_by": sort}
    try:
        r = session.get(OLX_API, params=params, timeout=15)
        if r.status_code != 200:
            print(f"[OLX-API] status={r.status_code}")
            return []
        data = r.json()
        offers = data.get("data") or []
        results = []
        for offer in offers:
            apt = _parse_api_offer(offer)
            if apt:
                results.append(apt)
        return results
    except Exception as e:
        print(f"[OLX-API] error: {e}")
        return []


# ── HTML fallback ─────────────────────────────────────────────

def _parse_json_ld(html: str) -> list:
    results = []
    for script in re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        if '"offers"' not in script or len(script) < 500:
            continue
        try:
            json_start = script.find('{')
            if json_start < 0:
                continue
            d = json.loads(script[json_start:])
            if d.get('@type') != 'Product':
                continue
            outer = d.get('offers', {})
            inner = outer.get('offers', []) if isinstance(outer, dict) else (outer if isinstance(outer, list) else [])
            for item in inner:
                try:
                    name = (item.get('name') or '').strip()
                    url = item.get('url') or ''
                    if not name or len(name) < 5 or not url or 'olx.pl' not in url:
                        continue
                    url = url.split('?')[0]
                    price = _price(item.get('price', 0))
                    area_obj = item.get('areaServed') or {}
                    district = (area_obj.get('name') if isinstance(area_obj, dict) else str(area_obj)) or 'Warszawa'
                    imgs = item.get('image') or []
                    image = imgs[0] if imgs else ''
                    results.append({
                        'title': name, 'price': price, 'district': district,
                        'rooms': _rooms_from_title(name), 'area': _area_from_title(name),
                        'floor': None, 'furnished': 0,
                        'link': url, 'image': image, 'source': 'OLX',
                    })
                except Exception:
                    continue
            break
        except Exception:
            continue
    return results


def _parse_html_cards(html: str) -> list:
    results = []
    raw_links = re.findall(r'href="(/d/oferta/[^"?]+)', html)
    seen_links = []
    seen_set = set()
    for l in raw_links:
        if l not in seen_set:
            seen_set.add(l)
            seen_links.append(l)
    raw_prices = re.findall(r'data-testid="ad-price"[^>]*>([\d\s\xa0]+)\s*zł', html, re.I)
    raw_locs = re.findall(r'data-testid="location-date"[^>]*>(.*?)</p>', html, re.DOTALL)
    card_sections = re.split(r'data-cy="l-card"', html)
    n = min(len(seen_links), len(raw_prices), len(raw_locs))
    for i in range(n):
        try:
            url = f"https://www.olx.pl{seen_links[i]}"
            price = _price(raw_prices[i])
            loc_raw = re.sub(r'<[^>]+>', '', raw_locs[i]).strip()
            district = 'Warszawa'
            loc_m = re.match(r'Warszawa,?\s*([^-–\d]+)', loc_raw)
            if loc_m:
                district = loc_m.group(1).strip().rstrip(',').strip()
            slug = seen_links[i].split('/')[-1]
            slug = re.sub(r'-CID\d+-ID\w+\.html$', '', slug)
            slug = re.sub(r'\.html$', '', slug)
            title = slug.replace('-', ' ').title()
            image = ''
            if i + 1 < len(card_sections):
                img_m = re.search(r'src="(https://ireland\.apollo\.olxcdn\.com[^"]+)"', card_sections[i + 1][:1000])
                if img_m:
                    image = img_m.group(1)
            results.append({
                'title': title, 'price': price, 'district': district,
                'rooms': _rooms_from_title(title), 'area': _area_from_title(title),
                'floor': None, 'furnished': 0,
                'link': url, 'image': image, 'source': 'OLX',
            })
        except Exception:
            continue
    return results


def _parse_page(html: str) -> list:
    results = _parse_json_ld(html)
    if not results:
        results = _parse_html_cards(html)
    return results


# ── Main parse function ───────────────────────────────────────

def parse_olx() -> list:
    results = []
    seen = set()
    session = _session()

    def add(items):
        n = 0
        for apt in items:
            if apt['link'] not in seen:
                seen.add(apt['link'])
                results.append(apt)
                n += 1
        return n

    # ── Pass 1: JSON API (newest) ─────────────────────────────
    api_ok = False
    for offset in range(0, 200, 50):
        items = _fetch_api(session, offset=offset, sort="created_at:desc")
        new = add(items)
        print(f"[OLX-API] offset={offset}: {new} new ({len(items)} fetched)")
        if not items or new == 0:
            break
        api_ok = True
        time.sleep(random.uniform(0.5, 1.0))

    # ── Pass 2: JSON API (price asc) ──────────────────────────
    for offset in range(0, 100, 50):
        items = _fetch_api(session, offset=offset, sort="filter_float_price:asc")
        new = add(items)
        print(f"[OLX-API-price] offset={offset}: {new} new")
        if not items or new == 0:
            break
        time.sleep(random.uniform(0.5, 1.0))

    # ── Pass 3: HTML fallback if API gave nothing ─────────────
    if not api_ok:
        print("[OLX] API failed, falling back to HTML")
        html_session = _html_session()
        for page in range(1, 6):
            url = SORT_NEW if page == 1 else f"{SORT_NEW}&page={page}"
            try:
                r = html_session.get(url, timeout=20)
                if r.status_code != 200:
                    break
                items = _parse_page(r.text[:200_000])
                new = add(items)
                print(f"[OLX-HTML] page={page}: {new} new")
                if new == 0 and page >= 2:
                    break
                time.sleep(random.uniform(2.0, 3.0))
            except Exception as e:
                print(f"[OLX-HTML] page={page} error: {e}")
                break

    print(f"[OLX] Total: {len(results)}")
    return results
