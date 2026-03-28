"""
Daily rental parser for Warsaw.
Sources:
  1. OLX.pl — "na doby" listings (real prices)
  2. Nocowanie.pl — Polish short-term platform
  3. Noclegi.pl — another Polish platform

Returns list of dicts: {title, price_per_night, total_price, district, link, image, source, rating, reviews}
"""
import re
import json
import time
import random
import requests
from datetime import datetime, timedelta
from config import USER_AGENTS


def _session(referer: str = "https://www.olx.pl/") -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,ru;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
        "Referer": referer,
    })
    return s


def _price(val) -> int:
    if not val:
        return 0
    try:
        return int(float(re.sub(r"[^\d.,]", "", str(val)).replace(",", ".")))
    except Exception:
        digits = re.sub(r"\D", "", str(val))
        return int(digits) if digits else 0


# ── OLX посуточно ─────────────────────────────────────────────

def _parse_olx_daily(html: str) -> list:
    results = []
    # Try JSON-LD first
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
        if '"offers"' not in script or len(script) < 200:
            continue
        try:
            d = json.loads(script[script.find('{'):])
            if d.get('@type') != 'Product':
                continue
            outer = d.get('offers', {})
            items = outer.get('offers', []) if isinstance(outer, dict) else []
            for item in items:
                name = (item.get('name') or '').strip()
                url = item.get('url') or ''
                if not name or not url:
                    continue
                price = _price(item.get('price', 0))
                if price < 50 or price > 2000:  # filter: 50-2000 zł/night
                    continue
                imgs = item.get('image') or []
                image = imgs[0] if imgs else ''
                area_obj = item.get('areaServed') or {}
                district = (area_obj.get('name') if isinstance(area_obj, dict) else '') or 'Warszawa'
                results.append({
                    'title': name,
                    'price_per_night': price,
                    'district': district,
                    'link': url.split('?')[0],
                    'image': image,
                    'source': 'OLX',
                    'rating': None,
                    'reviews': None,
                })
        except Exception:
            continue
    return results


def search_olx_daily(checkin: str, checkout: str, guests: int = 1, district: str = "") -> list:
    """Search OLX for short-term rentals."""
    session = _session()
    base = "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/"
    params = "?search%5Bfilter_enum_type%5D%5B0%5D=na-doby&search%5Border%5D=filter_float_price%3Aasc"
    results = []
    seen = set()

    for page in range(1, 4):
        url = f"{base}{params}" if page == 1 else f"{base}{params}&page={page}"
        try:
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                break
            html = r.text[:200_000]
            items = _parse_olx_daily(html)
            for item in items:
                if item['link'] not in seen:
                    seen.add(item['link'])
                    results.append(item)
            if not items:
                break
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            print(f"[Daily/OLX] page={page} error: {e}")
            break

    print(f"[Daily/OLX] Found {len(results)} listings")
    return results


# ── Nocowanie.pl ──────────────────────────────────────────────

def search_nocowanie(checkin: str, checkout: str, guests: int = 1) -> list:
    """Search nocowanie.pl for Warsaw short-term rentals."""
    session = _session("https://nocowanie.pl/")
    # checkin format: YYYY-MM-DD → nocowanie uses DD.MM.YYYY
    try:
        ci = datetime.strptime(checkin, "%Y-%m-%d").strftime("%d.%m.%Y")
        co = datetime.strptime(checkout, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        ci = co = ""

    url = (
        f"https://nocowanie.pl/noclegi/warszawa/apartamenty/"
        f"?data_od={ci}&data_do={co}&osoby={guests}&sort=cena_asc"
    )
    results = []
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return results
        html = r.text[:200_000]

        # Parse listing cards
        cards = re.split(r'<(?:article|div)[^>]+class="[^"]*(?:offer|listing|item)[^"]*"', html)
        for card in cards[1:21]:
            try:
                # Title
                title_m = re.search(r'<(?:h2|h3|h4)[^>]*>([^<]{5,100})<', card, re.I)
                if not title_m:
                    continue
                title = title_m.group(1).strip()

                # URL
                url_m = re.search(r'href="(https://nocowanie\.pl/[^"]{10,})"', card)
                if not url_m:
                    continue
                link = url_m.group(1)

                # Price
                price_m = re.search(r'(\d[\d\s]{1,5})\s*(?:zł|PLN)', card, re.I)
                price = _price(price_m.group(1)) if price_m else 0
                if price < 50 or price > 3000:
                    continue

                # Image
                img_m = re.search(r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', card, re.I)
                image = img_m.group(1) if img_m else ""

                # Rating
                rating_m = re.search(r'(\d+[.,]\d+)\s*/\s*10', card)
                rating = float(rating_m.group(1).replace(",", ".")) if rating_m else None

                results.append({
                    'title': title,
                    'price_per_night': price,
                    'district': 'Warszawa',
                    'link': link,
                    'image': image,
                    'source': 'Nocowanie.pl',
                    'rating': rating,
                    'reviews': None,
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[Daily/Nocowanie] error: {e}")

    print(f"[Daily/Nocowanie] Found {len(results)} listings")
    return results


# ── Main search function ──────────────────────────────────────

def search_daily_rentals(checkin: str, checkout: str, guests: int = 1, district: str = "Warszawa") -> list:
    """
    Search all sources for daily rentals.
    Returns sorted list by price_per_night ASC.
    """
    all_results = []

    # OLX
    try:
        olx = search_olx_daily(checkin, checkout, guests, district)
        all_results.extend(olx)
    except Exception as e:
        print(f"[Daily] OLX error: {e}")

    # Nocowanie
    try:
        noc = search_nocowanie(checkin, checkout, guests)
        all_results.extend(noc)
    except Exception as e:
        print(f"[Daily] Nocowanie error: {e}")

    # Calculate total price
    try:
        ci = datetime.strptime(checkin, "%Y-%m-%d")
        co = datetime.strptime(checkout, "%Y-%m-%d")
        nights = max(1, (co - ci).days)
    except Exception:
        nights = 1

    for r in all_results:
        r['nights'] = nights
        r['total_price'] = r['price_per_night'] * nights

    # Sort by price per night
    all_results.sort(key=lambda x: x['price_per_night'])

    # Deduplicate by title similarity
    seen_titles = set()
    unique = []
    for r in all_results:
        key = r['title'].lower()[:30]
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(r)

    return unique[:20]  # max 20 results
