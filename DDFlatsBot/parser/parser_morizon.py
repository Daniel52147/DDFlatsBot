import random
import re
import json
import time
import requests

from config import USER_AGENTS

BASE = "https://www.morizon.pl/do-wynajecia/mieszkania/warszawa/"


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    return s


def _fetch(url: str, session) -> str:
    # Don't use stream=True — prevents automatic Brotli/gzip decompression
    r = session.get(url, timeout=25)
    r.raise_for_status()
    return r.text


def _price(val) -> int:
    if not val:
        return 0
    # Handle float strings like "2900.00" — convert to float first, then int
    try:
        return int(float(str(val).replace(",", ".")))
    except Exception:
        digits = "".join(c for c in str(val) if c.isdigit())
        return int(digits) if digits else 0


def _parse_listings_html(html: str) -> list:
    """Parse individual apartment cards from Morizon listing page HTML."""
    results = []

    # Morizon uses <article> or <li> with class containing "listing" or "property"
    articles = re.findall(
        r'<(?:article|li)[^>]+class="[^"]*(?:listing|property|offer)[^"]*"[^>]*>(.*?)</(?:article|li)>',
        html, re.DOTALL | re.IGNORECASE
    )

    if not articles:
        articles = re.findall(
            r'<article[^>]*>(.*?)</article>',
            html, re.DOTALL | re.IGNORECASE
        )

    for article in articles:
        try:
            # Extract URL — Morizon links look like /oferta/mieszkanie-...
            url_match = re.search(
                r'href="(https://www\.morizon\.pl/oferta/[^"]+)"',
                article
            )
            if not url_match:
                url_match = re.search(r'href="(/oferta/[^"]+)"', article)
                if url_match:
                    url_match = type('m', (), {'group': lambda self, n: "https://www.morizon.pl" + url_match.group(1)})()
            if not url_match:
                continue
            url = url_match.group(1) if hasattr(url_match, 'group') else url_match

            # Extract title
            title_match = re.search(
                r'<(?:h2|h3|a)[^>]*class="[^"]*(?:title|name|heading)[^"]*"[^>]*>([^<]{5,120})<',
                article, re.IGNORECASE
            )
            if not title_match:
                title_match = re.search(r'title="([^"]{10,120})"', article)
            if not title_match:
                # Try alt text of image
                title_match = re.search(r'alt="([^"]{10,120})"', article)
            if not title_match:
                continue
            title = title_match.group(1).strip()

            # Extract price
            price = 0
            price_match = re.search(
                r'(\d[\d\s]{2,6})\s*(?:zł|PLN)',
                article, re.IGNORECASE
            )
            if price_match:
                price = _price(price_match.group(1))

            # Extract district/location
            district = "Warszawa"
            loc_match = re.search(
                r'<[^>]*class="[^"]*(?:location|address|city)[^"]*"[^>]*>([^<]{3,60})<',
                article, re.IGNORECASE
            )
            if loc_match:
                district = loc_match.group(1).strip()

            # Extract image
            image = ""
            img_match = re.search(
                r'<img[^>]+src="(https://[^"]+(?:jpg|jpeg|png|webp)[^"]*)"',
                article, re.IGNORECASE
            )
            if img_match:
                image = img_match.group(1)

            # Extract rooms from title
            rooms = None
            rm = re.search(r'(\d)\s*-?\s*(?:pok|pokój|pokoje|pokoi)', title, re.I)
            if rm:
                rooms = int(rm.group(1))

            # Extract area from title
            area = None
            am = re.search(r'(\d+(?:[.,]\d+)?)\s*m[²2]', title)
            if am:
                try:
                    area = float(am.group(1).replace(",", "."))
                except Exception:
                    pass

            results.append({
                "title": title,
                "price": price,
                "district": district,
                "rooms": rooms,
                "area": area,
                "floor": None,
                "furnished": 0,
                "link": url if isinstance(url, str) else url.group(1),
                "image": image,
                "source": "Morizon",
            })
        except Exception:
            continue

    return results


