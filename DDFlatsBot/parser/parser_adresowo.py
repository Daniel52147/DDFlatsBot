"""
Adresowo.pl parser — Polish real estate aggregator.
Replaces Szybko.pl (403 blocked on datacenter IPs).
Uses JSON-LD ItemList + HTML card fallback.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS, city_slug


def _adresowo_base(city: str) -> str:
    return f"https://adresowo.pl/mieszkania/wynajem/{city_slug(city)}"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://adresowo.pl/",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _price(val) -> int:
    if not val:
        return 0
    try:
        return int(float(re.sub(r'[^\d.]', '', str(val).replace(',', '.'))))
    except Exception:
        digits = re.sub(r'\D', '', str(val))
        return int(digits) if digits else 0


def _rooms_from_text(text: str):
    m = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', text, re.I)
    return int(m.group(1)) if m else None


def _area_from_text(text: str):
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', text, re.I)
    if m:
        try:
            return float(m.group(1).replace(',', '.'))
        except Exception:
            pass
    return None


def _parse_json_ld(html: str, default_city: str = "Warszawa") -> list:
    results = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        items = []
        if data.get("@type") == "ItemList":
            for el in data.get("itemListElement", []):
                item = el.get("item", el) if isinstance(el, dict) else {}
                items.append(item)
        elif data.get("@type") in ("Product", "Offer", "RealEstateListing"):
            items = [data]

        for item in items:
            name = (item.get("name") or "").strip()
            url = item.get("url") or ""
            if not name or len(name) < 8 or not url:
                continue
            if "adresowo.pl" not in url and not url.startswith("/"):
                continue

            # Price
            offers = item.get("offers") or {}
            price = 0
            if isinstance(offers, dict):
                price = _price(offers.get("price", 0))
            elif isinstance(offers, list) and offers:
                price = _price(offers[0].get("price", 0))

            # District
            addr = item.get("address") or {}
            district = default_city
            if isinstance(addr, dict):
                district = (
                    addr.get("addressLocality")
                    or addr.get("addressRegion")
                    or default_city
                )

            # Image
            image = item.get("image") or ""
            if isinstance(image, list):
                image = image[0] if image else ""

            if not url.startswith("http"):
                url = "https://adresowo.pl" + url

            results.append({
                "title": name,
                "price": price,
                "district": district,
                "rooms": _rooms_from_text(name),
                "area": _area_from_text(name),
                "floor": None,
                "furnished": 0,
                "link": url,
                "image": image,
                "source": "Adresowo",
            })

    return results


def _parse_html_cards(html: str, default_city: str = "Warszawa") -> list:
    results = []

    # Try article tags
    cards = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    if not cards:
        # Fallback: div with offer/listing class
        cards = re.findall(
            r'<div[^>]+class="[^"]*(?:offer|listing|property|ogloszenie)[^"]*"[^>]*>(.*?)</div\s*>',
            html, re.DOTALL | re.IGNORECASE
        )

    for card in cards:
        try:
            # URL
            url_m = re.search(r'href="(https?://adresowo\.pl/[^"]{10,})"', card)
            if not url_m:
                url_m = re.search(r'href="(/[^"]{10,})"', card)
            if not url_m:
                continue
            url = url_m.group(1)
            if not url.startswith("http"):
                url = "https://adresowo.pl" + url

            # Title
            title_m = (
                re.search(r'<(?:h2|h3|h4)[^>]*>([^<]{8,120})<', card, re.I)
                or re.search(r'title="([^"]{8,120})"', card)
                or re.search(r'alt="([^"]{8,120})"', card)
            )
            if not title_m:
                continue
            title = title_m.group(1).strip()

            # Price
            price = 0
            pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', card, re.I)
            if pm:
                price = _price(pm.group(1))

            # District
            district = default_city
            lm = re.search(
                r'<[^>]*class="[^"]*(?:location|address|city|district|dzielnica)[^"]*"[^>]*>([^<]{3,60})<',
                card, re.I
            )
            if lm:
                district = lm.group(1).strip() or default_city

            # Image
            img_m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', card, re.I)
            image = img_m.group(1) if img_m else ""

            results.append({
                "title": title,
                "price": price,
                "district": district,
                "rooms": _rooms_from_text(title),
                "area": _area_from_text(title),
                "floor": None,
                "furnished": 0,
                "link": url,
                "image": image,
                "source": "Adresowo",
            })
        except Exception:
            continue

    return results


def parse_adresowo(city: str = "Warszawa") -> list:
    """Parse Adresowo for the specified city."""
    from database.db import get_conn
    from validation.integration import ValidationPipeline
    
    base_url = _adresowo_base(city)
    print(f"[Adresowo/{city}] Starting parse (slug={city_slug(city)})...")
    
    # Initialize validation pipeline
    conn = get_conn()
    pipeline = ValidationPipeline(conn)
    
    results = []
    seen = set()
    session = _session()
    validated_count = 0
    rejected_count = 0

    for page in range(1, 6):
        url = base_url if page == 1 else f"{base_url}?page={page}"
        try:
            r = session.get(url, timeout=25)
            print(f"[Adresowo] Page {page} status={r.status_code} size={len(r.text)}")

            if r.status_code == 404:
                break
            if r.status_code != 200:
                print(f"[Adresowo] Blocked (status {r.status_code})")
                break

            page_results = _parse_json_ld(r.text, default_city=city)
            if not page_results:
                page_results = _parse_html_cards(r.text, default_city=city)

            new = 0
            for apt in page_results:
                if apt["link"] not in seen:
                    seen.add(apt["link"])
                    apt["source_city"] = city
                    # Validate before adding to results
                    validated_apt = pipeline.process_listing(apt, city)
                    if validated_apt:
                        results.append(validated_apt)
                        validated_count += 1
                        new += 1
                    else:
                        rejected_count += 1

            print(f"[Adresowo] Page {page}: {new} listings")
            if new == 0 and page >= 2:
                break

            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Adresowo] Page {page} error: {e}")
            break

    conn.close()
    print(f"[Adresowo] Total: {len(results)} listings (validated: {validated_count}, rejected: {rejected_count})")
    return results
