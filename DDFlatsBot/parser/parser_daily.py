"""
Daily / short-term rental search across Polish cities.
Sources: OLX (na doby), Nocowanie.pl, OLX JSON API fallback.
"""
import re
import json
import time
import random
import requests
from datetime import datetime
from config import USER_AGENTS, CITIES, NOCOWANIE_SLUGS


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


def _api_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Referer": "https://www.olx.pl/",
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


def _daily_keywords_ok(title: str) -> bool:
    """Keep only short-term rental listings."""
    t = title.lower()
    long_term = ("miesiąc", "miesiecz", "miesięcz", "długotermin", "na rok", "roczn")
    if any(x in t for x in long_term):
        return False
    markers = (
        "na doby", "doby", "dobow", "nocleg", "noclegi", "krótkotermin",
        "krótki", "weekend", "dziennie", "/dob", "pobyt", "wakacj",
        "święta", "ferie", "dobie", "overnight",
    )
    return any(m in t for m in markers)


def _item_from_offer(offer: dict, city_name: str) -> dict | None:
    try:
        title = (offer.get("title") or "").strip()
        if not title or len(title) < 5:
            return None
        if not _daily_keywords_ok(title):
            return None
        url = offer.get("url") or ""
        if not url:
            return None
        price = 0
        price_obj = offer.get("price") or {}
        if isinstance(price_obj, dict):
            price = _price(price_obj.get("value", 0))
        if price < 40 or price > 5000:
            return None
        loc = offer.get("location") or {}
        district = city_name
        if isinstance(loc, dict):
            d = loc.get("district") or {}
            c = loc.get("city") or {}
            district = (
                (d.get("name") if isinstance(d, dict) else d)
                or (c.get("name") if isinstance(c, dict) else c)
                or city_name
            )
        photos = offer.get("photos") or []
        image = ""
        if photos and isinstance(photos[0], dict):
            image = (photos[0].get("link") or "").replace("{width}", "400").replace("{height}", "300")
        return {
            "title": title,
            "price_per_night": price,
            "district": str(district),
            "city": city_name,
            "link": url.split("?")[0],
            "image": image,
            "source": "OLX",
            "rating": None,
            "reviews": None,
        }
    except Exception:
        return None


def search_olx_daily_api(city_key: str, max_pages: int = 3) -> list:
    """OLX JSON API — city-specific short-term listings."""
    cfg = CITIES.get(city_key, CITIES["Warszawa"])
    city_id = cfg.get("city_id_olx", 39610)
    region_id = cfg.get("region_id_olx", 7)
    session = _api_session()
    results = []
    seen = set()

    for page in range(max_pages):
        offset = page * 50
        params = {
            "offset": offset,
            "limit": 50,
            "category_id": 15,
            "region_id": region_id,
            "city_id": city_id,
            "sort_by": "created_at:desc",
        }
        try:
            r = session.get("https://www.olx.pl/api/v1/offers/", params=params, timeout=15)
            if r.status_code != 200:
                break
            offers = (r.json().get("data") or [])
            if not offers:
                break
            for offer in offers:
                item = _item_from_offer(offer, city_key)
                if item and item["link"] not in seen:
                    seen.add(item["link"])
                    results.append(item)
            time.sleep(random.uniform(0.4, 0.9))
        except Exception as e:
            print(f"[Daily/OLX-API/{city_key}] {e}")
            break

    print(f"[Daily/OLX-API/{city_key}] {len(results)} listings")
    return results


def _parse_olx_daily_html(html: str, city_name: str) -> list:
    results = []
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
                if not name or not url or not _daily_keywords_ok(name):
                    continue
                price = _price(item.get("price", 0))
                if price < 40 or price > 5000:
                    continue
                imgs = item.get("image") or []
                image = imgs[0] if imgs else ""
                area_obj = item.get("areaServed") or {}
                district = (area_obj.get("name") if isinstance(area_obj, dict) else "") or city_name
                results.append({
                    "title": name,
                    "price_per_night": price,
                    "district": district,
                    "city": city_name,
                    "link": url.split("?")[0],
                    "image": image,
                    "source": "OLX",
                    "rating": None,
                    "reviews": None,
                })
        except Exception:
            continue
    return results


