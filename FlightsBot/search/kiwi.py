"""
Kiwi.com Tequila API — free flight search.
Docs: https://tequila.kiwi.com/portal/docs/tequila-api/search_api

Register free at https://tequila.kiwi.com/ to get API key.
"""
import requests
from datetime import datetime, timedelta
from config import KIWI_API_KEY

TEQUILA_BASE = "https://api.tequila.kiwi.com/v2"


def _headers():
    return {"apikey": KIWI_API_KEY, "Content-Type": "application/json"}


def search_flights(
    origin: str,
    destination: str,
    date_from: str = None,       # "dd/mm/yyyy"
    date_to: str = None,         # "dd/mm/yyyy"
    nights_min: int = 2,
    nights_max: int = 14,
    price_max: int = None,
    adults: int = 1,
    limit: int = 10,
    sort: str = "price",         # price | duration | quality
) -> list:
    """
    Search one-way or return flights.
    Returns list of flight dicts.
    """
    if not KIWI_API_KEY:
        print("[Kiwi] No API key — returning mock data")
        return _mock_results(origin, destination)

    # Default: next 3 months
    if not date_from:
        date_from = datetime.now().strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=90)).strftime("%d/%m/%Y")

    params = {
        "fly_from": origin,
        "fly_to": destination,
        "date_from": date_from,
        "date_to": date_to,
        "nights_in_dst_from": nights_min,
        "nights_in_dst_to": nights_max,
        "adults": adults,
        "limit": limit,
        "sort": sort,
        "curr": "EUR",
        "locale": "ru",
        "partner": "picky",
    }
    if price_max:
        params["price_to"] = price_max

    try:
        r = requests.get(f"{TEQUILA_BASE}/search", headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return [_parse_flight(f) for f in data.get("data", [])]
    except Exception as e:
        print(f"[Kiwi] Search error: {e}")
        return []


def search_one_way(
    origin: str,
    destination: str,
    date_from: str = None,
    date_to: str = None,
    price_max: int = None,
    limit: int = 10,
) -> list:
    """Search one-way flights only."""
    if not KIWI_API_KEY:
        return []  # No mock for alerts — only real data matters

    if not date_from:
        date_from = datetime.now().strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=90)).strftime("%d/%m/%Y")

    params = {
        "fly_from": origin,
        "fly_to": destination,
        "date_from": date_from,
        "date_to": date_to,
        "flight_type": "oneway",
        "adults": 1,
        "limit": limit,
        "sort": "price",
        "curr": "EUR",
        "partner": "picky",
    }
    if price_max:
        params["price_to"] = price_max

    try:
        r = requests.get(f"{TEQUILA_BASE}/search", headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return [_parse_flight(f) for f in data.get("data", [])]
    except Exception as e:
        print(f"[Kiwi] One-way search error: {e}")
        return []


def get_hot_deals(origins: list, price_max: int = 100, limit: int = 20) -> list:
    """Find cheapest flights from given airports in next 30 days."""
    if not KIWI_API_KEY:
        return []

    origin_str = ",".join(origins)
    date_from = datetime.now().strftime("%d/%m/%Y")
    date_to = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")

    params = {
        "fly_from": origin_str,
        "fly_to": "anywhere",
        "date_from": date_from,
        "date_to": date_to,
        "price_to": price_max,
        "adults": 1,
        "limit": limit,
        "sort": "price",
        "curr": "EUR",
        "partner": "picky",
    }

    try:
        r = requests.get(f"{TEQUILA_BASE}/search", headers=_headers(), params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        return [_parse_flight(f) for f in data.get("data", [])]
    except Exception as e:
        print(f"[Kiwi] Hot deals error: {e}")
        return []


def get_cheapest_dates(origin: str, destination: str, months: int = 3) -> list:
    """Get cheapest dates for a route in next N months."""
    if not KIWI_API_KEY:
        return []

    date_from = datetime.now().strftime("%d/%m/%Y")
    date_to = (datetime.now() + timedelta(days=months * 30)).strftime("%d/%m/%Y")

    params = {
        "fly_from": origin,
        "fly_to": destination,
        "date_from": date_from,
        "date_to": date_to,
        "adults": 1,
        "limit": 5,
        "sort": "price",
        "curr": "EUR",
        "partner": "picky",
    }

    try:
        r = requests.get(f"{TEQUILA_BASE}/search", headers=_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return [_parse_flight(f) for f in data.get("data", [])]
    except Exception as e:
        print(f"[Kiwi] Cheapest dates error: {e}")
        return []


def _parse_flight(f: dict) -> dict:
    """Normalize Kiwi API flight object."""
    price = int(f.get("price", 0))

    # Departure / arrival
    depart_ts = f.get("dTime") or f.get("local_departure")
    arrive_ts = f.get("aTime") or f.get("local_arrival")

    def _fmt_time(ts):
        if not ts:
            return ""
        try:
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
            return str(ts)[:16].replace("T", " ")
        except Exception:
            return str(ts)

    depart_str = _fmt_time(depart_ts)
    arrive_str = _fmt_time(arrive_ts)

    # Airlines
    airlines = []
    for route in f.get("route", []):
        al = route.get("airline") or route.get("operating_carrier", "")
        if al and al not in airlines:
            airlines.append(al)
    airline = ", ".join(airlines) if airlines else f.get("airlines", ["?"])[0] if f.get("airlines") else "?"

    # Duration
    duration_min = f.get("duration", {}).get("total", 0) if isinstance(f.get("duration"), dict) else 0
    duration_str = f"{duration_min // 60}ч {duration_min % 60}м" if duration_min else ""

    # Stops
    stops = len(f.get("route", [])) - 1
    stops_str = "прямой" if stops <= 0 else f"{stops} пересадка" if stops == 1 else f"{stops} пересадки"

    # Booking link — Kiwi deep link
    link = f.get("deep_link") or f.get("booking_token", "")
    if not link.startswith("http"):
        token = f.get("booking_token", "")
        link = f"https://www.kiwi.com/booking?token={token}" if token else "https://www.kiwi.com"

    return {
        "origin":      f.get("flyFrom", ""),
        "destination": f.get("flyTo", ""),
        "origin_city": f.get("cityFrom", ""),
        "dest_city":   f.get("cityTo", ""),
        "price":       price,
        "currency":    "EUR",
        "airline":     airline,
        "depart_at":   depart_str,
        "arrive_at":   arrive_str,
        "duration":    duration_str,
        "stops":       stops_str,
        "link":        link,
    }


def _mock_results(origin: str, destination: str) -> list:
    """Mock data when no API key — for testing UI."""
    return [
        {
            "origin": origin, "destination": destination,
            "origin_city": "Warsaw", "dest_city": "Barcelona",
            "price": 29, "currency": "EUR",
            "airline": "Ryanair", "depart_at": "25.03 06:00", "arrive_at": "25.03 09:30",
            "duration": "3ч 30м", "stops": "прямой",
            "link": "https://www.kiwi.com",
        },
        {
            "origin": origin, "destination": destination,
            "origin_city": "Warsaw", "dest_city": "Barcelona",
            "price": 45, "currency": "EUR",
            "airline": "Wizz Air", "depart_at": "28.03 14:00", "arrive_at": "28.03 17:45",
            "duration": "3ч 45м", "stops": "прямой",
            "link": "https://www.kiwi.com",
        },
    ]
