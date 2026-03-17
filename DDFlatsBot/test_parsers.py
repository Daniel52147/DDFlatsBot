import requests
import re
import json

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
H = {"User-Agent": UA, "Accept-Language": "pl-PL,pl;q=0.9", "Accept": "application/json"}

print("=== OLX API test ===")
# Try different API endpoints
urls = [
    "https://www.olx.pl/api/v1/offers/?offset=0&limit=10&category_id=15&region_id=7&city_id=39610&sort_by=created_at:desc",
    "https://www.olx.pl/api/v1/offers/?offset=0&limit=10&category_id=15&city_id=39610",
]
for url in urls:
    try:
        r = requests.get(url, headers=H, timeout=10)
        d = r.json()
        items = d.get("data", [])
        print(f"URL: {url[-60:]}")
        print(f"  Status: {r.status_code}, Items: {len(items)}, Total: {d.get('metadata',{}).get('total_elements')}")
        if items:
            print(f"  First: {items[0].get('title','?')} | {items[0].get('url','?')[:60]}")
            break
    except Exception as e:
        print(f"  Error: {e}")

print("\n=== Otodom test ===")
try:
    r = requests.get(
        "https://www.otodom.pl/pl/oferty/wynajem/mieszkanie/warszawa",
        headers={**H, "Accept": "text/html"}, timeout=10
    )
    print(f"Status: {r.status_code}, Size: {len(r.text)}")
    # Quick regex search for slugs
    slugs = re.findall(r'"slug":"([a-z0-9\-]+ID\d+)"', r.text)
    titles = re.findall(r'"title":"([^"]{10,60})"', r.text)
    prices = re.findall(r'"value":(\d{3,6}),"currency":"PLN"', r.text)
    print(f"  Slugs: {len(slugs)}, Titles: {len(titles)}, Prices: {len(prices)}")
    if slugs:
        print(f"  First slug: {slugs[0]}")
    if titles:
        print(f"  First title: {titles[0]}")
except Exception as e:
    print(f"Error: {e}")

print("\n=== Gratka test ===")
try:
    r = requests.get(
        "https://gratka.pl/nieruchomosci/mieszkania/warszawa/wynajem",
        headers={**H, "Accept": "text/html"}, timeout=10
    )
    print(f"Status: {r.status_code}, Size: {len(r.text)}")
    links = re.findall(r'href="(https://gratka\.pl/nieruchomosci/[^"]+)"', r.text)
    print(f"  Links: {len(links)}, first: {links[0] if links else 'none'}")
except Exception as e:
    print(f"Error: {e}")