def search_olx_daily(city_key: str = "Warszawa") -> list:
    """HTML scrape OLX na-doby for a given city."""
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
            r = session.get(url, timeout=15)
            if r.status_code != 200:
                break
            items = _parse_olx_daily_html(r.text[:250_000], city_key)
            for item in items:
                if item["link"] not in seen:
                    seen.add(item["link"])
                    results.append(item)
            if not items:
                break
            time.sleep(random.uniform(0.8, 1.5))
        except Exception as e:
            print(f"[Daily/OLX/{city_key}] page={page} error: {e}")
            break

    print(f"[Daily/OLX/{city_key}] HTML {len(results)} listings")
    return results


def search_nocowanie(checkin: str, checkout: str, guests: int = 1, city_key: str = "Warszawa") -> list:
    """Nocowanie.pl — city-specific short-term."""
    slug = NOCOWANIE_SLUGS.get(city_key, "warszawa")
    session = _session("https://nocowanie.pl/")
    try:
        ci = datetime.strptime(checkin, "%Y-%m-%d").strftime("%d.%m.%Y")
        co = datetime.strptime(checkout, "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        ci = co = ""

    url = (
        f"https://nocowanie.pl/noclegi/{slug}/apartamenty/"
        f"?data_od={ci}&data_do={co}&osoby={guests}&sort=cena_asc"
    )
    results = []
    try:
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            return results
        html = r.text[:250_000]
        links = re.findall(r'href="(https://nocowanie\.pl/[^"]{15,})"', html)
        titles = re.findall(r'<(?:h2|h3|h4)[^>]*>([^<]{5,120})<', html, re.I)
        prices = re.findall(r"(\d[\d\s]{1,5})\s*(?:zł|PLN)", html, re.I)
        imgs = re.findall(
            r'src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', html, re.I
        )
        for i, link in enumerate(links[:25]):
            if link in {x["link"] for x in results}:
                continue
            title = titles[i].strip() if i < len(titles) else f"Nocleg {city_key}"
            price = _price(prices[i]) if i < len(prices) else 0
            if price < 40 or price > 5000:
                continue
            image = imgs[i] if i < len(imgs) else ""
            rating_m = re.search(r"(\d+[.,]\d+)\s*/\s*10", html)
            rating = float(rating_m.group(1).replace(",", ".")) if rating_m else None
            results.append({
                "title": title,
                "price_per_night": price,
                "district": city_key,
                "city": city_key,
                "link": link,
                "image": image,
                "source": "Nocowanie.pl",
                "rating": rating,
                "reviews": None,
            })
    except Exception as e:
        print(f"[Daily/Nocowanie/{city_key}] error: {e}")

    print(f"[Daily/Nocowanie/{city_key}] {len(results)} listings")
    return results


def search_daily_rentals(
    checkin: str,
    checkout: str,
    guests: int = 1,
    city_key: str = "Warszawa",
) -> list:
    """Search all sources for daily rentals in a specific city."""
    all_results = []

    try:
        api_items = search_olx_daily_api(city_key)
        all_results.extend(api_items)
    except Exception as e:
        print(f"[Daily] OLX API {city_key}: {e}")

    if len(all_results) < 5:
        try:
            all_results.extend(search_olx_daily(city_key))
        except Exception as e:
            print(f"[Daily] OLX HTML {city_key}: {e}")

    try:
        all_results.extend(search_nocowanie(checkin, checkout, guests, city_key))
    except Exception as e:
        print(f"[Daily] Nocowanie {city_key}: {e}")

    try:
        ci = datetime.strptime(checkin, "%Y-%m-%d")
        co = datetime.strptime(checkout, "%Y-%m-%d")
        nights = max(1, (co - ci).days)
    except Exception:
        nights = 1

    for r in all_results:
        r["nights"] = nights
        r["total_price"] = r["price_per_night"] * nights

    all_results.sort(key=lambda x: x["price_per_night"])

    seen = set()
    unique = []
    for r in all_results:
        key = (r["link"], r["title"].lower()[:35])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique[:20]
