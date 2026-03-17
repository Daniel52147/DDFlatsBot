import random
import re
import json
import time
import requests
from config import USER_AGENTS

API_URL = "https://www.olx.pl/api/v1/offers/"
MAX_BYTES = 512 * 1024  # 512KB


def _h(json_mode=True):
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.olx.pl/",
        "Accept-Language": "pl-PL,pl;q=0.9",
    }
    if json_mode:
        h["Accept"] = "application/json"
    else:
        h["Accept"] = "text/html,application/xhtml+xml"
    return h


def _price(params: list) -> int:
    for p in params:
        if p.get("key") == "price":
            try:
                return int(str(p["value"]["value"]).replace(" ", "").replace("\xa0", ""))
            except Exception:
                pass
    return 0


def _param(params: list, key: str):
    for p in params:
        if p.get("key") == key:
            v = p.get("value", {})
            return (v.get("label") or v.get("key")) if isinstance(v, dict) else v
    return None


def _fetch_json(url, params=None, headers=None, timeout=12) -> dict:
    r = requests.get(url, params=params, headers=headers, timeout=timeout, stream=True)
    r.raise_for_status()
    content = b""
    for chunk in r.iter_content(chunk_size=65536):
        content += chunk
        if len(content) >= MAX_BYTES:
            break
    r.close()
    return json.loads(content.decode("utf-8", errors="ignore"))


# Keywords that indicate non-apartment listings to skip
_JUNK_KEYWORDS = [
    "osuszacz", "klimatyzator", "agregat", "laweta", "przyczepa",
    "rower", "samochód", "auto ", "skuter", "motor", "kamera",
    "telewizor", "lodówka", "pralka", "zmywarka", "meble",
    "garaż", "parking", "miejsce postojowe", "komórka lokatorska",
    "działka", "dom na sprzedaż", "lokal użytkowy", "biuro",
    "magazyn", "hala", "grunt", "sprzedam", "na sprzedaż",
    "na doby", "na godziny", "noclegi", "na tydzień",
    "krótkoterminow", "dobowy", "/doby", "godz/", "osuszanie",
]

def _is_apartment(title: str, category: dict) -> bool:
    """Return False if this looks like a non-apartment listing."""
    title_lower = title.lower()
    for kw in _JUNK_KEYWORDS:
        if kw in title_lower:
            return False
    # Check OLX category
    if category:
        cat_id = category.get("id")
        # Block only if clearly wrong category AND no apartment words in title
        if cat_id and cat_id not in (15, 1, 3018, 3019, 3020):
            apt_words = ["mieszkanie", "kawalerka", "pokój", "apartament", "wynajem", "do wynajęcia"]
            if not any(w in title_lower for w in apt_words):
                return False
    return True


def _parse_offer(o: dict) -> dict | None:
    try:
        p = o.get("params", [])
        title = o.get("title", "").strip()
        link = o.get("url", "")
        if not title or not link:
            return None

        # Filter out non-apartment listings
        category = o.get("category", {})
        if not _is_apartment(title, category):
            return None

        price = _price(p)
        loc = o.get("location", {})
        district = (
            (loc.get("district") or {}).get("name") or
            (loc.get("city") or {}).get("name") or "Warsaw"
        )
        photos = o.get("photos", [])
        image = ""
        if photos:
            image = photos[0].get("link", "").replace("{width}", "400").replace("{height}", "300")
        rooms_raw = _param(p, "rooms")
        area_raw = _param(p, "m")
        rooms = None
        area = None
        if rooms_raw:
            try:
                rooms = int(str(rooms_raw).replace("+", "").strip())
            except Exception:
                pass
        if area_raw:
            try:
                area = float(str(area_raw).replace(",", ".").strip())
            except Exception:
                pass
        return {
            "title": title, "price": price, "district": district,
            "rooms": rooms, "area": area, "floor": None,
            "furnished": 0, "link": link, "image": image, "source": "OLX",
        }
    except Exception:
        return None


