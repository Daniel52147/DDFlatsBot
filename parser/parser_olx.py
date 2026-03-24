"""
OLX parser — dual approach:
- Page 1: JSON-LD Product > AggregateOffer > offers[] (structured, 20 items)
- Page 2+: HTML card parsing via data-cy="l-card" + data-testid attributes
No WAF bypass needed — standard HTML requests work fine.
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


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.olx.pl/",
        "Connection": "keep-alive",
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
    if rm:
        try:
            return int(rm.group(1))
        except Exception:
            pass
    return None


def _area_from_title(title: str):
    am = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', title, re.I)
    if am:
        try:
            return float(am.group(1).replace(',', '.'))
        except Exception:
            pass
    return None


def _parse_json_ld(html: str) -> list:
    """Extract listings from JSON-LD on page 1 (Product > AggregateOffer > offers[])."""
    results = []
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    for script in scripts:
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
                    url  = item.get('url') or ''
                    if not name or len(name) < 5 or not url or 'olx.pl' not in url:
                        continue
                    # Strip query params from URL
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
            break  # Found the right script
        except Exception:
            continue
    return results


def _parse_html_cards(html: str) -> list:
    """Parse listing cards from HTML (pages 2+) using data-testid attributes."""
    results = []

    # Extract parallel arrays: links, prices, locations
    # Links: /d/oferta/... (deduplicated — each card has 2 identical links)
    raw_links = re.findall(r'href="(/d/oferta/[^"?]+)', html)
    # Deduplicate while preserving order
    seen_links = []
    seen_set = set()
    for l in raw_links:
        if l not in seen_set:
            seen_set.add(l)
            seen_links.append(l)

    # Prices: data-testid="ad-price"
    raw_prices = re.findall(
        r'data-testid="ad-price"[^>]*>([\d\s\xa0]+)\s*zł',
        html, re.I
    )

    # Locations: data-testid="location-date"
    raw_locs = re.findall(
        r'data-testid="location-date"[^>]*>(.*?)</p>',
        html, re.DOTALL
    )

    # Images: olxcdn.com images near l-cards
    # Split by l-card to get per-card images
    card_sections = re.split(r'data-cy="l-card"', html)

    # Build results by matching links with prices and locations
    # OLX page structure: each card has 1 unique link, 1 price, 1 location
    n = min(len(seen_links), len(raw_prices), len(raw_locs))

    for i in range(n):
        try:
            url = f"https://www.olx.pl{seen_links[i]}"
            price = _price(raw_prices[i])

            # Parse location: "Warszawa, Mokotów - 18 marca 2026"
            loc_raw = re.sub(r'<[^>]+>', '', raw_locs[i]).strip()
            district = 'Warszawa'
            loc_m = re.match(r'Warszawa,?\s*([^-–\d]+)', loc_raw)
            if loc_m:
                district = loc_m.group(1).strip().rstrip(',').strip()

            # Title from URL slug
            slug = seen_links[i].split('/')[-1]
            # Remove ID suffix like -CID3-ID19NpGn.html
            slug = re.sub(r'-CID\d+-ID\w+\.html$', '', slug)
            slug = re.sub(r'\.html$', '', slug)
            title = slug.replace('-', ' ').title()

            # Image from corresponding card section
            image = ''
            if i + 1 < len(card_sections):
                img_m = re.search(
                    r'src="(https://ireland\.apollo\.olxcdn\.com[^"]+)"',
                    card_sections[i + 1][:1000]
                )
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
    """Try JSON-LD first, fall back to HTML card parsing."""
    results = _parse_json_ld(html)
    if not results:
        results = _parse_html_cards(html)
    return results


def parse_olx() -> list:
    results = []
    seen    = set()
    session = _session()

    def add(items):
        n = 0
        for apt in items:
            if apt['link'] not in seen:
                seen.add(apt['link'])
                results.append(apt)
                n += 1
        return n

    # Sort by newest — 5 pages
    for page in range(1, 6):
        url = SORT_NEW if page == 1 else f"{SORT_NEW}&page={page}"
        try:
            r = session.get(url, timeout=25)
            print(f"[OLX-new] page={page} status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                break
            items = _parse_page(r.text)
            new = add(items)
            print(f"[OLX-new] page={page}: {new} new ({len(items)} parsed)")
            if new == 0 and page >= 2:
                break
            time.sleep(random.uniform(2.0, 3.5))
        except Exception as e:
            print(f"[OLX-new] page={page} error: {e}")
            break

    # Sort by price ascending — 3 pages
    for page in range(1, 4):
        url = SORT_PRICE if page == 1 else f"{SORT_PRICE}&page={page}"
        try:
            r = session.get(url, timeout=25)
            print(f"[OLX-price] page={page} status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                break
            items = _parse_page(r.text)
            new = add(items)
            print(f"[OLX-price] page={page}: {new} new ({len(items)} parsed)")
            if new == 0:
                break
            time.sleep(random.uniform(2.0, 3.5))
        except Exception as e:
            print(f"[OLX-price] page={page} error: {e}")
            break

    print(f"[OLX] Total: {len(results)} listings")
    return results
