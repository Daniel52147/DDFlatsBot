"""
Flight search — sources:
1. Aviasales open prices API (no key needed)
2. Ryanair public API
3. Wizz Air public API
4. fast-flights (Google Flights scraper) — fallback
In-memory cache: 30 min per route.
"""
import time
import threading
import urllib.parse
import urllib.request
import json
from datetime import datetime, timedelta

try:
    from fast_flights import FlightQuery, Passengers, create_query, get_flights as _gf
    FAST_FLIGHTS_OK = True
except Exception:
    FAST_FLIGHTS_OK = False

# ── In-memory cache ────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 1800  # 30 minutes


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["ts"] < CACHE_TTL:
            print(f"[Cache] HIT {key}")
            return entry["data"]
    return None


def _cache_set(key: str, data: list):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}


# ── City / airline maps ────────────────────────────────────────────────────────
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
    "KTW": "Катовице",  "SZZ": "Щецин",
}

AIRLINE_NAMES = {
    "FR": "Ryanair",    "W6": "Wizz Air",   "VY": "Vueling",
    "U2": "easyJet",    "LO": "LOT",        "LH": "Lufthansa",
    "BA": "British Airways", "AF": "Air France", "KL": "KLM",
    "TK": "Turkish Airlines", "EK": "Emirates", "QR": "Qatar Airways",
    "TP": "TAP Portugal", "PS": "Ukraine Intl", "SN": "Brussels Airlines",
    "OS": "Austrian",   "SK": "SAS",        "AY": "Finnair",
    "IB": "Iberia",     "BT": "airBaltic",
}


# ── Link builders ──────────────────────────────────────────────────────────────

