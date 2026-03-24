"""
Lento.pl parser — Warsaw apartments for rent.
URL: https://warszawa.lento.pl/nieruchomosci/mieszkania/do-wynajecia.html
Cards use class="tablelist-tr", title in <a class="title-list-item">,
price in <span class="price-list-item">, image in <img src="...">.
"""
import random
import re
import time
import requests
from config import USER_AGENTS

BASE_URL = "https://warszawa.lento.pl/nieruchomosci/mieszkania/do-wynajecia.html"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://warszawa.lento.pl/",
        "Connection": "keep-alive",
    })
    return s


def _price(val) -> int:
    if not val:
        return 0
    cleaned = str(val).replace("\xa0", "").replace(" ", "").replace("\u00a0", "")
    try:
        return int(float(cleaned.replace(",", ".")))
    except Exception:
        digits = "".join(c for c in cleaned if c.isdigit())
        return int(digits) if digits else 0


def _parse_page(html: str) -> list:
    results = []

    # Each listing card: <div class="tablelist-tr ..." data-id="NNNN">
    # Split by tablelist-tr to get individual cards
    cards = re.findall(
        r'<div[^>]*class="tablelist-tr[^"]*"[^>]*data-id="\d+".*?(?=<div[^>]*class="tablelist-tr|$)',
        html, re.DOTALL
    )

    for card in cards:
        try:
            # Title + link
            link_m = re.search(
                r'href="(https://warszawa\.lento\.pl/[^"]+,\d+\.html)"[^>]*class="title-list-item"[^>]*>([^<]{5,150})<',
                card
            )
            if not link_m:
                link_m = re.search(
                    r'class="title-list-item"[^>]*href="(https://warszawa\.lento\.pl/[^"]+,\d+\.html)"[^>]*>([^<]{5,150})<',
                    card
                )
            if not link_m:
                # Try any title-list-item
                title_m2 = re.search(r'class="title-list-item"[^>]*>([^<]{5,150})<', card)
                url_m2 = re.search(r'href="(https://warszawa\.lento\.pl/[^"]+,\d+\.html)"', card)
                if not title_m2 or not url_m2:
                    continue
                title = title_m2.group(1).strip()
                url = url_m2.group(1)
            else:
                url = link_m.group(1)
                title = link_m.group(2).strip()

            if len(title) < 5:
                continue

            # Price
            price = 0
            pm = re.search(r'class="price-list-item"[^>]*>([\d\s\xa0\u00a0,\.]+)\s*zł', card, re.I)
            if pm:
                price = _price(pm.group(1))
            if not price:
                pm2 = re.search(r'([\d][\d\s\xa0]{2,8})\s*zł', card, re.I)
                if pm2:
                    price = _price(pm2.group(1))

            # District / location
            district = "Warszawa"
            loc_m = re.search(r'class="[^"]*(?:licon-pin|mark-pointer)[^"]*"[^>]*>([^<]{3,60})<', card, re.I)
            if loc_m:
                district = loc_m.group(1).strip() or "Warszawa"

            # Area
            area = None
            am = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:&nbsp;)?m2', card, re.I)
            if am:
                try:
                    area = float(am.group(1).replace(",", "."))
                except Exception:
                    pass

            # Rooms — from param block "2 pokoje" or title
            rooms = None
            rm = re.search(r'(\d)\s*pokoje?|(\d)\s*pok\.', card, re.I)
            if rm:
                try:
                    rooms = int(rm.group(1) or rm.group(2))
                except Exception:
                    pass
            if not rooms:
                rm2 = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
                if rm2:
                    try:
                        rooms = int(rm2.group(1))
                    except Exception:
                        pass

            # Image — try regular src first, then data-src (lazy)
            img_m = re.search(
                r'<img[^>]+src="(https://st-lento\.pl/adpics/[^"]+\.(?:jpg|jpeg|png)[^"]*)"',
                card, re.I
            )
            if not img_m:
                img_m = re.search(
                    r'data-src="(https://st-lento\.pl/adpics/[^"]+\.(?:jpg|jpeg|png)[^"]*)"',
                    card, re.I
                )
            image = img_m.group(1) if img_m else ""

            results.append({
                "title": title,
                "price": price,
                "district": district,
                "rooms": rooms,
                "area": area,
                "floor": None,
                "furnished": 0,
                "link": url,
                "image": image,
                "source": "Lento",
            })
        except Exception:
            continue

    return results


def parse_lento() -> list:
    results = []
    seen = set()
    session = _session()

    def add(items):
        n = 0
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)
                n += 1
        return n

    for page in range(1, 6):
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        try:
            r = session.get(url, timeout=25)
            print(f"[Lento] page={page} status={r.status_code} size={len(r.text)}")
            if r.status_code != 200:
                break
            items = _parse_page(r.text)
            new = add(items)
            print(f"[Lento] page={page}: {new} new listings")
            if new == 0:
                break
            time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Lento] page={page} error: {e}")
            break

    print(f"[Lento] Total: {len(results)} listings")
    return results
