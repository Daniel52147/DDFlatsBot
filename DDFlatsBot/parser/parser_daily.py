"""
Daily / short-term rental search across Polish cities.
Sources: OLX na-doby, Otodom, Nocowanie.pl, local DB — within radius of selected city.
"""
import re
import json
import time
import random
import requests
from datetime import datetime
from config import (
    USER_AGENTS, CITIES, NOCOWANIE_SLUGS, FLATIO_SLUGS,
    get_cities_in_radius, SEARCH_RADIUS_KM_DEFAULT,
)

_DAILY_CACHE: dict = {}
_CACHE_TTL = 3600
_DAILY_KEYWORDS = (
    "doby", "nocleg", "krótko", "krótkotermin", "weekend", "pobyt",
    "na doby", "wynajem krótkoterminowy", "short",
)


def _session(referer: str = "https://www.olx.pl/") -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
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


def _parse_olx_daily_html(html: str, city_name: str) -> list:
    results = []
    seen = set()

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    for script in scripts:
        if '"offers"' not in script or len(script) < 200:
            continue
        try:
            d = json.loads(script[script.find("{") :])
            if d.get("@type") != "Product":
                continue
            outer = d.get("offers", {})
            items = outer.get("offers", []) if isinstance(outer, dict) else []
            for item in items:
                name = (item.get("name") or "").strip()
                url = item.get("url") or ""
                if not name or not url:
                    continue
                price = _price(item.get("price", 0))
                if price < 40 or price > 5000:
                    continue
                link = url.split("?")[0]
                if link in seen:
                    continue
                seen.add(link)
                imgs = item.get("image") or []
                image = imgs[0] if imgs else ""
                area_obj = item.get("areaServed") or {}
                district = (area_obj.get("name") if isinstance(area_obj, dict) else "") or city_name
                results.append({
                    "title": name,
                    "price_per_night": price,
                    "district": district,
                    "city": city_name,
                    "link": link,
                    "image": image,
                    "source": "OLX",
                    "rating": None,
                    "reviews": None,
                })
        except Exception:
            continue

    if len(results) < 3:
        for m in re.finditer(
            r'href="(https://www\.olx\.pl/d/oferta/[^"]+)"[^>]*>.*?(\d[\d\s]{2,5})\s*zł',
            html,
            re.I | re.DOTALL,
        ):
            link = m.group(1).split("?")[0]
            if link in seen:
                continue
            price = _price(m.group(2))
            if price < 40 or price > 5000:
                continue
            seen.add(link)
            slug = link.rstrip("/").split("/")[-1].replace("-", " ")[:60]
            results.append({
                "title": slug or "Oferta OLX",
                "price_per_night": price,
                "district": city_name,
                "city": city_name,
                "link": link,
                "image": "",
                "source": "OLX",
                "rating": None,
                "reviews": None,
            })

    return results


def search_olx_daily(city_key: str = "Warszawa") -> list:
    cfg = CITIES.get(city_key, CITIES["Warszawa"])
    slug = cfg.get("url_olx", "warszawa")
    session = _session()
    base = f"https://www.olx.pl/nieruchomosci/mieszkania/wynajem/{slug}/"
    params = "?search%5Bfilter_enum_type%5D%5B0%5D=na-doby&search%5Border%5D=filter_float_price%3Aasc"
    results = []
    seen = set()

    for page in range(1, 4):
        url = f"{base}{params}" if page == 1 else f"{base}{params}&page={page}"
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                break
            items = _parse_olx_daily_html(r.text[:400_000], city_key)
            for item in items:
                if item["link"] not in seen:
                    seen.add(item["link"])
                    results.append(item)
            if not items:
                break
            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            print(f"[Daily/OLX/{city_key}] page={page} error: {e}")
            break

    print(f"[Daily/OLX/{city_key}] {len(results)} listings")
    return results