def _aviasales_link(origin: str, dest: str, date_str: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m")
    except Exception:
        d = "0101"
    return f"https://www.aviasales.ru/search/{origin}{d}{dest}1"


def _google_flights_link(origin: str, dest: str, date_str: str, ret: str = None) -> str:
    q = f"Flights from {origin} to {dest} on {date_str}"
    if ret:
        q += f" returning {ret}"
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"


def _airline_link(code: str, origin: str, dest: str, date_str: str) -> str:
    c = code.upper()
    o, d = origin.upper(), dest.upper()
    if c == "FR":
        return f"https://www.ryanair.com/en/cheap-flights/{o.lower()}-to-{d.lower()}/"
    if c == "W6":
        return f"https://wizzair.com/#/booking/select-flight/{o}/{d}/{date_str}/null/1/0/0/null"
    if c == "LO":
        return f"https://www.lot.com/en/en/flight-search#/results?from={o}&to={d}&departure={date_str}&adults=1&tripType=ONE_WAY"
    if c == "U2":
        return f"https://www.easyjet.com/en/cheap-flights/{o.lower()}-{d.lower()}"
    if c == "LH":
        return f"https://www.lufthansa.com/de/en/flight-search?origin={o}&destination={d}&outboundDate={date_str}&adults=1"
    if c == "TK":
        return f"https://www.turkishairlines.com/en-int/flights/find-flights/?origin={o}&destination={d}&departureDate={date_str}&adult=1"
    if c == "VY":
        return f"https://www.vueling.com/en/book-your-flights/search?dep={o}&arr={d}&depDate={date_str}&pax=1"
    return _google_flights_link(origin, dest, date_str)


def _make_flight(origin, dest, price, airline_code, depart_str, arrive_str,
                 duration_min, stops, date_str) -> dict:
    airline_name = AIRLINE_NAMES.get(airline_code.upper(), airline_code)
    stops_str = "прямой" if stops == 0 else f"{stops} пересадка" if stops == 1 else f"{stops} пересадки"
    dur_str = ""
    if duration_min:
        h, m = divmod(int(duration_min), 60)
        dur_str = f"{h}ч {m}м" if m else f"{h}ч"
    return {
        "origin":         origin,
        "destination":    dest,
        "origin_city":    CITY_NAMES.get(origin, origin),
        "dest_city":      CITY_NAMES.get(dest, dest),
        "price":          int(price),
        "currency":       "EUR",
        "airline":        airline_name,
        "airline_code":   airline_code.upper(),
        "depart_at":      depart_str,
        "arrive_at":      arrive_str,
        "duration":       dur_str,
        "stops":          stops_str,
        "link":           _airline_link(airline_code, origin, dest, date_str),
        "link_aviasales": _aviasales_link(origin, dest, date_str),
    }


# ── Source 1: Aviasales open API ───────────────────────────────────────────────

def _aviasales_search(origin: str, dest: str, date_from: str,
                      price_max: int = None, limit: int = 10) -> list:
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d_from = datetime.now() + timedelta(days=1)

    results = []
    # Try current month and next month
    for offset in range(2):
        month_dt = (d_from.replace(day=1) + timedelta(days=32 * offset)).replace(day=1)
        month = month_dt.strftime("%Y-%m")
        url = (f"https://api.travelpayouts.com/v1/prices/cheap"
               f"?origin={origin}&destination={dest}"
               f"&depart_date={month}&one_way=true&currency=eur&limit=20")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SkyCheapBot/2.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            if not data.get("success"):
                continue
            dest_data = data.get("data", {}).get(dest, {})
            for _, item in dest_data.items():
                price = item.get("price", 0)
                if not price or (price_max and price > price_max):
                    continue
                dep = item.get("departure_at", "")
                try:
                    dt = datetime.fromisoformat(dep[:16])
                    depart_str = dt.strftime("%d.%m %H:%M")
                    date_iso   = dt.strftime("%Y-%m-%d")
                except Exception:
                    depart_str = dep[:10]
                    date_iso   = month_dt.strftime("%Y-%m-%d")
                code = item.get("airline", "")
                results.append(_make_flight(
                    origin, dest, price, code,
                    depart_str, "", item.get("duration", 0),
                    item.get("transfers", 0), date_iso,
                ))
        except Exception as e:
            print(f"[Aviasales] {origin}→{dest} {month}: {e}")

    results.sort(key=lambda x: x["price"])
    seen, out = set(), []
    for f in results:
        k = f"{f['depart_at']}:{f['price']}"
        if k not in seen:
            seen.add(k)
            out.append(f)
    print(f"[Aviasales] {origin}→{dest}: {len(out)} results")
    return out[:limit]


# ── Source 2: Ryanair public API ───────────────────────────────────────────────

def _ryanair_search(origin: str, dest: str, date_from: str,
                    price_max: int = None, limit: int = 5) -> list:
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
        d_to   = d_from + timedelta(days=60)
    except Exception:
        return []

    url = (f"https://www.ryanair.com/api/farfnd/v4/oneWayFares"
           f"?departureAirportIataCode={origin}"
           f"&arrivalAirportIataCode={dest}"
           f"&outboundDepartureDateFrom={d_from.strftime('%Y-%m-%d')}"
           f"&outboundDepartureDateTo={d_to.strftime('%Y-%m-%d')}"
           f"&currency=EUR&priceValueTo=300&limit=10")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        fares = data.get("fares", [])
        results = []
        for fare in fares:
            price = fare.get("price", {}).get("value", 0)
            if not price or (price_max and price > price_max):
                continue
            dep = fare.get("outbound", {}).get("departureDate", "")
            arr = fare.get("outbound", {}).get("arrivalDate", "")
            try:
                dt_dep = datetime.fromisoformat(dep[:16])
                dt_arr = datetime.fromisoformat(arr[:16])
                depart_str = dt_dep.strftime("%d.%m %H:%M")
                arrive_str = dt_arr.strftime("%d.%m %H:%M")
                date_iso   = dt_dep.strftime("%Y-%m-%d")
                dur_min    = int((dt_arr - dt_dep).total_seconds() / 60)
            except Exception:
                depart_str = dep[:10]
                arrive_str = ""
                date_iso   = dep[:10]
                dur_min    = 0
            results.append(_make_flight(
                origin, dest, price, "FR",
                depart_str, arrive_str, dur_min, 0, date_iso,
            ))
        results.sort(key=lambda x: x["price"])
        print(f"[Ryanair] {origin}→{dest}: {len(results)} results")
        return results[:limit]
    except Exception as e:
        print(f"[Ryanair] {origin}→{dest}: {e}")
        return []


# ── Source 3: Wizz Air public API ─────────────────────────────────────────────

def _wizzair_search(origin: str, dest: str, date_from: str,
                    price_max: int = None, limit: int = 5) -> list:
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        return []

    url = (f"https://be.wizzair.com/14.3.0/Api/search/timetable"
           f"?departureStation={origin}&arrivalStation={dest}"
           f"&from={d_from.strftime('%Y-%m-%d')}"
           f"&to={(d_from + timedelta(days=60)).strftime('%Y-%m-%d')}"
           f"&priceType=regular&adultCount=1&childCount=0&infantCount=0")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "x-requestedwith": "XMLHttpRequest",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        results = []
        for day in data.get("outboundFlights", []):
            for flight in day.get("departures", []):
                price = flight.get("price", {}).get("amount", 0)
                if not price or (price_max and price > price_max):
                    continue
                dep = flight.get("departureDateTime", "")
                arr = flight.get("arrivalDateTime", "")
                try:
                    dt_dep = datetime.fromisoformat(dep[:16])
                    dt_arr = datetime.fromisoformat(arr[:16])
                    depart_str = dt_dep.strftime("%d.%m %H:%M")
                    arrive_str = dt_arr.strftime("%d.%m %H:%M")
                    date_iso   = dt_dep.strftime("%Y-%m-%d")
                    dur_min    = int((dt_arr - dt_dep).total_seconds() / 60)
                except Exception:
                    depart_str = dep[:10]
                    arrive_str = ""
                    date_iso   = dep[:10]
                    dur_min    = 0
                results.append(_make_flight(
                    origin, dest, price, "W6",
                    depart_str, arrive_str, dur_min, 0, date_iso,
                ))
        results.sort(key=lambda x: x["price"])
        print(f"[Wizz] {origin}→{dest}: {len(results)} results")
        return results[:limit]
    except Exception as e:
        print(f"[Wizz] {origin}→{dest}: {e}")
        return []


# ── Source 4: fast-flights fallback ───────────────────────────────────────────

def _fmt_dt(sdt) -> str:
    try:
        y, m, d = sdt.date
        h, mi = sdt.time
        return f"{d:02d}.{m:02d} {h:02d}:{mi:02d}"
    except Exception:
        return ""


def _fast_flights_search(origin: str, dest: str, date_from: str,
                         price_max: int = None, limit: int = 10) -> list:
    if not FAST_FLIGHTS_OK:
        return []
    try:
        d_from = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d_from = datetime.now() + timedelta(days=1)

    results = []
    seen = set()
    for i in range(4):
        date_str = (d_from + timedelta(weeks=i)).strftime("%Y-%m-%d")
        try:
            q = create_query(
                flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=dest)],
                trip="one-way", seat="economy",
                passengers=Passengers(adults=1), currency="EUR",
            )
            for item in _gf(q):
                if not item.flights:
                    continue
                airlines  = list(item.airlines) if item.airlines else []
                code      = airlines[0] if airlines else ""
                first_leg = item.flights[0]
                last_leg  = item.flights[-1]
                dep_str   = _fmt_dt(first_leg.departure)
                arr_str   = _fmt_dt(last_leg.arrival)
                total_min = sum(getattr(f, "duration", 0) for f in item.flights)
                stops     = len(item.flights) - 1
                price     = item.price
                if price_max and price > price_max:
                    continue
                k = f"{dep_str}:{price}"
                if k in seen:
                    continue
                seen.add(k)
                results.append(_make_flight(
                    origin, dest, price, code,
                    dep_str, arr_str, total_min, stops, date_str,
                ))
        except Exception as e:
            print(f"[FastFlights] {origin}→{dest} {date_str}: {e}")
    results.sort(key=lambda x: x["price"])
    print(f"[FastFlights] {origin}→{dest}: {len(results)} results")
    return results[:limit]


