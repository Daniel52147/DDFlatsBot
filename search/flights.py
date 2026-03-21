"""
Flight search — 5 sources in parallel:
1. Aviasales open API (travelpayouts) — 3 months
2. Ryanair public API
3. Wizz Air public API
4. Skyscanner browse (no key)
5. fast-flights (Google Flights scraper)
Cache: 30 min per route.
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

# ── Cache ──────────────────────────────────────────────────────────────────────
_cache: dict = {}
_cache_lock = threading.Lock()
CACHE_TTL = 1800  # 30 min

def _cache_get(key):
    with _cache_lock:
        e = _cache.get(key)
        if e and time.time() - e["ts"] < CACHE_TTL:
            return e["data"]
    return None

def _cache_set(key, data):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time()}

# ── Maps ───────────────────────────────────────────────────────────────────────
CITY_NAMES = {
    "WAW":"Варшава",  "KRK":"Краков",   "WRO":"Вроцлав",  "GDN":"Гданьск",
    "KTW":"Катовице", "POZ":"Познань",  "SZZ":"Щецин",    "LUZ":"Люблин",
    "BCN":"Барселона","MAD":"Мадрид",   "TFS":"Тенерифе", "PMI":"Майорка",
    "AGP":"Малага",   "ALC":"Аликанте", "IBZ":"Ибица",    "SVQ":"Севилья",
    "FCO":"Рим",      "MXP":"Милан",    "NAP":"Неаполь",  "VCE":"Венеция",
    "BLQ":"Болонья",  "PSA":"Пиза",     "CTA":"Катания",  "PMO":"Палермо",
    "LTN":"Лондон",   "LHR":"Лондон",   "STN":"Лондон",   "MAN":"Манчестер",
    "BHX":"Бирмингем","EDI":"Эдинбург",
    "CDG":"Париж",    "ORY":"Париж",    "NCE":"Ницца",    "LYS":"Лион",
    "DXB":"Дубай",    "AUH":"Абу-Даби", "SHJ":"Шарджа",
    "AMS":"Амстердам","LIS":"Лиссабон", "ATH":"Афины",    "OPO":"Порту",
    "PRG":"Прага",    "BUD":"Будапешт", "VIE":"Вена",     "BTS":"Братислава",
    "BER":"Берлин",   "MUC":"Мюнхен",   "FRA":"Франкфурт","HAM":"Гамбург",
    "DUS":"Дюссельдорф","STR":"Штутгарт","CGN":"Кёльн",
    "BKK":"Бангкок",  "HKT":"Пхукет",   "CMB":"Коломбо",  "KUL":"Куала-Лумпур",
    "SIN":"Сингапур", "HAN":"Ханой",    "SGN":"Хошимин",
    "JFK":"Нью-Йорк", "LAX":"Лос-Анджелес","MIA":"Майами","ORD":"Чикаго",
    "IST":"Стамбул",  "SAW":"Стамбул",  "ADB":"Измир",    "AYT":"Анталья",
    "TLV":"Тель-Авив","CAI":"Каир",     "HRG":"Хургада",  "SSH":"Шарм-эш-Шейх",
    "SKG":"Салоники", "HER":"Ираклион", "RHO":"Родос",    "CFU":"Корфу",
    "DBV":"Дубровник","SPU":"Сплит",    "ZAD":"Задар",    "PUY":"Пула",
    "OTP":"Бухарест", "SOF":"София",    "OHD":"Охрид",    "SKP":"Скопье",
    "RIX":"Рига",     "TLL":"Таллин",   "VNO":"Вильнюс",
    "KBP":"Киев",     "LWO":"Львов",
    "GRO":"Жирона",   "REU":"Реус",     "VLC":"Валенсия", "BIO":"Бильбао",
    "MRS":"Марсель",  "BOD":"Бордо",    "TLS":"Тулуза",
    "BRU":"Брюссель", "GVA":"Женева",   "ZRH":"Цюрих",    "CPH":"Копенгаген",
    "OSL":"Осло",     "ARN":"Стокгольм","HEL":"Хельсинки",
    "DUB":"Дублин",   "BFS":"Белфаст",
    "LCA":"Ларнака",  "PFO":"Пафос",    "RKV":"Рейкьявик",
    "CMN":"Касабланка","RAK":"Марракеш", "TUN":"Тунис",
    "GPA":"Патры",    "KGS":"Кос",      "JMK":"Миконос",  "JTR":"Санторини",
}

AIRLINE_NAMES = {
    "FR":"Ryanair",   "W6":"Wizz Air",  "VY":"Vueling",   "U2":"easyJet",
    "LO":"LOT",       "LH":"Lufthansa", "BA":"British Airways","AF":"Air France",
    "KL":"KLM",       "TK":"Turkish Airlines","EK":"Emirates","QR":"Qatar Airways",
    "TP":"TAP Portugal","PS":"Ukraine Intl","SN":"Brussels Airlines",
    "OS":"Austrian",  "SK":"SAS",       "AY":"Finnair",   "IB":"Iberia",
    "BT":"airBaltic", "PC":"Pegasus",   "XQ":"SunExpress","HV":"Transavia",
    "TO":"Transavia France","V7":"Volotea","FR ":"Ryanair",
    "4U":"Germanwings","DE":"Condor",   "X3":"TUIfly",    "EN":"Air Dolomiti",
}

# ── Link builders ──────────────────────────────────────────────────────────────

def _aviasales_link(origin, dest, date_str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m")
    except Exception:
        d = "0101"
    return f"https://www.aviasales.ru/search/{origin}{d}{dest}1"

def _google_link(origin, dest, date_str, ret=None):
    q = f"Flights from {origin} to {dest} on {date_str}"
    if ret:
        q += f" returning {ret}"
    return f"https://www.google.com/travel/flights?q={urllib.parse.quote(q)}"

def _airline_link(code, origin, dest, date_str):
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
    if c == "PC":
        return f"https://www.flypgs.com/en/cheap-flights/{o.lower()}-{d.lower()}"
    return _google_link(origin, dest, date_str)

def _make(origin, dest, price, code, dep, arr, dur_min, stops, date_iso):
    name = AIRLINE_NAMES.get(code.upper(), code) if code else "?"
    s = "прямой" if stops == 0 else f"{stops} пересадка" if stops == 1 else f"{stops} пересадки"
    dur = ""
    if dur_min:
        h, m = divmod(int(dur_min), 60)
        dur = f"{h}ч {m}м" if m else f"{h}ч"
    return {
        "origin": origin, "destination": dest,
        "origin_city": CITY_NAMES.get(origin, origin),
        "dest_city":   CITY_NAMES.get(dest, dest),
        "price": int(price), "currency": "EUR",
        "airline": name, "airline_code": code.upper() if code else "",
        "depart_at": dep, "arrive_at": arr,
        "duration": dur, "stops": s,
        "link": _airline_link(code, origin, dest, date_iso),
        "link_aviasales": _aviasales_link(origin, dest, date_iso),
    }

# ── Source 1: Aviasales — 3 months ────────────────────────────────────────────

def _aviasales(origin, dest, date_from, price_max=None, limit=20):
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d0 = datetime.now() + timedelta(days=1)

    results = []
    for offset in range(3):  # 3 months
        month = (d0.replace(day=1) + timedelta(days=32*offset)).replace(day=1).strftime("%Y-%m")
        url = (f"https://api.travelpayouts.com/v1/prices/cheap"
               f"?origin={origin}&destination={dest}"
               f"&depart_date={month}&one_way=true&currency=eur&limit=30")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SkyCheapBot/2.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            if not data.get("success"):
                continue
            for _, item in data.get("data", {}).get(dest, {}).items():
                p = item.get("price", 0)
                if not p or (price_max and p > price_max):
                    continue
                dep_raw = item.get("departure_at", "")
                try:
                    dt = datetime.fromisoformat(dep_raw[:16])
                    dep = dt.strftime("%d.%m %H:%M")
                    iso = dt.strftime("%Y-%m-%d")
                except Exception:
                    dep = dep_raw[:10]; iso = dep_raw[:10] or month+"-01"
                results.append(_make(origin, dest, p, item.get("airline",""),
                                     dep, "", item.get("duration",0),
                                     item.get("transfers",0), iso))
        except Exception as e:
            print(f"[Aviasales] {origin}→{dest} {month}: {e}")

    results.sort(key=lambda x: x["price"])
    seen, out = set(), []
    for f in results:
        k = f"{f['depart_at']}:{f['price']}"
        if k not in seen:
            seen.add(k); out.append(f)
    print(f"[Aviasales] {origin}→{dest}: {len(out)}")
    return out[:limit]

# ── Source 2: Aviasales calendar — cheapest per day ───────────────────────────

def _aviasales_calendar(origin, dest, date_from, price_max=None, limit=20):
    """Uses /v2/prices/month-matrix — one price per day for 2 months."""
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d0 = datetime.now() + timedelta(days=1)

    results = []
    for offset in range(2):
        month = (d0.replace(day=1) + timedelta(days=32*offset)).replace(day=1).strftime("%Y-%m")
        url = (f"https://api.travelpayouts.com/v2/prices/month-matrix"
               f"?origin={origin}&destination={dest}"
               f"&month={month}&currency=eur&show_to_affiliates=true")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SkyCheapBot/2.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            for item in data.get("data", []):
                p = item.get("price", 0)
                if not p or (price_max and p > price_max):
                    continue
                dep_raw = item.get("depart_date", "")
                try:
                    dt = datetime.fromisoformat(dep_raw[:10])
                    dep = dt.strftime("%d.%m")
                    iso = dt.strftime("%Y-%m-%d")
                except Exception:
                    dep = dep_raw[:10]; iso = dep_raw[:10]
                results.append(_make(origin, dest, p, "",
                                     dep, "", 0, 0, iso))
        except Exception as e:
            print(f"[AviasalesCal] {origin}→{dest} {month}: {e}")

    results.sort(key=lambda x: x["price"])
    seen, out = set(), []
    for f in results:
        k = f"{f['depart_at']}:{f['price']}"
        if k not in seen:
            seen.add(k); out.append(f)
    print(f"[AviasalesCal] {origin}→{dest}: {len(out)}")
    return out[:limit]

# ── Source 3: Ryanair ─────────────────────────────────────────────────────────

def _ryanair(origin, dest, date_from, price_max=None, limit=10):
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
        d1 = d0 + timedelta(days=90)
    except Exception:
        return []
    url = (f"https://www.ryanair.com/api/farfnd/v4/oneWayFares"
           f"?departureAirportIataCode={origin}&arrivalAirportIataCode={dest}"
           f"&outboundDepartureDateFrom={d0.strftime('%Y-%m-%d')}"
           f"&outboundDepartureDateTo={d1.strftime('%Y-%m-%d')}"
           f"&currency=EUR&priceValueTo=500&limit=20")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        out = []
        for fare in data.get("fares", []):
            p = fare.get("price", {}).get("value", 0)
            if not p or (price_max and p > price_max):
                continue
            ob = fare.get("outbound", {})
            dep_raw = ob.get("departureDate", "")
            arr_raw = ob.get("arrivalDate", "")
            try:
                dt_d = datetime.fromisoformat(dep_raw[:16])
                dt_a = datetime.fromisoformat(arr_raw[:16])
                dep = dt_d.strftime("%d.%m %H:%M")
                arr = dt_a.strftime("%d.%m %H:%M")
                iso = dt_d.strftime("%Y-%m-%d")
                dur = int((dt_a - dt_d).total_seconds() / 60)
            except Exception:
                dep = dep_raw[:10]; arr = ""; iso = dep_raw[:10]; dur = 0
            out.append(_make(origin, dest, p, "FR", dep, arr, dur, 0, iso))
        out.sort(key=lambda x: x["price"])
        print(f"[Ryanair] {origin}→{dest}: {len(out)}")
        return out[:limit]
    except Exception as e:
        print(f"[Ryanair] {origin}→{dest}: {e}")
        return []

# ── Source 4: Wizz Air ────────────────────────────────────────────────────────

def _wizzair(origin, dest, date_from, price_max=None, limit=10):
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
        d1 = d0 + timedelta(days=90)
    except Exception:
        return []
    url = (f"https://be.wizzair.com/14.3.0/Api/search/timetable"
           f"?departureStation={origin}&arrivalStation={dest}"
           f"&from={d0.strftime('%Y-%m-%d')}&to={d1.strftime('%Y-%m-%d')}"
           f"&priceType=regular&adultCount=1&childCount=0&infantCount=0")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json",
               "x-requestedwith": "XMLHttpRequest"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        out = []
        for day in data.get("outboundFlights", []):
            for fl in day.get("departures", []):
                p = fl.get("price", {}).get("amount", 0)
                if not p or (price_max and p > price_max):
                    continue
                dep_raw = fl.get("departureDateTime", "")
                arr_raw = fl.get("arrivalDateTime", "")
                try:
                    dt_d = datetime.fromisoformat(dep_raw[:16])
                    dt_a = datetime.fromisoformat(arr_raw[:16])
                    dep = dt_d.strftime("%d.%m %H:%M")
                    arr = dt_a.strftime("%d.%m %H:%M")
                    iso = dt_d.strftime("%Y-%m-%d")
                    dur = int((dt_a - dt_d).total_seconds() / 60)
                except Exception:
                    dep = dep_raw[:10]; arr = ""; iso = dep_raw[:10]; dur = 0
                out.append(_make(origin, dest, p, "W6", dep, arr, dur, 0, iso))
        out.sort(key=lambda x: x["price"])
        print(f"[Wizz] {origin}→{dest}: {len(out)}")
        return out[:limit]
    except Exception as e:
        print(f"[Wizz] {origin}→{dest}: {e}")
        return []

# ── Source 5: fast-flights (Google Flights) ───────────────────────────────────

def _fmt_dt(sdt):
    try:
        y, m, d = sdt.date; h, mi = sdt.time
        return f"{d:02d}.{m:02d} {h:02d}:{mi:02d}"
    except Exception:
        return ""

def _fast_flights(origin, dest, date_from, price_max=None, limit=10):
    if not FAST_FLIGHTS_OK:
        return []
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d0 = datetime.now() + timedelta(days=1)

    out, seen = [], set()
    # Try 6 dates spread over 3 months
    for i in [0, 2, 4, 6, 8, 10]:
        date_str = (d0 + timedelta(weeks=i)).strftime("%Y-%m-%d")
        try:
            q = create_query(
                flights=[FlightQuery(date=date_str, from_airport=origin, to_airport=dest)],
                trip="one-way", seat="economy",
                passengers=Passengers(adults=1), currency="EUR",
            )
            for item in _gf(q):
                if not item.flights:
                    continue
                codes = list(item.airlines) if item.airlines else []
                code  = codes[0] if codes else ""
                fl0   = item.flights[0]; fln = item.flights[-1]
                dep   = _fmt_dt(fl0.departure); arr = _fmt_dt(fln.arrival)
                dur   = sum(getattr(f, "duration", 0) for f in item.flights)
                stops = len(item.flights) - 1
                p     = item.price
                if price_max and p > price_max:
                    continue
                k = f"{dep}:{p}"
                if k not in seen:
                    seen.add(k)
                    out.append(_make(origin, dest, p, code, dep, arr, dur, stops, date_str))
        except Exception as e:
            print(f"[FF] {origin}→{dest} {date_str}: {e}")
    out.sort(key=lambda x: x["price"])
    print(f"[FastFlights] {origin}→{dest}: {len(out)}")
    return out[:limit]

# ── Merge ──────────────────────────────────────────────────────────────────────

def _merge(*lists):
    seen, out = set(), []
    for lst in lists:
        for f in lst:
            k = f"{f['depart_at']}:{f['airline_code']}:{f['price']}"
            if k not in seen:
                seen.add(k); out.append(f)
    out.sort(key=lambda x: x["price"])
    return out

# ── Public API ─────────────────────────────────────────────────────────────────

def search_flights(origin, destination, date_from=None, date_to=None,
                   price_max=None, limit=15, **kwargs):
    if not date_from:
        date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")

    cache_key = f"{origin}:{destination}:{date_from}:{price_max}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached[:limit]

    res: dict = {}

    def run(name, fn, *args):
        try:
            res[name] = fn(*args)
        except Exception as e:
            print(f"[Search] {name}: {e}"); res[name] = []

    threads = [
        threading.Thread(target=run, args=("av1",  _aviasales,          origin, destination, date_from, price_max, 20)),
        threading.Thread(target=run, args=("av2",  _aviasales_calendar, origin, destination, date_from, price_max, 20)),
        threading.Thread(target=run, args=("ry",   _ryanair,            origin, destination, date_from, price_max, 10)),
        threading.Thread(target=run, args=("wz",   _wizzair,            origin, destination, date_from, price_max, 10)),
        threading.Thread(target=run, args=("ff",   _fast_flights,       origin, destination, date_from, price_max, 10)),
    ]
    for t in threads: t.start()
    for t in threads: t.join(timeout=15)

    merged = _merge(res.get("av1",[]), res.get("av2",[]),
                    res.get("ry",[]),  res.get("wz",[]),
                    res.get("ff",[]))

    print(f"[Search] {origin}→{destination}: {len(merged)} total")
    if merged:
        _cache_set(cache_key, merged)
    return merged[:limit]


def search_one_way(origin, destination, date_from=None, date_to=None,
                   price_max=None, limit=5):
    return search_flights(origin, destination, date_from, date_to, price_max, limit)


def search_round_trip(origin, destination, date_from=None, date_to=None,
                      return_from=None, return_to=None, limit=8):
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
    results = []
    for f in out[:limit]:
        c = dict(f)
        if ret_price:
            c["price"]     = f["price"] + ret_price
            c["return_at"] = ret_date
            try:
                d1 = datetime.strptime(date_from,   "%d/%m/%Y").strftime("%Y-%m-%d")
                d2 = datetime.strptime(return_from, "%d/%m/%Y").strftime("%Y-%m-%d")
                c["link"] = _google_link(origin, destination, d1, d2)
            except Exception:
                pass
        results.append(c)
    results.sort(key=lambda x: x["price"])
    return results[:limit]


def get_hot_deals(origins, price_max=80, limit=30):
    from config import POPULAR_DESTINATIONS
    dests     = [code for _, code in POPULAR_DESTINATIONS]  # all destinations
    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    all_deals = []

    # Run all origin×dest combos in parallel threads
    lock = threading.Lock()

    def fetch(org, dst):
        if org == dst:
            return
        try:
            flights = search_flights(org, dst, date_from, price_max=price_max, limit=3)
            with lock:
                all_deals.extend(flights)
        except Exception as e:
            print(f"[HotDeals] {org}→{dst}: {e}")

    threads = []
    for org in origins[:4]:
        for dst in dests[:8]:
            t = threading.Thread(target=fetch, args=(org, dst))
            threads.append(t)
            t.start()
    for t in threads:
        t.join(timeout=20)

    all_deals.sort(key=lambda x: x["price"])
    # Deduplicate
    seen, out = set(), []
    for f in all_deals:
        k = f"{f['origin']}:{f['destination']}:{f['price']}"
        if k not in seen:
            seen.add(k); out.append(f)
    return out[:limit]


def get_cheapest_dates(origin, destination, months=3):
    results = _aviasales_calendar(origin, destination,
                                  (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y"),
                                  limit=30)
    if not results:
        results = _aviasales(origin, destination,
                             (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y"),
                             limit=15)
    if not results and FAST_FLIGHTS_OK:
        results = _fast_flights(origin, destination,
                                (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y"),
                                limit=10)
    results.sort(key=lambda x: x["price"])
    return results[:5]


def get_week_prices(origin, destination):
    """Price for each of next 7 days."""
    out = []
    days_ru = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    now = datetime.now()
    for i in range(1, 8):
        day = now + timedelta(days=i)
        iso = day.strftime("%Y-%m-%d")
        d_from = day.strftime("%d/%m/%Y")
        flights = _aviasales(origin, destination, d_from, limit=1)
        if not flights:
            flights = _ryanair(origin, destination, d_from, limit=1)
        if not flights:
            flights = _wizzair(origin, destination, d_from, limit=1)
        entry = {
            "date": day.strftime("%d.%m"),
            "weekday": days_ru[day.weekday()],
            "price": flights[0]["price"] if flights else None,
            "link": flights[0]["link"] if flights else _google_link(origin, destination, iso),
            "link_aviasales": _aviasales_link(origin, destination, iso),
        }
        out.append(entry)
    return out
