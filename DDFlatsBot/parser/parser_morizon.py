"""
Morizon parser — __NEXT_DATA__ JSON + JSON-LD + HTML cards.
Falls back to nieruchomosci-online.pl if Morizon is blocked.
"""
import random
import re
import json
import time
import requests
from config import USER_AGENTS

MORIZON_BASE = "https://www.morizon.pl/do-wynajecia/mieszkania/warszawa/"
NIERUCH_BASE = "https://www.nieruchomosci-online.pl/szukaj.html"


def _session(referer: str = "https://www.morizon.pl/"):
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


# ── Morizon parsers ───────────────────────────────────────────

def _parse_morizon_next_data(html: str) -> list:
    """Extract from __NEXT_DATA__ if Morizon uses Next.js."""
    results = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return results
    try:
        data = json.loads(m.group(1))
        page_props = data.get("props", {}).get("pageProps", {})

        def find_items(obj, depth=0):
            if depth > 6:
                return []
            if isinstance(obj, list) and len(obj) > 0:
                if isinstance(obj[0], dict) and ("slug" in obj[0] or "title" in obj[0] or "url" in obj[0]):
                    return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    found = find_items(v, depth + 1)
                    if found:
                        return found
            return []

        items = find_items(page_props)
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or item.get("name") or "").strip()
            url = item.get("url") or item.get("link") or item.get("slug") or ""
            if not title or not url or len(title) < 5:
                continue
            if not url.startswith("http"):
                url = f"https://www.morizon.pl{url}"
            price = _price(item.get("price") or item.get("totalPrice") or 0)
            district = (item.get("district") or item.get("city") or "Warszawa")
            results.append({
                "title": title, "price": price, "district": str(district),
                "rooms": None, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": "", "source": "Morizon",
            })
    except Exception as e:
        print(f"[Morizon] __NEXT_DATA__ error: {e}")
    return results


def _parse_morizon_json_ld(html: str) -> list:
    results = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

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
                    "link": url, "image": image, "source": "Morizon",
                })

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
                    "link": url, "image": "", "source": "Morizon",
                })
    return results


def _parse_morizon_html_cards(html: str) -> list:
    results = []
    articles = re.findall(r'<article[^>]*>(.*?)</article>', html, re.DOTALL | re.IGNORECASE)
    for article in articles:
        try:
            url_m = re.search(r'href="(https://www\.morizon\.pl/oferta/[^"]+)"', article)
            if not url_m:
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
            lm = re.search(r'<[^>]*class="[^"]*(?:location|address)[^"]*"[^>]*>([^<]{3,60})<', article, re.I)
            if lm:
                district = lm.group(1).strip()
            rooms = None
            rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
            if rm:
                rooms = int(rm.group(1))
            results.append({
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": None, "floor": None, "furnished": 0,
                "link": url, "image": "", "source": "Morizon",
            })
        except Exception:
            continue
    return results


# ── Nieruchomosci-online fallback ─────────────────────────────

def _parse_nieruch_online(html: str) -> list:
    """Parse nieruchomosci-online.pl listing page."""
    results = []

    # Try JSON-LD
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
                        "link": url, "image": "", "source": "Morizon",
                    })
        except Exception:
            continue

    if results:
        return results

    # HTML fallback
    cards = re.findall(
        r'<(?:article|li|div)[^>]*class="[^"]*(?:listing|offer|property|item)[^"]*"[^>]*>(.*?)</(?:article|li|div)>',
        html, re.DOTALL | re.IGNORECASE
    )
    for card in cards:
        try:
            url_m = re.search(r'href="(https://[^"]*nieruchomosci-online[^"]+)"', card)
            if not url_m:
                continue
            url = url_m.group(1)
            title_m = re.search(r'<(?:h2|h3|h4|a)[^>]*>([^<]{10,120})<', card, re.I)
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
                "link": url, "image": "", "source": "Morizon",
            })
        except Exception:
            continue
    return results


def parse_morizon() -> list:
    results = []
    seen = set()

    def add(items):
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)

    # Try Morizon first
    session = _session("https://www.morizon.pl/")
    morizon_ok = False
    for page in range(1, 6):
        url = MORIZON_BASE if page == 1 else f"{MORIZON_BASE}?page={page}"
        try:
            r = session.get(url, timeout=25)
            html = r.text
            print(f"[Morizon] Page {page} status={r.status_code} size={len(html)}")

            if r.status_code != 200:
                print(f"[Morizon] Blocked (status {r.status_code})")
                break

            page_results = _parse_morizon_next_data(html)
            if not page_results:
                page_results = _parse_morizon_json_ld(html)
            if not page_results:
                page_results = _parse_morizon_html_cards(html)

            if page_results:
                add(page_results)
                morizon_ok = True
                print(f"[Morizon] Page {page}: {len(page_results)} listings")
            else:
                snippet = html[:300].replace("\n", " ")
                print(f"[Morizon] Page {page}: 0 listings. Snippet: {snippet}")
                if page == 1:
                    break

            time.sleep(random.uniform(2, 3))
        except Exception as e:
            print(f"[Morizon] Page {page} error: {e}")
            break

    # Fallback: nieruchomosci-online.pl
    if not morizon_ok:
        print("[Morizon] Trying nieruchomosci-online fallback...")
        session2 = _session("https://www.nieruchomosci-online.pl/")
        params = {
            "transaction": "2",   # wynajem
            "category": "1",      # mieszkania
            "city_id": "26",      # Warszawa
            "page": 1,
        }
        for page in range(1, 4):
            params["page"] = page
            try:
                r = session2.get(NIERUCH_BASE, params=params, timeout=25)
                html = r.text
                print(f"[Nieruch-online] Page {page} status={r.status_code} size={len(html)}")
                page_results = _parse_nieruch_online(html)
                if page_results:
                    add(page_results)
                    print(f"[Nieruch-online] Page {page}: {len(page_results)} listings")
                else:
                    snippet = html[:300].replace("\n", " ")
                    print(f"[Nieruch-online] Page {page}: 0. Snippet: {snippet}")
                time.sleep(random.uniform(2, 3))
            except Exception as e:
                print(f"[Nieruch-online] Page {page} error: {e}")

    print(f"[Morizon] Found {len(results)} listings")
    return results
