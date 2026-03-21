"""
Flight search via fast-flights (Google Flights scraper).
No API key needed. Falls back to Amadeus if fast-flights fails.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

# ── fast-flights import (graceful fallback if not installed) ───────────────────
try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights as _gf
    FAST_FLIGHTS_OK = True
except ImportError:
    FAST_FLIGHTS_OK = False
    print("[Search] fast-flights not installed — using mock data")


# ── City name map for display ──────────────────────────────────────────────────
CITY_NAMES = {
    "WAW": "Варшава",   "KRK": "Краков",    "WRO": "Вроцлав",
    "GDN": "Гданьск",   "KTW": "Катовице",  "POZ": "Познань",
    "BCN": "Барселона", "MAD": "Мадрид",    "TFS": "Тенерифе",
    "PMI": "Майорка",   "AGP": "Малага",
    "FCO": "Рим",       "MXP": "Милан",     "NAP": "Неаполь",  "VCE": "Венеция",
    "LTN": "Лондон",    "LHR": "Лондон",    "STN": "Лондон",   "MAN": "Манчестер",
    "CDG": "Париж",     "ORY": "Париж",     "NCE": "Ницца",
    "DXB": "Дубай",     "AUH": "Абу-Даби",
    "AMS": "Амстердам", "LIS": "Лиссабон",  "ATH": "Афины",
    "PRG": "Прага",     "BUD": "Будапешт",  "VIE": "Вена",
    "BER": "Берлин",    "MUC": "Мюнхен",    "FRA": "Франкфурт", "HAM": "Гамбург",
    "BKK": "Бангкок",   "HKT": "Пхукет",    "CMB": "Коломбо",
    "JFK": "Нью-Йорк",  "LAX": "Лос-Анджелес", "MIA": "Майами",
    "IST": "Стамбул",   "SAW": "Стамбул",
    "TLV": "Тель-Авив", "CAI": "Каир",      "HRG": "Хургада",
}


def _fmt_dt(sdt) -> str:
    """Format SimpleDatetime → '25.03 14:30'"""
    try:
        y, m, d = sdt.date
        h, mi = sdt.time
        return f"{d:02d}.{m:02d} {h:02d}:{mi:02d}"
    except Exception:
        return ""


def _duration_str(minutes: int) -> str:
    if not minutes:
        return ""
    return f"{minutes // 60}ч {minutes % 60}м"


def _build_link(origin: str, dest: str, date: str) -> str:
    """Build Google Flights deep link."""
    # date format: YYYY-MM-DD
    return (
        f"https://www.google.com/travel/flights/search?"
        f"q=Flights+from+{origin}+to+{dest}+on+{date}"
    )


def _parse_result(result, origin: str, dest: str, date_str: str) -> list:
    """Convert fast-flights MetaList → our standard flight dicts."""
    flights = []
    for item in result:
        if not item.flights:
            continue
        first_leg = item.flights[0]
        last_leg = item.flights[-1]

        depart_str = _fmt_dt(first_leg.departure)
        arrive_str = _fmt_dt(last_leg.arrival)

        # Total duration
        total_min = sum(f.duration for f in item.flights)
        duration_str = _duration_str(total_min)

        # Airlines
        airline_names = []
        for code in item.airlines:
            airline_names.append(code)
        airline = ", ".join(airline_names) if airline_names else "?"

        stops = len(item.flights) - 1
        stops_str = "прямой" if stops == 0 else f"{stops} пересадка" if stops == 1 else f"{stops} пересадки"

        origin_code = first_leg.from_airport.code or origin
        dest_code = last_leg.to_airport.code or dest

        flights.append({
            "origin":       origin_code,
            "destination":  dest_code,
            "origin_city":  CITY_NAMES.get(origin_code, first_leg.from_airport.name or origin_code),
            "dest_city":    CITY_NAMES.get(dest_code, last_leg.to_airport.name or dest_code),
            "price":        item.price,
            "currency":     "EUR",
            "airline":      airline,
            "depart_at":    depart_str,
            "arrive_at":    arrive_str,
            "duration":     duration_str,
            "stops":        stops_str,
            "link":         _build_link(origin_code, dest_code, date_str),
        })

    # Sort by price
    flights.sort(key=lambda x: x["price"])
    return flights


def _date_from_range(date_from: str, date_to: str) -> list:
    """
    Generate a list of dates to try within the range.
    date_from/date_to format: 'dd/mm/yyyy'
    Returns list of 'YYYY-MM-DD' strings (up to 5 spread across range).
    """
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
        d_to = datetime.strptime(date_to, "%d/%m/%Y")
    except Exception:
        d_from = datetime.now() + timedelta(days=1)
        d_to = d_from + timedelta(days=30)

    delta = (d_to - d_from).days
    if delta <= 0:
        return [d_from.strftime("%Y-%m-%d")]

    # Pick up to 5 evenly spaced dates
    count = min(5, delta + 1)
    step = max(1, delta // (count - 1)) if count > 1 else 1
    dates = []
    for i in range(count):
        d = d_from + timedelta(days=i * step)
        if d <= d_to:
            dates.append(d.strftime("%Y-%m-%d"))
    return dates


def search_flights(
    origin: str,
    destination: str,
    date_from: str = None,
    date_to: str = None,
    price_max: int = None,
    limit: int = 10,
    **kwargs,
) -> list:
    """
    Search flights using fast-flights (Google Flights).
    Tries multiple dates in range, returns best results sorted by price.
    """
    if not FAST_FLIGHTS_OK:
        return _mock_results(origin, destination)

    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=60)).strftime("%d/%m/%Y")

    dates = _date_from_range(date_from, date_to)
    all_flights = []
    seen_keys = set()

    for date_str in dates:
        try:
            q = create_query(
                flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=destination)],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
                currency="EUR",
            )
            result = _gf(q)
            parsed = _parse_result(result, origin, destination, date_str)
            for f in parsed:
                key = f"{f['depart_at']}:{f['airline']}:{f['price']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_flights.append(f)
        except Exception as e:
            print(f"[Search] {origin}→{destination} {date_str}: {e}")
            continue

    if not all_flights:
        print(f"[Search] No results for {origin}→{destination}")
        return []

    # Filter by price
    if price_max:
        all_flights = [f for f in all_flights if f["price"] <= price_max]

    all_flights.sort(key=lambda x: x["price"])
    print(f"[Search] {origin}→{destination}: {len(all_flights)} flights found")
    return all_flights[:limit]


def search_one_way(
    origin: str,
    destination: str,
    date_from: str = None,
    date_to: str = None,
    price_max: int = None,
    limit: int = 5,
) -> list:
    """Alias for alerts — same as search_flights."""
    return search_flights(origin, destination, date_from, date_to, price_max, limit)


def get_hot_deals(origins: list, price_max: int = 80, limit: int = 20) -> list:
    """
    Find cheap flights from given airports in next 14 days.
    Tries each origin against popular destinations.
    """
    if not FAST_FLIGHTS_OK:
        return []

    from config import POPULAR_DESTINATIONS
    destinations = [code for _, code in POPULAR_DESTINATIONS[:8]]

    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    date_to = (datetime.now() + timedelta(days=14)).strftime("%d/%m/%Y")

    all_deals = []
    for origin in origins[:3]:  # limit to avoid rate limiting
        for dest in destinations[:4]:
            if origin == dest:
                continue
            try:
                flights = search_flights(origin, dest, date_from, date_to, price_max=price_max, limit=2)
                all_deals.extend(flights)
            except Exception as e:
                print(f"[HotDeals] {origin}→{dest}: {e}")
            # Small delay to avoid hammering Google
            import time
            time.sleep(0.5)

    all_deals.sort(key=lambda x: x["price"])
    return all_deals[:limit]


def get_cheapest_dates(origin: str, destination: str, months: int = 3) -> list:
    """
    Get cheapest dates for a route — tries one date per week for N months.
    Returns top 5 cheapest.
    """
    if not FAST_FLIGHTS_OK:
        return []

    all_flights = []
    seen_keys = set()
    start = datetime.now() + timedelta(days=1)

    # Try one date per week
    weeks = months * 4
    for i in range(weeks):
        date_str = (start + timedelta(weeks=i)).strftime("%Y-%m-%d")
        try:
            q = create_query(
                flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=destination)],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
                currency="EUR",
            )
            result = _gf(q)
            parsed = _parse_result(result, origin, destination, date_str)
            if parsed:
                cheapest = parsed[0]  # already sorted by price
                key = f"{cheapest['depart_at']}:{cheapest['price']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_flights.append(cheapest)
        except Exception as e:
            print(f"[CheapDates] {date_str}: {e}")
        import time
        time.sleep(0.3)

    all_flights.sort(key=lambda x: x["price"])
    return all_flights[:5]


def _mock_results(origin: str, destination: str) -> list:
    """Mock data when fast-flights not available."""
    return [
        {
            "origin": origin, "destination": destination,
            "origin_city": CITY_NAMES.get(origin, origin),
            "dest_city": CITY_NAMES.get(destination, destination),
            "price": 29, "currency": "EUR",
            "airline": "Ryanair", "depart_at": "25.04 06:00", "arrive_at": "25.04 09:30",
            "duration": "3ч 30м", "stops": "прямой",
            "link": f"https://www.google.com/travel/flights",
        },
        {
            "origin": origin, "destination": destination,
            "origin_city": CITY_NAMES.get(origin, origin),
            "dest_city": CITY_NAMES.get(destination, destination),
            "price": 45, "currency": "EUR",
            "airline": "Wizz Air", "depart_at": "28.04 14:00", "arrive_at": "28.04 17:45",
            "duration": "3ч 45м", "stops": "прямой",
            "link": f"https://www.google.com/travel/flights",
        },
    ]
