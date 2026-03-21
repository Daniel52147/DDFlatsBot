"""
Flight search via fast-flights (Google Flights scraper).
Generates real booking deep links per airline.
"""
import time
import urllib.parse
from datetime import datetime, timedelta

try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights as _gf
    FAST_FLIGHTS_OK = True
except ImportError:
    FAST_FLIGHTS_OK = False
    print("[Search] fast-flights not installed — using mock data")

CITY_NAMES = {
    "WAW": "Варшава",   "KRK": "Краков",    "WRO": "Вроцлав",
    "GDN": "Гданьск",   "KTW": "Катовице",  "POZ": "Познань",
    "BCN": "Барселона", "MAD": "Мадрид",    "TFS": "Тенерифе",
    "PMI": "Майорка",   "AGP": "Малага",    "ALC": "Аликанте",
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
    "OPO": "Порту",     "SVQ": "Севилья",   "IBZ": "Ибица",
    "SKG": "Салоники",  "HER": "Ираклион",  "RHO": "Родос",
    "DBV": "Дубровник", "SPU": "Сплит",     "ZAD": "Задар",
    "OTP": "Бухарест",  "SOF": "София",     "KBP": "Киев",
    "RIX": "Рига",      "TLL": "Таллин",    "VNO": "Вильнюс",
}

# ── Airline IATA → booking URL templates ──────────────────────────────────────
# {origin}, {dest}, {date} placeholders (date = YYYY-MM-DD)
AIRLINE_LINKS = {
    "FR":  "https://www.ryanair.com/en/cheap-flights/{origin_lc}-to-{dest_lc}/",
    "W6":  "https://wizzair.com/#/booking/select-flight/{origin}/{dest}/{date}/null/1/0/0/null",
    "VY":  "https://www.vueling.com/en/book-your-flights/search?dep={origin}&arr={dest}&depDate={date}&pax=1",
    "U2":  "https://www.easyjet.com/en/cheap-flights/{origin_lc}-{dest_lc}",
    "LO":  "https://www.lot.com/en/en/flight-search#/results?from={origin}&to={dest}&departure={date}&adults=1&tripType=ONE_WAY",
    "LH":  "https://www.lufthansa.com/de/en/flight-search?origin={origin}&destination={dest}&outboundDate={date}&adults=1",
    "BA":  "https://www.britishairways.com/travel/fx/public/en_gb?eId=106047&from={origin}&to={dest}&depart={date}&adult=1",
    "AF":  "https://www.airfrance.com/en/flight/{origin_lc}-{dest_lc}",
    "KL":  "https://www.klm.com/en/search#outbound={origin},{dest},{date};cabin=Y;adults=1",
    "TK":  "https://www.turkishairlines.com/en-int/flights/find-flights/?origin={origin}&destination={dest}&departureDate={date}&adult=1",
    "EK":  "https://www.emirates.com/english/book/flights/?origin={origin}&destination={dest}&departDate={date}&numAdults=1",
    "QR":  "https://www.qatarairways.com/en/flights.html?from={origin}&to={dest}&depart={date}&adult=1",
    "PS":  "https://www.flyuia.com/ua/en/flights?from={origin}&to={dest}&date={date}&adults=1",
}

GOOGLE_FLIGHTS_TPL = (
    "https://www.google.com/travel/flights/search"
    "?tfs=CBwQAhoeEgoyMDI1LTAxLTAxagcIARIDe3tvcmlnaW59fXIHCAESA3t7ZGVzdH19QAFIAXABggELCP___________wGYAQI"
)


def _build_link(origin: str, dest: str, date_str: str, airline: str = "") -> str:
    """
    Build the best booking link for a given flight.
    Tries airline-specific deep link first, falls back to Google Flights.
    date_str: YYYY-MM-DD
    """
    code = airline[:2].upper() if airline else ""

    # Try airline-specific link
    if code in AIRLINE_LINKS:
        try:
            tpl = AIRLINE_LINKS[code]
            # Parse date parts
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            url = tpl.format(
                origin=origin,
                dest=dest,
                origin_lc=origin.lower(),
                dest_lc=dest.lower(),
                date=date_str,
                date_dd=dt.strftime("%d"),
                date_mm=dt.strftime("%m"),
                date_yyyy=dt.strftime("%Y"),
            )
            return url
        except Exception:
            pass

    # Google Flights deep link (works for all airlines)
    return _google_flights_link(origin, dest, date_str)


def _google_flights_link(origin: str, dest: str, date_str: str, return_date: str = None) -> str:
    """Proper Google Flights search URL."""
    base = "https://www.google.com/travel/flights"
    if return_date:
        q = f"Flights from {origin} to {dest} on {date_str} returning {return_date}"
    else:
        q = f"Flights from {origin} to {dest} on {date_str}"
    return f"{base}?q={urllib.parse.quote(q)}"


