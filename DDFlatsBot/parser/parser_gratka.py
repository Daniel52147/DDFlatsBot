import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE = "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem"


def _h():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://gratka.pl/",
        "Connection": "keep-alive",
    }


def _price(text: str) -> int:
    digits = "".join(c for c in str(text) if c.isdigit())
    return int(digits) if digits else 0


def _parse_html(html: str) -> list:
    results = []

    # Try JSON-LD structured data first
    json_ld_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    for block in json_ld_blocks:
        try:
            data = json.loads(block)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") not in ("Product", "RealEstateListing", "Offer"):
                    continue
                name = item.get("name", "").strip()
                url = item.get("url", "")
                price_obj = item.get("offers", {})
                price = _price(price_obj.get("price", 0)) if isinstance(price_obj, dict) else 0
                if name and url:
                    results.append({
                        "title": name, "price": price, "district": "Warsaw",
                        "rooms": None, "area": None, "floor": None,
                        "furnished": 0, "link": url, "image": "", "source": "Gratka",
                    })
        except Exception:
            continue

    if results:
        return results

    # Fallback: extract links from HTML
    # Gratka listing URLs pattern: /nieruchomosci/mieszkanie-na-wynajem/...
    links = re.findall(
        r'href="(https://gratka\.pl/nieruchomosci/[^"]+?)"',
        html
    )
    # Filter to detail pages only (not category pages)
    seen = set()
    clean_links = []
    for l in links:
        # Skip pagination, category, filter pages
        if any(x in l for x in ["/wynajem\"", "/sprzedaz\"", "?", "#", "/warszawa\""]):
            continue
        if l not in seen and len(l) > 50:
            seen.add(l)
            clean_links.append(l)

    # Extract titles
    title_matches = re.findall(
        r'(?:class="[^"]*(?:title|name|heading)[^"]*"[^>]*>|<h[23][^>]*>)\s*([^<]{10,120})',
        html
    )
    # Extract prices
    price_matches = re.findall(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', html)

    for i, link in enumerate(clean_links[:40]):
        title = title_matches[i].strip() if i < len(title_matches) else f"Mieszkanie Warszawa #{i+1}"
        price = _price(price_matches[i]) if i < len(price_matches) else 0

        # Extract district from URL
        district = "Warsaw"
        m = re.search(r'/warszawa-([a-z\-]+)/', link)
        if m:
            district = m.group(1).replace("-", " ").title()

        results.append({
            "title": title, "price": price, "district": district,
            "rooms": None, "area": None, "floor": None,
            "furnished": 0, "link": link, "image": "", "source": "Gratka",
        })

    return results


def parse_gratka() -> list:
    results = []
    session = requests.Session()
    session.headers.update(_h())

    for page in range(1, 4):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
            page_results = _parse_html(r.text)
            results.extend(page_results)
            print(f"[Gratka] Page {page}: {len(page_results)} listings")
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"[Gratka] Page {page} error: {e}")

    print(f"[Gratka] Found {len(results)} listings")
    return results