def _parse_json_ld_offers(html: str) -> list:
    """Parse individual Offer items from JSON-LD."""
    results = []
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)

    for block in blocks:
        try:
            data = json.loads(block)
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        if data.get("@type") == "ItemList":
            for element in data.get("itemListElement", []):
                item = element.get("item", element) if isinstance(element, dict) else {}
                name = item.get("name", "").strip()
                url = item.get("url", "")
                if not name or not url or len(name) < 10:
                    continue
                price_spec = item.get("offers", {})
                price = _price(price_spec.get("price", 0) if isinstance(price_spec, dict) else 0)
                results.append({
                    "title": name, "price": price, "district": "Warszawa",
                    "rooms": None, "area": None, "floor": None, "furnished": 0,
                    "link": url, "image": "", "source": "Morizon",
                })

        # Main pattern: Product > offers (AggregateOffer) > offers (list of Offer)
        top_offers = data.get("offers", {})
        if isinstance(top_offers, dict):
            inner = top_offers.get("offers", [])
            if isinstance(inner, list):
                for offer in inner:
                    if not isinstance(offer, dict):
                        continue
                    name = offer.get("name", "").strip()
                    url = offer.get("url", "")
                    if not name or not url or len(name) < 10:
                        continue
                    price = _price(offer.get("price", 0))
                    image = offer.get("image", "")
                    if isinstance(image, list):
                        image = image[0] if image else ""

                    # Extract district from itemOffered
                    district = "Warszawa"
                    item_offered = offer.get("itemOffered", {})
                    if isinstance(item_offered, dict):
                        addr = item_offered.get("address", {})
                        if isinstance(addr, dict):
                            locality = addr.get("addressLocality", "")
                            street = addr.get("streetAddress", "")
                            if locality and locality != "Warszawa":
                                district = locality
                            elif street:
                                district = f"Warszawa, {street[:25]}"

                    # Rooms and area from name
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

    return results


def _parse_inline_json(html: str) -> list:
    """Try to extract listings from inline JS data."""
    results = []
    patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>',
        r'"listings"\s*:\s*(\[.*?\])\s*[,}]',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, list):
                    for item in data[:30]:
                        if isinstance(item, dict) and item.get("url"):
                            results.append({
                                "title": item.get("name", item.get("title", "Mieszkanie"))[:120],
                                "price": _price(item.get("price", 0)),
                                "district": "Warszawa",
                                "rooms": None, "area": None, "floor": None, "furnished": 0,
                                "link": item["url"], "image": "", "source": "Morizon",
                            })
            except Exception:
                continue
    return results


def parse_morizon() -> list:
    results = []
    session = _session()

    for page in range(1, 11):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        try:
            html = _fetch(url, session)

            # Method 1: JSON-LD individual offers (most reliable for Morizon)
            page_results = _parse_json_ld_offers(html)
            if page_results:
                results.extend(page_results)
                print(f"[Morizon] Page {page} JSON-LD: {len(page_results)}")
                time.sleep(random.uniform(1.5, 3))
                continue

            # Method 2: Parse HTML article cards
            page_results = _parse_listings_html(html)
            if page_results:
                results.extend(page_results)
                print(f"[Morizon] Page {page} HTML: {len(page_results)}")
                time.sleep(random.uniform(1.5, 3))
                continue

            # Method 3: Inline JS data
            page_results = _parse_inline_json(html)
            if page_results:
                results.extend(page_results)
                print(f"[Morizon] Page {page} inline JS: {len(page_results)}")
            else:
                print(f"[Morizon] Page {page}: 0 results")

            time.sleep(random.uniform(1.5, 3))
        except Exception as e:
            print(f"[Morizon] Page {page} error: {e}")

    print(f"[Morizon] Total: {len(results)}")
    return results