def _aviasales_link(origin: str, dest: str, date_str: str) -> str:
    """Aviasales search link (works without API key)."""
    # Format: DDMM e.g. 2504 for April 25
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        d = dt.strftime("%d%m")
    except Exception:
        d = "0101"
    return f"https://www.aviasales.ru/search/{origin}{d}{dest}1"


def _fmt_dt(sdt) -> str:
    try:
        y, m, d = sdt.date
        h, mi = sdt.time
        return f"{d:02d}.{m:02d} {h:02d}:{mi:02d}"
    except Exception:
        return ""


def _duration_str(minutes: int) -> str:
    if not minutes:
        return ""
    h, m = divmod(minutes, 60)
    return f"{h}ч {m}м" if m else f"{h}ч"


def _parse_result(result, origin: str, dest: str, date_str: str) -> list:
    flights = []
    for item in result:
        if not item.flights:
            continue
        first_leg = item.flights[0]
        last_leg  = item.flights[-1]

        depart_str   = _fmt_dt(first_leg.departure)
        arrive_str   = _fmt_dt(last_leg.arrival)
        total_min    = sum(getattr(f, "duration", 0) for f in item.flights)
        duration_str = _duration_str(total_min)

        airlines = list(item.airlines) if item.airlines else []
        airline  = ", ".join(airlines) if airlines else "?"
        main_code = airlines[0] if airlines else ""

        stops     = len(item.flights) - 1
        stops_str = "прямой" if stops == 0 else (
            f"{stops} пересадка" if stops == 1 else f"{stops} пересадки"
        )

        origin_code = getattr(first_leg.from_airport, "code", None) or origin
        dest_code   = getattr(last_leg.to_airport,   "code", None) or dest

        # Build best link
        link = _build_link(origin_code, dest_code, date_str, main_code)
        # Also add Aviasales as backup
        aviasales = _aviasales_link(origin_code, dest_code, date_str)

        flights.append({
            "origin":       origin_code,
            "destination":  dest_code,
            "origin_city":  CITY_NAMES.get(origin_code, getattr(first_leg.from_airport, "name", origin_code) or origin_code),
            "dest_city":    CITY_NAMES.get(dest_code,   getattr(last_leg.to_airport,   "name", dest_code)   or dest_code),
            "price":        item.price,
            "currency":     "EUR",
            "airline":      airline,
            "airline_code": main_code,
            "depart_at":    depart_str,
            "arrive_at":    arrive_str,
            "duration":     duration_str,
            "stops":        stops_str,
            "link":         link,
            "link_aviasales": aviasales,
        })

    flights.sort(key=lambda x: x["price"])
    return flights


def _date_from_range(date_from: str, date_to: str) -> list:
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
        d_to   = datetime.strptime(date_to,   "%d/%m/%Y")
    except Exception:
        d_from = datetime.now() + timedelta(days=1)
        d_to   = d_from + timedelta(days=30)

    delta = (d_to - d_from).days
    if delta <= 0:
        return [d_from.strftime("%Y-%m-%d")]

    count = min(5, delta + 1)
    step  = max(1, delta // (count - 1)) if count > 1 else 1
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
    if not FAST_FLIGHTS_OK:
        return _mock_results(origin, destination)

    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=60)).strftime("%d/%m/%Y")

    dates = _date_from_range(date_from, date_to)
    all_flights = []
    seen_keys   = set()

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
            for f in _parse_result(result, origin, destination, date_str):
                key = f"{f['depart_at']}:{f['airline']}:{f['price']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_flights.append(f)
        except Exception as e:
            print(f"[Search] {origin}→{destination} {date_str}: {e}")

    if not all_flights:
        return []

    if price_max:
        all_flights = [f for f in all_flights if f["price"] <= price_max]

    all_flights.sort(key=lambda x: x["price"])
    print(f"[Search] {origin}→{destination}: {len(all_flights)} results")
    return all_flights[:limit]


def search_one_way(origin, destination, date_from=None, date_to=None, price_max=None, limit=5):
    return search_flights(origin, destination, date_from, date_to, price_max, limit)


