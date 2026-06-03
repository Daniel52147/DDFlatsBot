"""
Gratka parser — JSON-LD + HTML cards + Domiporta fallback.
Uses retry with exponential backoff to handle blocks.
"""
import random
import re
import json
import time
from parser._retry import make_session, fetch_with_retry

GRATKA_BASE      = "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem?sort=newest"
GRATKA_PRICE_ASC = "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem?sort=price_asc"
DOMIPORTA_BASE   = "https://www.domiporta.pl/mieszkanie/wynajme/mazowieckie/warszawa"


def _price(val) -> int:
    if not val:
        return 0
    try:
        return int(float(str(val).replace(",", ".")))
    except Exception:
        digits = "".join(c for c in str(val) if c.isdigit())
        return int(digits) if digits else 0


def _rooms(text: str):
    m = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', text, re.I)
    return int(m.group(1)) if m else None


def _area(text: str):
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', text, re.I)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except Exception:
            pass
    return None


def _parse_json_ld(html: str, source: str = "Gratka") -> list:
    results = []
    blocks = re.findall(r'<script[^>]*ld\+json[^>]*>([^<]{10,80000})</script>', html)
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        # Pattern 1: offers.offers list
        top = data.get("offers", {})
        if isinstance(top, dict):
            for offer in top.get("offers", []):
                if not isinstance(offer, dict):
                    continue
                name = (offer.get("name") or "").strip()
                url  = offer.get("url") or ""
                if not name or len(name) < 8 or not url:
                    continue
                price = _price(offer.get("price", 0))
                image = offer.get("image") or ""
                if isinstance(image, list):
                    image = image[0] if image else ""
                district = "Warszawa"
                io = offer.get("itemOffered") or {}
                if isinstance(io, dict):
                    addr = io.get("address") or {}
                    if isinstance(addr, dict):
                        district = addr.get("addressLocality") or "Warszawa"
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": _rooms(name), "area": _area(name),
                    "floor": None, "furnished": 0,
                    "link": url, "image": str(image), "source": source,
                })

        # Pattern 2: ItemList
        if data.get("@type") == "ItemList":
            for el in data.get("itemListElement", []):
                item = el.get("item", el) if isinstance(el, dict) else {}
                name = (item.get("name") or "").strip()
                url  = item.get("url") or ""
                if not name or len(name) < 8 or not url:
                    continue
                price_spec = item.get("offers") or {}
                price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                addr = item.get("address") or {}
                district = (addr.get("addressLocality") or "Warszawa") if isinstance(addr, dict) else "Warszawa"
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": _rooms(name), "area": _area(name),
                    "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": source,
                })
    return results


def _parse_html_cards(html: str, source: str = "Gratka") -> list:
    results = []
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    for article in articles:
        try:
            url_m = re.search(r'href="(https://gratka\.pl/nieruchomosci/[^"]+)"', article)
            if not url_m or url_m.group(1).count("/") < 5:
                continue
            url = url_m.group(1).split("?")[0]
            title_m = (
                re.search(r'<(?:h2|h3)[^>]*>([^<]{5,120})<', article, re.I) or
                re.search(r'title="([^"]{10,120})"', article)
            )
            if not title_m:
                continue
            title = title_m.group(1).strip()
            price = 0
            pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', article, re.I)
            if pm:
                price = _price(pm.group(1))
            district = "Warszawa"
            lm = re.search(r'class="[^"]*location[^"]*"[^>]*>([^<]{3,60})<', article, re.I)
            if lm:
                district = lm.group(1).strip() or "Warszawa"
            img_m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', article, re.I)
            image = img_m.group(1) if img_m else ""
            results.append({
                "title": title, "price": price, "district": district,
                "rooms": _rooms(title), "area": _area(title),
                "floor": None, "furnished": 0,
                "link": url, "image": image, "source": source,
            })
        except Exception:
            continue
    return results


def _parse_domiporta(html: str) -> list:
    results = _parse_json_ld(html, source="Gratka")
    if results:
        return results
    # HTML fallback
    cards = re.findall(
        r'<(?:article|div)[^>]*class="[^"]*(?:listing|offer|property)[^"]*"[^>]*>(.*?)</(?:article|div)>',
        html, re.DOTALL | re.IGNORECASE
    )
    for card in cards:
        try:
            url_m = re.search(r'href="(https://www\.domiporta\.pl/[^"]+)"', card)
            if not url_m:
                continue
            url = url_m.group(1).split("?")[0]
            title_m = re.search(r'<(?:h2|h3|h4)[^>]*>([^<]{5,120})<', card, re.I)
            if not title_m:
                continue
            title = title_m.group(1).strip()
            price = 0
            pm = re.search(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', card, re.I)
            if pm:
                price = _price(pm.group(1))
            results.append({
                "title": title, "price": price, "district": "Warszawa",
                "rooms": _rooms(title), "area": None,
                "floor": None, "furnished": 0,
                "link": url, "image": "", "source": "Gratka",
            })
        except Exception:
            continue
    return results


def parse_gratka(city: str = "Warszawa") -> list:
    """Parse Gratka for the specified city."""
    from database.db import get_conn
    from validation.integration import ValidationPipeline
    
    print(f"[Gratka/{city}] Starting parse (Warszawa only for now)...")
    
    # Initialize validation pipeline
    conn = get_conn()
    pipeline = ValidationPipeline(conn)
    
    results = []
    seen = set()
    validated_count = 0
    rejected_count = 0

    def add(items):
        nonlocal validated_count, rejected_count
        n = 0
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                apt["source_city"] = city
                # Validate before adding to results
                validated_apt = pipeline.process_listing(apt, city)
                if validated_apt:
                    results.append(validated_apt)
                    validated_count += 1
                    n += 1
                else:
                    rejected_count += 1
        return n

    gratka_ok = False
    for base_url in [GRATKA_BASE, GRATKA_PRICE_ASC]:
        from config import PARSER_COOKIES
        cookie_str = PARSER_COOKIES.get("Gratka", "")
        session = make_session(referer="https://gratka.pl/", cookie_str=cookie_str)
        for page in range(1, 4):
            url = base_url if page == 1 else f"{base_url}&page={page}"
            # Warm up on first page only
            warmup = "https://gratka.pl/" if page == 1 else ""
            status, html = fetch_with_retry(session, url, max_retries=3, backoff_base=3.0, warmup_url=warmup)
            print(f"[Gratka] page={page} status={status} size={len(html)}")
            if status != 200:
                break
            items = _parse_json_ld(html) or _parse_html_cards(html)
            new = add(items)
            print(f"[Gratka] page={page}: {new} new")
            if new > 0:
                gratka_ok = True
            elif page >= 2:
                break
            time.sleep(random.uniform(2.0, 3.5))

    if not gratka_ok:
        print("[Gratka] Trying Domiporta fallback...")
        session2 = make_session(referer="https://www.domiporta.pl/")
        for page in range(1, 4):
            url = DOMIPORTA_BASE if page == 1 else f"{DOMIPORTA_BASE}?PageNumber={page}"
            status, html = fetch_with_retry(session2, url, max_retries=2)
            print(f"[Domiporta] page={page} status={status} size={len(html)}")
            if status != 200:
                break
            items = _parse_domiporta(html)
            new = add(items)
            print(f"[Domiporta] page={page}: {new} new")
            if new == 0 and page >= 2:
                break
            time.sleep(random.uniform(2.0, 3.0))

    conn.close()
    print(f"[Gratka] Total: {len(results)} (validated: {validated_count}, rejected: {rejected_count})")
    return results