def search_otodom_daily(city_key: str = "Warszawa") -> list:
    cfg = CITIES.get(city_key, CITIES["Warszawa"])
    slug = cfg.get("url_otodom", "warszawa")
    session = _session("https://www.otodom.pl/")
    results = []
    seen = set()

    for page in range(1, 4):
        url = (
            f"https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/{slug}"
            f"?limit=36&by=DEFAULT&direction=ASC&page={page}"
        )
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                break
            html = r.text[:500_000]
            found = 0
            for m in re.finditer(
                r'href="(https://www\.otodom\.pl/pl/oferta/[^"]+)"',
                html,
                re.I,
            ):
                link = m.group(1).split("?")[0]
                if link in seen:
                    continue
                chunk = html[max(0, m.start() - 200): m.end() + 800]
                title_m = re.search(r'title="([^"]{8,120})"', chunk)
                title = (title_m.group(1) if title_m else "").strip()
                if not title:
                    continue
                low = title.lower()
                if not any(k in low for k in _DAILY_KEYWORDS):
                    continue
                price_m = re.search(r"(\d[\d\s]{2,5})\s*zł", chunk, re.I)
                price = _price(price_m.group(1)) if price_m else 0
                if price and (price < 40 or price > 5000):
                    continue
                seen.add(link)
                found += 1
                results.append({
                    "title": title,
                    "price_per_night": price or 0,
                    "district": city_key,
                    "city": city_key,
                    "link": link,
                    "image": "",
                    "source": "Otodom",
                    "rating": None,
                    "reviews": None,
                })
            if not found:
                break
            time.sleep(random.uniform(0.4, 0.8))
        except Exception as e:
            print(f"[Daily/Otodom/{city_key}] page={page} {e}")
            break

    print(f"[Daily/Otodom/{city_key}] {len(results)} listings")
    return [r for r in results if r.get("price_per_night", 0) >= 40]