# ── Merge results from multiple sources ───────────────────────────────────────

def _merge(*lists) -> list:
    seen, out = set(), []
    for lst in lists:
        for f in lst:
            k = f"{f['depart_at']}:{f['airline_code']}:{f['price']}"
            if k not in seen:
                seen.add(k)
                out.append(f)
    out.sort(key=lambda x: x["price"])
    return out


# ── Public API ─────────────────────────────────────────────────────────────────

def search_flights(origin: str, destination: str,
                   date_from: str = None, date_to: str = None,
                   price_max: int = None, limit: int = 10, **kwargs) -> list:
    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    cache_key = f"{origin}:{destination}:{date_from}:{price_max}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached[:limit]

    # Run all sources in parallel threads
    results_map: dict = {}

    def run(name, fn, *args):
        try:
            results_map[name] = fn(*args)
        except Exception as e:
            print(f"[Search] {name} error: {e}")
            results_map[name] = []

    threads = [
        threading.Thread(target=run, args=("aviasales", _aviasales_search, origin, destination, date_from, price_max, limit)),
        threading.Thread(target=run, args=("ryanair",   _ryanair_search,   origin, destination, date_from, price_max, 5)),
        threading.Thread(target=run, args=("wizzair",   _wizzair_search,   origin, destination, date_from, price_max, 5)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=12)

    merged = _merge(
        results_map.get("aviasales", []),
        results_map.get("ryanair",   []),
        results_map.get("wizzair",   []),
    )

    # Fallback to fast-flights if nothing found
    if not merged:
        merged = _fast_flights_search(origin, destination, date_from, price_max, limit)

    if merged:
        _cache_set(cache_key, merged)

    print(f"[Search] {origin}→{destination}: {len(merged)} total results")
    return merged[:limit]


def search_one_way(origin, destination, date_from=None, date_to=None,
                   price_max=None, limit=5) -> list:
    return search_flights(origin, destination, date_from, date_to, price_max, limit)


def search_round_trip(origin: str, destination: str,
                      date_from: str = None, date_to: str = None,
                      return_from: str = None, return_to: str = None,
                      limit: int = 8) -> list:
    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    if not return_from:
        return_from = (datetime.now() + timedelta(days=7)).strftime("%d/%m/%Y")

    out = search_flights(origin, destination, date_from, limit=limit)
    ret = search_flights(destination, origin, return_from, limit=3)

    if not out:
        return []

    ret_price = ret[0]["price"] if ret else 0
    ret_date  = ret[0]["depart_at"][:5] if ret else ""
    results   = []
    for f in out[:limit]:
        combined = dict(f)
        if ret_price:
            combined["price"]     = f["price"] + ret_price
            combined["return_at"] = ret_date
            try:
                d1 = datetime.strptime(date_from,   "%d/%m/%Y").strftime("%Y-%m-%d")
                d2 = datetime.strptime(return_from, "%d/%m/%Y").strftime("%Y-%m-%d")
                combined["link"] = _google_flights_link(origin, destination, d1, d2)
            except Exception:
                pass
        results.append(combined)
    results.sort(key=lambda x: x["price"])
    return results[:limit]


def get_hot_deals(origins: list, price_max: int = 80, limit: int = 20) -> list:
    from config import POPULAR_DESTINATIONS
    destinations = [code for _, code in POPULAR_DESTINATIONS[:8]]
    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    all_deals = []

    for origin in origins[:3]:
        for dest in destinations[:5]:
            if origin == dest:
                continue
            try:
                flights = search_flights(origin, dest, date_from,
                                         price_max=price_max, limit=2)
                all_deals.extend(flights)
            except Exception as e:
                print(f"[HotDeals] {origin}→{dest}: {e}")
            time.sleep(0.1)

    all_deals.sort(key=lambda x: x["price"])
    return all_deals[:limit]


def get_cheapest_dates(origin: str, destination: str, months: int = 3) -> list:
    """Get cheapest flight per month for N months."""
    all_flights = []
    seen = set()
    now = datetime.now()

    for i in range(months):
        month_start = (now.replace(day=1) + timedelta(days=32 * i)).replace(day=1)
        d_from = max(now + timedelta(days=1), month_start).strftime("%d/%m/%Y")
        try:
            flights = _aviasales_search(origin, destination, d_from, limit=3)
            for f in flights:
                k = f"{f['depart_at']}:{f['price']}"
                if k not in seen:
                    seen.add(k)
                    all_flights.append(f)
        except Exception as e:
            print(f"[CheapDates] {i}: {e}")

    if not all_flights:
        # Fallback
        all_flights = _fast_flights_search(origin, destination,
                                           (now + timedelta(days=1)).strftime("%d/%m/%Y"),
                                           limit=5)

    all_flights.sort(key=lambda x: x["price"])
    return all_flights[:5]


def get_week_prices(origin: str, destination: str) -> list:
    """Get prices for each day of the next 7 days."""
    results = []
    now = datetime.now()
    for i in range(1, 8):
        day = now + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        d_from   = day.strftime("%d/%m/%Y")
        try:
            flights = _aviasales_search(origin, destination, d_from, limit=1)
            if flights:
                results.append({"date": day.strftime("%d.%m"), "weekday": _weekday(day), **flights[0]})
            else:
                results.append({"date": day.strftime("%d.%m"), "weekday": _weekday(day),
                                 "price": None, "link": _aviasales_link(origin, destination, date_str),
                                 "link_aviasales": _aviasales_link(origin, destination, date_str)})
        except Exception:
            results.append({"date": day.strftime("%d.%m"), "weekday": _weekday(day), "price": None,
                             "link": _aviasales_link(origin, destination, date_str),
                             "link_aviasales": _aviasales_link(origin, destination, date_str)})
    return results


def _weekday(dt: datetime) -> str:
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    return days[dt.weekday()]
