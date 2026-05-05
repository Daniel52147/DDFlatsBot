"""
Lento.pl parser — Warsaw apartments for rent.
Uses retry + close connection to prevent hangs.
"""
import random
import re
import time
from parser._retry import make_session, fetch_with_retry

BASE_URL = "https://warszawa.lento.pl/nieruchomosci/mieszkania/do-wynajecia.html"


def _price(val) -> int:
    if not val:
        return 0
    cleaned = str(val).replace("\xa0", "").replace("\u00a0", "").replace(" ", "")
    try:
        return int(float(cleaned.replace(",", ".")))
    except Exception:
        digits = "".join(c for c in cleaned if c.isdigit())
        return int(digits) if digits else 0


def _parse_page(html: str) -> list:
    results = []
    # Split by card boundary
    cards = re.findall(
        r'<div[^>]*class="tablelist-tr[^"]*"[^>]*data-id="\d+".*?(?=<div[^>]*class="tablelist-tr|$)',
        html, re.DOTALL
    )
    for card in cards:
        try:
            # Title + link — try multiple patterns
            url, title = "", ""
            # Pattern 1: href before class
            m = re.search(
                r'href="(https://warszawa\.lento\.pl/[^"]+,\d+\.html)"[^>]*class="title-list-item"[^>]*>([^<]{5,150})<',
                card
            )
            if m:
                url, title = m.group(1), m.group(2).strip()
            else:
                # Pattern 2: class before href
                m = re.search(
                    r'class="title-list-item"[^>]*href="(https://warszawa\.lento\.pl/[^"]+,\d+\.html)"[^>]*>([^<]{5,150})<',
                    card
                )
                if m:
                    url, title = m.group(1), m.group(2).strip()
                else:
                    # Pattern 3: separate
                    tm = re.search(r'class="title-list-item"[^>]*>([^<]{5,150})<', card)
                    um = re.search(r'href="(https://warszawa\.lento\.pl/[^"]+,\d+\.html)"', card)
                    if tm and um:
                        title, url = tm.group(1).strip(), um.group(1)

            if not url or not title or len(title) < 5:
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

            # District
            district = "Warszawa"
            lm = re.search(r'class="[^"]*(?:licon-pin|mark-pointer)[^"]*"[^>]*>([^<]{3,60})<', card, re.I)
            if lm:
                district = lm.group(1).strip() or "Warszawa"

            # Area
            area = None
            am = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:&nbsp;)?m2', card, re.I)
            if am:
                try:
                    area = float(am.group(1).replace(",", "."))
                except Exception:
                    pass

            # Rooms
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

            # Image — src first, then data-src (lazy load)
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
                "title": title, "price": price, "district": district,
                "rooms": rooms, "area": area, "floor": None, "furnished": 0,
                "link": url, "image": image, "source": "Lento",
            })
        except Exception:
            continue
    return results


def parse_lento() -> list:
    results = []
    seen = set()

    def add(items):
        n = 0
        for apt in items:
            if apt["link"] not in seen:
                seen.add(apt["link"])
                results.append(apt)
                n += 1
        return n

    # close=True prevents keep-alive hangs on Lento
    session = make_session(referer="https://warszawa.lento.pl/", close=True)

    for page in range(1, 6):
        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        status, html = fetch_with_retry(session, url, max_retries=3, timeout=20, backoff_base=2.5)
        print(f"[Lento] page={page} status={status} size={len(html)}")
        if status != 200:
            break
        items = _parse_page(html)
        new = add(items)
        print(f"[Lento] page={page}: {new} new")
        if new == 0:
            break
        time.sleep(random.uniform(1.5, 2.5))

    print(f"[Lento] Total: {len(results)}")
    return results