def search_nocowanie(checkin: str, checkout: str, guests: int = 1, city_key: str = "Warszawa") -> list:
    slug = NOCOWANIE_SLUGS.get(city_key, "warszawa")
    session = _session("https://nocowanie.pl/")
    try:
        ci = datetime.strptime(checkin, "%Y-%m-%d").strftime("%d.%m.%Y")
        co = datetime.strptime(checkout, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        ci = co = ""

    urls = [
        f"https://nocowanie.pl/noclegi/{slug}/apartamenty/?data_od={ci}&data_do={co}&osoby={guests}&sort=cena_asc",
        f"https://nocowanie.pl/noclegi/{slug}/?data_od={ci}&data_do={co}&osoby={guests}",
    ]
    results = []
    seen = set()
    for url in urls:
        try:
            r = session.get(url, timeout=20)
            if r.status_code != 200:
                continue
            html = r.text[:350_000]
            links = re.findall(r'href="(https://nocowanie\.pl/[^"]{15,})"', html)
            titles = re.findall(r'<(?:h2|h3|h4|a)[^>]*>([^<]{5,120})</', html, re.I)
            prices = re.findall(r"(\d[\d\s]{1,5})\s*(?:zł|PLN)", html, re.I)
            for i, link in enumerate(links[:35]):
                if link in seen or "/apartamenty" in link and link.count("/") < 4:
                    continue
                title = titles[i].strip() if i < len(titles) else f"Nocleg — {city_key}"
                if len(title) < 5:
                    continue
                price = _price(prices[i]) if i < len(prices) else 0
                if price and (price < 40 or price > 5000):
                    continue
                seen.add(link)
                results.append({
                    "title": title,
                    "price_per_night": price or 0,
                    "district": city_key,
                    "city": city_key,
                    "link": link,
                    "image": "",
                    "source": "Nocowanie.pl",
                    "rating": None,
                    "reviews": None,
                })
        except Exception as e:
            print(f"[Daily/Nocowanie/{city_key}] {e}")

    print(f"[Daily/Nocowanie/{city_key}] {len(results)} listings")
    return [r for r in results if r.get("price_per_night", 0) > 0]


def search_flatio_daily(city_key: str = "Warszawa") -> list:
    """Ready furnished apartments from Flatio short-term pages."""
    slug = FLATIO_SLUGS.get(city_key, "warszawa")
    session = _session("https://www.flatio.pl/")
    url = f"https://www.flatio.pl/najem-krotkoterminowy-{slug}"
    results = []
    seen = set()
    try:
        r = session.get(url, timeout=20)
        if r.status_code != 200:
            return results
        html = r.text[:500_000]
        for m in re.finditer(
            r'href="(https://www\.flatio\.pl/dzierzawa/[^"]+|/dzierzawa/[^"]+)"',
            html,
            re.I,
        ):
            raw = m.group(1)
            link = raw if raw.startswith("http") else f"https://www.flatio.pl{raw}"
            link = link.split("?")[0]
            if link in seen:
                continue
            chunk = html[max(0, m.start() - 100): m.end() + 600]
            title_m = re.search(
                r'(?:title|aria-label)="([^"]{8,100})"',
                chunk,
                re.I,
            )
            title = (title_m.group(1) if title_m else "").strip()
            if not title:
                slug_part = link.rstrip("/").split("/")[-1].replace("-", " ")[:70]
                title = slug_part or f"Flatio — {city_key}"
            price_m = re.search(r"(\d[\d\s]{2,5})\s*zł", chunk, re.I)
            monthly = _price(price_m.group(1)) if price_m else 0
            if monthly and (monthly < 800 or monthly > 20000):
                continue
            nightly = int(monthly / 30) if monthly else 0
            if nightly and nightly < 40:
                continue
            seen.add(link)
            results.append({
                "title": title[:100],
                "price_per_night": nightly or 0,
                "district": city_key,
                "city": city_key,
                "link": link,
                "image": "",
                "source": "Flatio",
                "rating": None,
                "reviews": None,
            })
    except Exception as e:
        print(f"[Daily/Flatio/{city_key}] {e}")

    print(f"[Daily/Flatio/{city_key}] {len(results)} listings")
    return [r for r in results if r.get("price_per_night", 0) >= 40]


def search_daily_rentals(
    checkin: str,
    checkout: str,
    guests: int = 1,
    city_key: str = "Warszawa",
    radius_km: int | float | None = None,
) -> list:
    if radius_km is None:
        radius_km = SEARCH_RADIUS_KM_DEFAULT

    cache_key = (city_key, checkin, checkout, guests, int(radius_km))
    cached = _DAILY_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    cities = get_cities_in_radius(city_key, float(radius_km))
    hub_cities = cities[:3]
    all_results = []
    seen_links = set()

    def _add(items):
        for item in items:
            link = item.get("link", "")
            if link and link not in seen_links:
                seen_links.add(link)
                all_results.append(item)

    for c in cities:
        try:
            _add(search_olx_daily(c))
        except Exception as e:
            print(f"[Daily] OLX {c}: {e}")

    for c in hub_cities:
        try:
            _add(search_otodom_daily(c))
        except Exception as e:
            print(f"[Daily] Otodom {c}: {e}")

    try:
        from database.db import get_daily_listings_from_db
        _add(get_daily_listings_from_db(cities, limit=25))
    except Exception as e:
        print(f"[Daily] DB: {e}")

    for c in hub_cities:
        try:
            _add(search_nocowanie(checkin, checkout, guests, c))
        except Exception as e:
            print(f"[Daily] Nocowanie {c}: {e}")
        try:
            _add(search_flatio_daily(c))
        except Exception as e:
            print(f"[Daily] Flatio {c}: {e}")

    try:
        ci = datetime.strptime(checkin, "%Y-%m-%d")
        co = datetime.strptime(checkout, "%Y-%m-%d")
        nights = max(1, (co - ci).days)
    except Exception:
        nights = 1

    for r in all_results:
        r["nights"] = nights
        if r.get("price_per_night"):
            r["total_price"] = r["price_per_night"] * nights

    all_results = [r for r in all_results if r.get("price_per_night", 0) >= 40]
    all_results.sort(key=lambda x: (0 if x.get("city") == city_key else 1, x["price_per_night"]))
    out = all_results[:35]
    _DAILY_CACHE[cache_key] = (time.time(), out)
    return out
