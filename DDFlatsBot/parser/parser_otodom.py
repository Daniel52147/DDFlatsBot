"""
Otodom parser — uses their internal Elasticsearch API.
No HTML scraping, no Cloudflare issues.
"""
import random
import time
import requests
from config import USER_AGENTS


def _session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "pl-PL,pl;q=0.9",
        "Origin": "https://www.otodom.pl",
        "Referer": "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa",
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


def _parse_item(item: dict) -> dict | None:
    try:
        title = (item.get("title") or "").strip()
        if not title or len(title) < 5:
            return None

        slug = item.get("slug") or item.get("id") or ""
        if not slug:
            return None
        link = f"https://www.otodom.pl/pl/oferta/{slug}"

        price = 0
        for pf in ("totalPrice", "rentPrice", "price"):
            pobj = item.get(pf)
            if pobj:
                price = _price(pobj.get("value") if isinstance(pobj, dict) else pobj)
                if price:
                    break

        loc = item.get("location") or {}
        addr = loc.get("address") or {} if isinstance(loc, dict) else {}
        district = (
            (addr.get("district") or {}).get("name") or
            (addr.get("city") or {}).get("name") or
            "Warszawa"
        )
        if isinstance(district, dict):
            district = district.get("name", "Warszawa")

        images = item.get("images") or []
        image = ""
        if images and isinstance(images[0], dict):
            image = images[0].get("medium") or images[0].get("small") or ""

        rooms = None
        try:
            r = item.get("roomsNumber") or item.get("rooms")
            if r:
                rooms = int(str(r).replace("+", ""))
        except Exception:
            pass

        area = None
        try:
            a = item.get("areaInSquareMeters") or item.get("area")
            if a:
                area = float(a)
        except Exception:
            pass

        return {
            "title": title, "price": price, "district": str(district),
            "rooms": rooms, "area": area, "floor": None, "furnished": 0,
            "link": link, "image": image, "source": "Otodom",
        }
    except Exception:
        return None


def parse_otodom() -> list:
    """
    Uses Otodom's internal GraphQL-like API endpoint.
    Warsaw city_id = 26, region_id = 7 (Mazowieckie).
    """
    results = []
    seen = set()
    session = _session()

    # Try the internal API first
    for page in range(1, 6):
        try:
            url = (
                "https://www.otodom.pl/api/offers/"
                f"?limit=36&page={page}"
                "&category=mieszkania&offerType=wynajem"
                "&locations[0][regionId]=7&locations[0][cityId]=26"
            )
            r = session.get(url, timeout=20)
            print(f"[Otodom] API page {page} status: {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                items = (
                    data.get("items") or
                    data.get("data", {}).get("searchAds", {}).get("items") or
                    []
                )
                if not items:
                    print(f"[Otodom] API page {page}: empty response keys: {list(data.keys())}")
                    break
                for item in items:
                    apt = _parse_item(item)
                    if apt and apt["link"] not in seen:
                        seen.add(apt["link"])
                        results.append(apt)
                print(f"[Otodom] API page {page}: {len(items)} items")
                time.sleep(random.uniform(1, 2))
            else:
                print(f"[Otodom] API blocked ({r.status_code}), trying GraphQL...")
                break
        except Exception as e:
            print(f"[Otodom] API error page {page}: {e}")
            break

    # Fallback: GraphQL API
    if not results:
        try:
            gql_url = "https://www.otodom.pl/api/graphql"
            query = """
            query GetListings($page: Int) {
              searchAds(filters: {
                category: {id: 101},
                offerType: RENT,
                location: {cities: [{id: 26}]}
              }, pagination: {page: $page, limit: 36}) {
                items {
                  id slug title
                  totalPrice { value }
                  location { address { city { name } district { name } } }
                  images { medium }
                  roomsNumber areaInSquareMeters
                }
              }
            }
            """
            for page in range(1, 4):
                r = session.post(gql_url, json={"query": query, "variables": {"page": page}}, timeout=20)
                print(f"[Otodom] GraphQL page {page} status: {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    items = (data.get("data") or {}).get("searchAds", {}).get("items") or []
                    for item in items:
                        apt = _parse_item(item)
                        if apt and apt["link"] not in seen:
                            seen.add(apt["link"])
                            results.append(apt)
                    print(f"[Otodom] GraphQL page {page}: {len(items)} items")
                time.sleep(random.uniform(1.5, 2.5))
        except Exception as e:
            print(f"[Otodom] GraphQL error: {e}")

    print(f"[Otodom] Found {len(results)} listings")
    return results