def parse_olx() -> list:
    results = []

    # Fetch multiple pages from API using query search (most reliable for Warsaw)
    for offset in [0, 50, 100, 150, 200, 250, 300, 350, 400, 450]:
        params = {
            "offset": offset,
            "limit": 50,
            "query": "mieszkanie wynajem warszawa",
            "sort_by": "created_at:desc",
        }
        try:
            data = _fetch_json(API_URL, params=params, headers=_h(json_mode=True))
            offers = data.get("data", [])
            if not offers:
                break
            for o in offers:
                apt = _parse_offer(o)
                if apt:
                    results.append(apt)
            print(f"[OLX] offset={offset}: {len(offers)} offers")
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"[OLX] API error at offset={offset}: {e}")
            break

    # Also fetch by category (mieszkania/wynajem) for more coverage
    for offset in [0, 50, 100, 150, 200]:
        params = {
            "offset": offset,
            "limit": 50,
            "category_id": 15,
            "region_id": 7,  # Mazowieckie
            "city_id": 39610,  # Warszawa
            "sort_by": "created_at:desc",
        }
        try:
            data = _fetch_json(API_URL, params=params, headers=_h(json_mode=True))
            offers = data.get("data", [])
            if not offers:
                break
            for o in offers:
                apt = _parse_offer(o)
                if apt:
                    results.append(apt)
            print(f"[OLX] category offset={offset}: {len(offers)} offers")
            time.sleep(random.uniform(1, 2))
        except Exception as e:
            print(f"[OLX] category API error at offset={offset}: {e}")
            break

    # HTML fallback if API returned nothing
    if not results:
        try:
            r = requests.get(
                "https://www.olx.pl/nieruchomosci/mieszkania/wynajem/warszawa/",
                headers=_h(json_mode=False), timeout=15, stream=True
            )
            content = b""
            for chunk in r.iter_content(65536):
                content += chunk
                if len(content) >= MAX_BYTES:
                    break
            r.close()
            text = content.decode("utf-8", errors="ignore")

            # Try embedded JSON
            m = re.search(r'"offers"\s*:\s*(\[.*?\])\s*,\s*"[a-z]', text, re.DOTALL)
            if m:
                try:
                    offers = json.loads(m.group(1))
                    for o in offers[:50]:
                        apt = _parse_offer(o)
                        if apt:
                            results.append(apt)
                except Exception:
                    pass

            # BeautifulSoup fallback
            if not results:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(text, "lxml")
                    cards = soup.find_all("div", attrs={"data-cy": "l-card"})
                    for card in cards[:50]:
                        a = card.find("a", href=True)
                        if not a:
                            continue
                        href = a["href"]
                        if not href.startswith("http"):
                            href = "https://www.olx.pl" + href
                        title_el = card.find("h6") or card.find("h4") or card.find("h3")
                        title = title_el.get_text(strip=True) if title_el else ""
                        if not title:
                            continue
                        price_el = card.find(attrs={"data-testid": "ad-price"})
                        price = _price([]) if not price_el else int(
                            "".join(c for c in price_el.get_text() if c.isdigit()) or "0"
                        )
                        results.append({
                            "title": title, "price": price, "district": "Warsaw",
                            "rooms": None, "area": None, "floor": None,
                            "furnished": 0, "link": href, "image": "", "source": "OLX",
                        })
                except Exception as e:
                    print(f"[OLX] BS4 error: {e}")

            # Last resort: regex
            if not results:
                links = re.findall(r'"url"\s*:\s*"(https://www\.olx\.pl/d/oferta/[^"]+)"', text)
                titles = re.findall(r'"title"\s*:\s*"([^"]{10,100})"', text)
                seen = set()
                for i, link in enumerate(links[:50]):
                    if link in seen:
                        continue
                    seen.add(link)
                    title = titles[i] if i < len(titles) else f"Mieszkanie #{i+1}"
                    results.append({
                        "title": title, "price": 0, "district": "Warsaw",
                        "rooms": None, "area": None, "floor": None,
                        "furnished": 0, "link": link, "image": "", "source": "OLX",
                    })
        except Exception as e:
            print(f"[OLX] HTML fallback error: {e}")

    print(f"[OLX] Found {len(results)} listings")
    return results
