"""
Aviasales partner API — affiliate links with commission.
Docs: https://www.aviasales.ru/api

Without API key: builds standard search URLs with partner marker.
With API key: uses Data API for real prices.
"""
from config import AVIASALES_TOKEN, AVIASALES_MARKER

AVIASALES_BASE = "https://api.travelpayouts.com/v1"


def build_search_url(origin: str, destination: str, date: str = "", marker: str = "") -> str:
    """
    Build Aviasales affiliate search URL.
    date format: YYYY-MM-DD
    """
    m = marker or AVIASALES_MARKER or ""
    base = f"https://www.aviasales.ru/search/{origin}{date.replace('-', '')}{destination}1"
    if m:
        base += f"?marker={m}"
    return base


def get_cheap_tickets(origin: str, destination: str, currency: str = "EUR") -> list:
    """
    Get cheapest tickets via Aviasales Data API.
    Returns list of flight dicts.
    """
    if not AVIASALES_TOKEN:
        return []

    import requests
    params = {
        "origin": origin,
        "destination": destination,
        "currency": currency,
        "token": AVIASALES_TOKEN,
        "limit": 10,
        "one_way": True,
    }
    try:
        r = requests.get(f"{AVIASALES_BASE}/prices/cheap", params=params, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", {})
        results = []
        for dest, months in data.items():
            for month, info in months.items():
                if not isinstance(info, dict):
                    continue
                price = info.get("price", 0)
                depart = info.get("departure_at", "")
                airline = info.get("airline", "")
                link = build_search_url(origin, destination, depart[:10])
                results.append({
                    "origin": origin,
                    "destination": destination,
                    "origin_city": origin,
                    "dest_city": destination,
                    "price": price,
                    "currency": currency,
                    "airline": airline,
                    "depart_at": depart[:10],
                    "arrive_at": "",
                    "duration": "",
                    "stops": "",
                    "link": link,
                })
        return sorted(results, key=lambda x: x["price"])[:10]
    except Exception as e:
        print(f"[Aviasales] Error: {e}")
        return []
