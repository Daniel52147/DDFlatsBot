"""
Gratka parser — scrapes listing page with JSON-LD + HTML card fallback.
Falls back to domiporta.pl if Gratka is blocked.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

GRATKA_BASE = "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem?sort=newest"
GRATKA_PRICE_ASC = "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem?sort=price_asc"
DOMIPORTA_BASE = "https://www.domiporta.pl/mieszkanie/wynajme/mazowieckie/warszawa"


def _session(referer: str = "https://gratka.pl/"):
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
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


# ── Gratka parsers ────────────────────────────────────────────

def _parse_gratka_json_ld(html: str) -> list:
    results = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
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
                url = offer.get("url") or ""
                if not name or not url or len(name) < 10:
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
                rooms = None
                rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', name, re.I)
                if rm:
                    rooms = int(rm.group(1))
                area = None
                am = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', name)
                if am:
                    try:
                        area = float(am.group(1).replace(",", "."))
                    except Exception:
                        pass
                results.append({
                    "title": name, "price": price, "district": district,
                    "rooms": rooms, "area": area, "floor": None, "furnished": 0,
                    "link": url, "image": image, "source": "Gratka",
                })

        # Pattern 2: ItemList
        if data.get("@type") == "ItemList":
            for el in data.get("itemListElement", []):
                item = el.get("item", el) if isinstance(el, dict) else {}
                name = (item.get("name") or "").strip()
                url = item.get("url") or ""
                if not name or not url or len(name) < 10:
                    continue
                price_spec = item.get("offers") or {}
                price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                results.append({
                    "title": name, "price": price, "district": "Warszawa",
                    "rooms": None, "area": None, "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": "Gratka",
                })
    return results


def _parse_gratka_html_cards(html: str) -> list:
    results = []
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    for article in articles:
        try:
            url_m = re.search(r'href="(https://gratka\.pl/nieruchomosci/[^"]+)"', article)
            if not url_m or url_m.group(1).count("/") < 5:
                continue
            url = url_m.group(1)
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
            lm = re.search(r'<[^>]*class="[^"]*location[^"]*"[^>]*>([^<]{3,60})<', article, re.I)
            if lm:
                district = lm.group(1).strip()
            rooms = None
            rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
            if rm:
                rooms = int(rm.group(1))
            # Image
            img_m = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', article, re.I)
            image = img_m.group(1) if img_m else ""
            results.append({
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": image, "source": "Gratka",
            })
        except Exception:
            continue
    return results


# ── Domiporta fallback ────────────────────────────────────────

def _parse_domiporta_page(html: str) -> list:
    results = []

    # Try JSON-LD first
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
            if not isinstance(data, dict):
                continue
            if data.get("@type") == "ItemList":
                for el in data.get("itemListElement", []):
                    item = el.get("item", el) if isinstance(el, dict) else {}
                    name = (item.get("name") or "").strip()
                    url = item.get("url") or ""
                    if not name or not url or len(name) < 10:
                        continue
                    price_spec = item.get("offers") or {}
                    price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                    addr = item.get("address") or {}
                    district = (addr.get("addressLocality") or "Warszawa") if isinstance(addr, dict) else "Warszawa"
                    results.append({
                        "title": name, "price": price, "district": district,
                        "rooms": None, "area": None, "floor": None, "furnished": 0,
                        "link": url, "image": "", "source": "Gratka",
                    })
        except Exception:
            continue

    if results:
        return results

    # HTML card fallback
    cards = re.findall(r'<(?:article|div)[^>]*class="[^"]*(?:listing|offer|property)[^"]*"[^>]*>(.*?)</(?:article|div)>', html, re.DOTALL | re.IGNORECASE)
    for card in cards:
        try:
            url_m = re.search(r'href="(https://www\.domiporta\.pl/[^"]+)"', card)
            if not url_m:
                continue
            url = url_m.group(1)
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
                "rooms": None, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": "", "source": "Gratka",
            })
        except Exception:
            continue
    return results


def parse_gratka() -> list:
    results = []
    seen = set()

    def add(items):
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)

    # Two passes: newest first, then price_asc (catches different listings)
    urls_to_try = [GRATKA_BASE, GRATKA_PRICE_ASC]
    gratka_ok = False

    for base_url in urls_to_try:
        session = _session("https://gratka.pl/")
        # Only 3 pages per sort — we run every 10 min so page 1-3 is enough for new listings
        for page in range(1, 4):
            url = base_url if page == 1 else f"{base_url}&page={page}"
            try:
                r = session.get(url, timeout=25)
                html = r.text
                print(f"[Gratka] Page {page} status={r.status_code} size={len(html)}")

                if r.status_code != 200:
                    print(f"[Gratka] Blocked (status {r.status_code})")
                    break

                page_results = _parse_gratka_json_ld(html)
                if not page_results:
                    page_results = _parse_gratka_html_cards(html)

                if page_results:
                    add(page_results)
                    gratka_ok = True
                    print(f"[Gratka] Page {page}: {len(page_results)} listings")
                else:
                    snippet = html[:300].replace("\n", " ")
                    print(f"[Gratka] Page {page}: 0 listings. Snippet: {snippet}")
                    if page == 1:
                        break

                time.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                print(f"[Gratka] Page {page} error: {e}")
                break

    # Fallback: Domiporta
    if not gratka_ok:
        print("[Gratka] Trying Domiporta fallback...")
        session2 = _session("https://www.domiporta.pl/")
        for page in range(1, 4):
            url = DOMIPORTA_BASE if page == 1 else f"{DOMIPORTA_BASE}?PageNumber={page}"
            try:
                r = session2.get(url, timeout=25)
                html = r.text
                print(f"[Domiporta] Page {page} status={r.status_code} size={len(html)}")
                page_results = _parse_domiporta_page(html)
                if page_results:
                    add(page_results)
                    print(f"[Domiporta] Page {page}: {len(page_results)} listings")
                else:
                    snippet = html[:300].replace("\n", " ")
                    print(f"[Domiporta] Page {page}: 0. Snippet: {snippet}")
                time.sleep(random.uniform(1.5, 2.5))
            except Exception as e:
                print(f"[Domiporta] Page {page} error: {e}")

    print(f"[Gratka] Found {len(results)} listings")
    return results
