"""
Flight search — primary: Aviasales open search (no API key needed)
Fallback: fast-flights (Google Flights scraper)
"""
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta

# ── fast-flights fallback ──────────────────────────────────────────────────────
try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights as _gf
    FAST_FLIGHTS_OK = True
except Exception:
    FAST_FLIGHTS_OK = False

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
    "OTP": "Бухарест",  "SOF": "София",
    "RIX": "Рига",      "TLL": "Таллин",    "VNO": "Вильнюс",
}

AIRLINE_NAMES = {
    "FR": "Ryanair", "W6": "Wizz Air", "VY": "Vueling", "U2": "easyJet",
    "LO": "LOT",     "LH": "Lufthansa","BA": "British Airways","AF": "Air France",
    "KL": "KLM",     "TK": "Turkish Airlines","EK": "Emirates",
    "QR": "Qatar Airways","TP": "TAP Air Portugal","PS": "Ukraine Intl",
    "FR ": "Ryanair","SN": "Brussels Airlines","OS": "Austrian",
}

AIRLINE_ICONS = {
    "FR": "🟡", "W6": "🟣", "VY": "🟠", "U2": "🟠",
    "LO": "🔵", "LH": "🟡", "BA": "🔵", "AF": "🔵",
    "KL": "🔵", "TP": "🟢", "EK": "🔴", "QR": "🟤",
    "TK": "🔴", "SU": "🔴", "PS": "🔵",
}


# ── Link builders ──────────────────────────────────────────────────────────────

