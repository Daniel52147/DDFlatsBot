import random
import re
import json
import time
import requests
from config import USER_AGENTS

BASE = "https://www.morizon.pl/do-wynajecia/mieszkania/warszawa/"


def _h():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.morizon.pl/",
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
                if item.get("@type") not in ("Product", "RealEstateListing", "Offer", "Apartment"):
                    continue
                name = item.get("name", "").strip()
                url = item.get("url", "")
                price_obj = item.get("offers", {})
                price = _price(price_obj.get("price", 0)) if isinstance(price_obj, dict) else 0
                if name and url:
                    results.append({
                        "title": name, "price": price, "district": "Warsaw",
                        "rooms": None, "area": None, "floor": None,
                        "furnished": 0, "link": url, "image": "", "source": "Morizon",
                    })
        except Exception:
            continue

    if results:
        return results

    # Fallback: extract links from HTML
    # Morizon listing URLs: /mieszkanie/warszawa/...
    links = re.findall(
        r'href="(https://www\.morizon\.pl/mieszkanie/[^"]+?)"',
        html
    )
    # Also try relative links
    rel_links = re.findall(r'href="(/mieszkanie/[^"]+?)"', html)
    for l in rel_links:
        links.append(f"https://www.morizon.pl{l}")

    seen = set()
    clean_links = []
    for l in links:
        if "?" in l or "#" in l:
            continue
        if l not in seen and len(l) > 40:
            seen.add(l)
            clean_links.append(l)

    titles = re.findall(
        r'(?:class="[^"]*(?:title|name|heading)[^"]*"[^>]*>|<h[23][^>]*>)\s*([^<]{10,120})',
        html
    )
    prices = re.findall(r'(\d[\d\s]{2,6})\s*(?:zł|PLN)', html)

    for i, link in enumerate(clean_links[:40]):
        title = titles[i].strip() if i < len(titles) else f"Mieszkanie Warszawa #{i+1}"
        price = _price(prices[i]) if i < len(prices) else 0

        # Rooms/area from URL
        rooms = None
        area = None
        m = re.search(r'(\d)-pokojowe', link, re.I)
        if m:
            rooms = int(m.group(1))
        m2 = re.search(r'(\d+)-m2', link)
        if m2:
            try:
                area = float(m2.group(1))
            except Exception:
                pass

        results.append({
            "title": title, "price": price, "district": "Warsaw",
            "rooms": rooms, "area": area, "floor": None,
            "furnished": 0, "link": link, "image": "", "source": "Morizon",
        })

    return results


def parse_morizon() -> list:
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
            print(f"[Morizon] Page {page}: {len(page_results)} listings")
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"[Morizon] Page {page} error: {e}")

    print(f"[Morizon] Found {len(results)} listings")
    return results