def search_round_trip(
    origin: str,
    destination: str,
    date_from: str = None,
    date_to: str = None,
    return_from: str = None,
    return_to: str = None,
    limit: int = 8,
) -> list:
    if not FAST_FLIGHTS_OK:
        return _mock_results(origin, destination)

    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
    if not return_from:
        return_from = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
    if not return_to:
        return_to = (datetime.now() + timedelta(days=37)).strftime("%d/%m/%Y")

    out_dates = _date_from_range(date_from, date_to)[:3]
    ret_dates = _date_from_range(return_from, return_to)[:2]
    all_flights = []
    seen_keys   = set()

    for out_date in out_dates:
        for ret_date in ret_dates:
            try:
                q = create_query(
                    flights=[
                        FlightQuery(date=out_date, from_airport=origin, to_airport=destination),
                        FlightQuery(date=ret_date, from_airport=destination, to_airport=origin),
                    ],
                    trip="round-trip",
                    seat="economy",
                    passengers=Passengers(adults=1),
                    currency="EUR",
                )
                result = _gf(q)
                for f in _parse_result(result, origin, destination, out_date):
                    f["return_at"] = ret_date
                    # Update link to include return date
                    f["link"] = _google_flights_link(origin, destination, out_date, ret_date)
                    key = f"{f['depart_at']}:{f['airline']}:{f['price']}:{ret_date}"
                    if key not in seen_keys:
                        seen_keys.add(key)
                        all_flights.append(f)
            except Exception as e:
                print(f"[RoundTrip] {origin}↔{destination} {out_date}/{ret_date}: {e}")
            time.sleep(0.3)

    all_flights.sort(key=lambda x: x["price"])
    return all_flights[:limit]


def get_hot_deals(origins: list, price_max: int = 80, limit: int = 20) -> list:
    if not FAST_FLIGHTS_OK:
        return []

    from config import POPULAR_DESTINATIONS
    destinations = [code for _, code in POPULAR_DESTINATIONS[:8]]
    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    date_to   = (datetime.now() + timedelta(days=14)).strftime("%d/%m/%Y")
    all_deals = []

    for origin in origins[:3]:
        for dest in destinations[:4]:
            if origin == dest:
                continue
            try:
                flights = search_flights(origin, dest, date_from, date_to, price_max=price_max, limit=2)
                all_deals.extend(flights)
            except Exception as e:
                print(f"[HotDeals] {origin}→{dest}: {e}")
            time.sleep(0.5)

    all_deals.sort(key=lambda x: x["price"])
    return all_deals[:limit]


def get_cheapest_dates(origin: str, destination: str, months: int = 3) -> list:
    if not FAST_FLIGHTS_OK:
        return []

    all_flights = []
    seen_keys   = set()
    start       = datetime.now() + timedelta(days=1)

    for i in range(months * 4):
        date_str = (start + timedelta(weeks=i)).strftime("%Y-%m-%d")
        try:
            q = create_query(
                flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=destination)],
                trip="one-way",
                seat="economy",
                passengers=Passengers(adults=1),
                currency="EUR",
            )
            result  = _gf(q)
            parsed  = _parse_result(result, origin, destination, date_str)
            if parsed:
                cheapest = parsed[0]
                key = f"{cheapest['depart_at']}:{cheapest['price']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_flights.append(cheapest)
        except Exception as e:
            print(f"[CheapDates] {date_str}: {e}")
        time.sleep(0.3)

    all_flights.sort(key=lambda x: x["price"])
    return all_flights[:5]


def _mock_results(origin: str, destination: str) -> list:
    today = datetime.now() + timedelta(days=7)
    date_str = today.strftime("%Y-%m-%d")
    return [
        {
            "origin": origin, "destination": destination,
            "origin_city": CITY_NAMES.get(origin, origin),
            "dest_city":   CITY_NAMES.get(destination, destination),
            "price": 29, "currency": "EUR",
            "airline": "Ryanair", "airline_code": "FR",
            "depart_at": today.strftime("%d.%m 06:00"),
            "arrive_at": today.strftime("%d.%m 09:30"),
            "duration": "3ч 30м", "stops": "прямой",
            "link": _build_link(origin, destination, date_str, "FR"),
            "link_aviasales": _aviasales_link(origin, destination, date_str),
        },
        {
            "origin": origin, "destination": destination,
            "origin_city": CITY_NAMES.get(origin, origin),
            "dest_city":   CITY_NAMES.get(destination, destination),
            "price": 45, "currency": "EUR",
            "airline": "Wizz Air", "airline_code": "W6",
            "depart_at": (today + timedelta(days=3)).strftime("%d.%m 14:00"),
            "arrive_at": (today + timedelta(days=3)).strftime("%d.%m 17:45"),
            "duration": "3ч 45м", "stops": "прямой",
            "link": _build_link(origin, destination, (today + timedelta(days=3)).strftime("%Y-%m-%d"), "W6"),
            "link_aviasales": _aviasales_link(origin, destination, (today + timedelta(days=3)).strftime("%Y-%m-%d")),
        },
    ]