def _aviasales_link(origin: str, dest: str, date_str: str) -> str:
    """Aviasales search link — always works, no API key."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        d = dt.strftime("%d%m")
    except Exception:
        d = "0101"
    return f"https://www.aviasales.ru/search/{origin}{d}{dest}1"


def _google_flights_link(origin: str, dest: str, date_str: str, return_date: str = None) -> str:
    if return_date:
        q = f"Flights from {origin} to {dest} on {date_str} returning {return_date}"
    else:
        q = f"Flights from {origin} to {dest} on {date_str}"
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"


def _airline_booking_link(airline_code: str, origin: str, dest: str, date_str: str) -> str:
    """Direct airline booking links."""
    c = airline_code.upper()
    o, d = origin.upper(), dest.upper()
    ol, dl = o.lower(), d.lower()
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        dt = datetime.now() + timedelta(days=7)

    if c == "FR":  # Ryanair
        return f"https://www.ryanair.com/en/cheap-flights/{ol}-to-{dl}/"
    if c == "W6":  # Wizz Air
        return f"https://wizzair.com/#/booking/select-flight/{o}/{d}/{date_str}/null/1/0/0/null"
    if c == "LO":  # LOT
        return (f"https://www.lot.com/en/en/flight-search#/results"
                f"?from={o}&to={d}&departure={date_str}&adults=1&tripType=ONE_WAY")
    if c == "U2":  # easyJet
        return f"https://www.easyjet.com/en/cheap-flights/{ol}-{dl}"
    if c == "VY":  # Vueling
        return (f"https://www.vueling.com/en/book-your-flights/search"
                f"?dep={o}&arr={d}&depDate={date_str}&pax=1")
    if c == "LH":  # Lufthansa
        return (f"https://www.lufthansa.com/de/en/flight-search"
                f"?origin={o}&destination={d}&outboundDate={date_str}&adults=1")
    if c == "TK":  # Turkish
        return (f"https://www.turkishairlines.com/en-int/flights/find-flights/"
                f"?origin={o}&destination={d}&departureDate={date_str}&adult=1")
    # Default: Google Flights
    return _google_flights_link(origin, dest, date_str)


# ── Aviasales open data API ────────────────────────────────────────────────────

def _aviasales_search(origin: str, dest: str, date_from: str, date_to: str,
                      price_max: int = None, limit: int = 10) -> list:
    """
    Use Aviasales open prices API — no API key needed.
    Returns cheapest flights for the month.
    """
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d_from = datetime.now() + timedelta(days=1)

    month = d_from.strftime("%Y-%m")
    url = (
        f"https://api.travelpayouts.com/v1/prices/cheap"
        f"?origin={origin}&destination={dest}"
        f"&depart_date={month}&one_way=true&currency=eur&limit=30"
    )
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SkyCheapBot/1.0)"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"[Aviasales] API error: {e}")
        return []

    if not data.get("success") or not data.get("data"):
        return []

    dest_data = data["data"].get(dest, {})
    results = []
    for num, item in dest_data.items():
        price = item.get("price", 0)
        if price_max and price > price_max:
            continue
        dep_date = item.get("departure_at", "")
        airline_code = item.get("airline", "")
        airline_name = AIRLINE_NAMES.get(airline_code, airline_code)

        # Format date
        try:
            dt = datetime.fromisoformat(dep_date[:16])
            depart_str = dt.strftime("%d.%m %H:%M")
            date_str_iso = dt.strftime("%Y-%m-%d")
        except Exception:
            depart_str = dep_date[:10]
            date_str_iso = dep_date[:10] if dep_date else (d_from + timedelta(days=7)).strftime("%Y-%m-%d")

        transfers = item.get("transfers", 0)
        stops_str = "прямой" if transfers == 0 else f"{transfers} пересадка"

        link = _airline_booking_link(airline_code, origin, dest, date_str_iso)
        aviasales = _aviasales_link(origin, dest, date_str_iso)

        results.append({
            "origin":         origin,
            "destination":    dest,
            "origin_city":    CITY_NAMES.get(origin, origin),
            "dest_city":      CITY_NAMES.get(dest, dest),
            "price":          price,
            "currency":       "EUR",
            "airline":        airline_name,
            "airline_code":   airline_code,
            "depart_at":      depart_str,
            "arrive_at":      "",
            "duration":       f"{item.get('duration', 0) // 60}ч {item.get('duration', 0) % 60}м" if item.get("duration") else "",
            "stops":          stops_str,
            "link":           link,
            "link_aviasales": aviasales,
        })

    results.sort(key=lambda x: x["price"])
    print(f"[Aviasales] {origin}→{dest}: {len(results)} results")
    return results[:limit]


# ── fast-flights fallback ──────────────────────────────────────────────────────

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


def _parse_ff_result(result, origin: str, dest: str, date_str: str) -> list:
    flights = []
    for item in result:
        if not item.flights:
            continue
        first_leg = item.flights[0]
        last_leg  = item.flights[-1]
        depart_str   = _fmt_dt(first_leg.departure)
        arrive_str   = _fmt_dt(last_leg.arrival)
        total_min    = sum(getattr(f, "duration", 0) for f in item.flights)
        airlines     = list(item.airlines) if item.airlines else []
        airline      = ", ".join(AIRLINE_NAMES.get(c, c) for c in airlines) if airlines else "?"
        main_code    = airlines[0] if airlines else ""
        stops        = len(item.flights) - 1
        stops_str    = "прямой" if stops == 0 else f"{stops} пересадка" if stops == 1 else f"{stops} пересадки"
        origin_code  = getattr(first_leg.from_airport, "code", None) or origin
        dest_code    = getattr(last_leg.to_airport,   "code", None) or dest
        link         = _airline_booking_link(main_code, origin_code, dest_code, date_str)
        flights.append({
            "origin":         origin_code,
            "destination":    dest_code,
            "origin_city":    CITY_NAMES.get(origin_code, origin_code),
            "dest_city":      CITY_NAMES.get(dest_code, dest_code),
            "price":          item.price,
            "currency":       "EUR",
            "airline":        airline,
            "airline_code":   main_code,
            "depart_at":      depart_str,
            "arrive_at":      arrive_str,
            "duration":       _duration_str(total_min),
            "stops":          stops_str,
            "link":           link,
            "link_aviasales": _aviasales_link(origin_code, dest_code, date_str),
        })
    flights.sort(key=lambda x: x["price"])
    return flights


def _fast_flights_search(origin: str, dest: str, date_from: str, date_to: str,
                         price_max: int = None, limit: int = 10) -> list:
    if not FAST_FLIGHTS_OK:
        return []
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
        d_to   = datetime.strptime(date_to,   "%d/%m/%Y")
    except Exception:
        d_from = datetime.now() + timedelta(days=1)
        d_to   = d_from + timedelta(days=30)

    delta = (d_to - d_from).days
    count = min(4, delta + 1)
    step  = max(1, delta // (count - 1)) if count > 1 else 1
    dates = [(d_from + timedelta(days=i * step)).strftime("%Y-%m-%d") for i in range(count)]

    all_flights = []
    seen = set()
    for date_str in dates:
        try:
            q = create_query(
                flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=dest)],
                trip="one-way", seat="economy",
                passengers=Passengers(adults=1), currency="EUR",
            )
            result = _gf(q)
            for f in _parse_ff_result(result, origin, dest, date_str):
                key = f"{f['depart_at']}:{f['airline']}:{f['price']}"
                if key not in seen:
                    seen.add(key)
                    all_flights.append(f)
        except Exception as e:
            print(f"[FastFlights] {origin}→{dest} {date_str}: {e}")
    if price_max:
        all_flights = [f for f in all_flights if f["price"] <= price_max]
    all_flights.sort(key=lambda x: x["price"])
    return all_flights[:limit]


# ── Date helpers ───────────────────────────────────────────────────────────────

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
    return [(d_from + timedelta(days=i * step)).strftime("%Y-%m-%d") for i in range(count) if d_from + timedelta(days=i * step) <= d_to]


# ── Public API ─────────────────────────────────────────────────────────────────

def search_flights(origin: str, destination: str,
                   date_from: str = None, date_to: str = None,
                   price_max: int = None, limit: int = 10, **kwargs) -> list:
    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=60)).strftime("%d/%m/%Y")

    # Try Aviasales first (most reliable, no scraping)
    results = _aviasales_search(origin, destination, date_from, date_to, price_max, limit)
    if results:
        return results

    # Fallback: fast-flights (Google Flights scraper)
    print(f"[Search] Aviasales empty, trying fast-flights for {origin}→{destination}")
    results = _fast_flights_search(origin, destination, date_from, date_to, price_max, limit)
    if results:
        return results

    # Last resort: Aviasales link only (no price data but real link)
    print(f"[Search] No results for {origin}→{destination}, returning link-only")
    return []


def search_one_way(origin, destination, date_from=None, date_to=None,
                   price_max=None, limit=5) -> list:
    return search_flights(origin, destination, date_from, date_to, price_max, limit)


def search_round_trip(origin: str, destination: str,
                      date_from: str = None, date_to: str = None,
                      return_from: str = None, return_to: str = None,
                      limit: int = 8) -> list:
    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    if not date_to:
        date_to = (datetime.now() + timedelta(days=30)).strftime("%d/%m/%Y")
    if not return_from:
        return_from = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")
    if not return_to:
        return_to = (datetime.now() + timedelta(days=37)).strftime("%d/%m/%Y")

    # Get outbound
    out = search_flights(origin, destination, date_from, date_to, limit=limit)
    # Get return
    ret = search_flights(destination, origin, return_from, return_to, limit=3)

    if not out:
        return []

    # Combine: pair cheapest outbound with cheapest return
    results = []
    ret_price = ret[0]["price"] if ret else 0
    ret_date  = ret[0]["depart_at"][:5] if ret else ""

    for f in out[:limit]:
        combined = dict(f)
        if ret_price:
            combined["price"]     = f["price"] + ret_price
            combined["return_at"] = ret_date
            # Update link to Google Flights round-trip
            try:
                d_from_iso = datetime.strptime(date_from, "%d/%m/%Y").strftime("%Y-%m-%d")
                d_ret_iso  = datetime.strptime(return_from, "%d/%m/%Y").strftime("%Y-%m-%d")
                combined["link"] = _google_flights_link(origin, destination, d_from_iso, d_ret_iso)
            except Exception:
                pass
        results.append(combined)

    results.sort(key=lambda x: x["price"])
    return results[:limit]


def get_hot_deals(origins: list, price_max: int = 80, limit: int = 20) -> list:
    from config import POPULAR_DESTINATIONS
    destinations = [code for _, code in POPULAR_DESTINATIONS[:8]]
    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    date_to   = (datetime.now() + timedelta(days=14)).strftime("%d/%m/%Y")
    all_deals = []

    for origin in origins[:3]:
        for dest in destinations[:5]:
            if origin == dest:
                continue
            try:
                flights = search_flights(origin, dest, date_from, date_to,
                                         price_max=price_max, limit=2)
                all_deals.extend(flights)
            except Exception as e:
                print(f"[HotDeals] {origin}→{dest}: {e}")
            time.sleep(0.2)

    all_deals.sort(key=lambda x: x["price"])
    return all_deals[:limit]


def get_cheapest_dates(origin: str, destination: str, months: int = 3) -> list:
    all_flights = []
    seen = set()
    now = datetime.now()

    for i in range(months):
        month_start = (now.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        d_from = max(now + timedelta(days=1), month_start).strftime("%d/%m/%Y")
        d_to   = ((month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)).strftime("%d/%m/%Y")
        try:
            flights = _aviasales_search(origin, destination, d_from, d_to, limit=3)
            for f in flights:
                key = f"{f['depart_at']}:{f['price']}"
                if key not in seen:
                    seen.add(key)
                    all_flights.append(f)
        except Exception as e:
            print(f"[CheapDates] month {i}: {e}")

    # Fallback to fast-flights if no results
    if not all_flights and FAST_FLIGHTS_OK:
        start = datetime.now() + timedelta(days=1)
        for i in range(months * 4):
            date_str = (start + timedelta(weeks=i)).strftime("%Y-%m-%d")
            try:
                q = create_query(
                    flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=destination)],
                    trip="one-way", seat="economy",
                    passengers=Passengers(adults=1), currency="EUR",
                )
                parsed = _parse_ff_result(_gf(q), origin, destination, date_str)
                if parsed:
                    key = f"{parsed[0]['depart_at']}:{parsed[0]['price']}"
                    if key not in seen:
                        seen.add(key)
                        all_flights.append(parsed[0])
            except Exception as e:
                print(f"[CheapDates FF] {date_str}: {e}")
            time.sleep(0.3)

    all_flights.sort(key=lambda x: x["price"])
    return all_flights[:5]
