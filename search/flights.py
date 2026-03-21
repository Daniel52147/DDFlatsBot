"""
Flight search — 6 источников параллельно:
1. Kiwi.com public API (без ключа) — любые маршруты, с пересадками
2. Ryanair farfnd API — прямые рейсы FR
3. Ryanair calendar — дешёвые даты FR
4. Wizz Air timetable — прямые рейсы W6
5. fast-flights (Google Flights scraper)
6. Aviasales open data (кэшированные цены)
Fallback: всегда возвращаем ссылки даже если цен нет.
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
CACHE_TTL = 1800

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
    "WMI":"Варшава-Модлин",
    "BCN":"Барселона","MAD":"Мадрид",   "TFS":"Тенерифе", "PMI":"Майорка",
    "AGP":"Малага",   "ALC":"Аликанте", "IBZ":"Ибица",    "SVQ":"Севилья",
    "GRO":"Жирона",   "REU":"Реус",     "VLC":"Валенсия", "BIO":"Бильбао",
    "FCO":"Рим",      "MXP":"Милан",    "NAP":"Неаполь",  "VCE":"Венеция",
    "BLQ":"Болонья",  "PSA":"Пиза",     "CTA":"Катания",  "PMO":"Палермо",
    "BRI":"Бари",     "TRN":"Турин",    "GOA":"Генуя",    "TSF":"Тревизо",
    "LTN":"Лондон",   "LHR":"Лондон",   "STN":"Лондон",   "MAN":"Манчестер",
    "BHX":"Бирмингем","EDI":"Эдинбург", "BRS":"Бристоль",
    "CDG":"Париж",    "ORY":"Париж",    "NCE":"Ницца",    "LYS":"Лион",
    "MRS":"Марсель",  "BOD":"Бордо",    "TLS":"Тулуза",
    "DXB":"Дубай",    "AUH":"Абу-Даби", "SHJ":"Шарджа",   "DOH":"Доха",
    "AMS":"Амстердам","LIS":"Лиссабон", "OPO":"Порту",
    "ATH":"Афины",    "SKG":"Салоники", "HER":"Ираклион", "RHO":"Родос",
    "CFU":"Корфу",    "KGS":"Кос",      "JMK":"Миконос",  "JTR":"Санторини",
    "CHQ":"Ханья",    "ZTH":"Закинф",
    "PRG":"Прага",    "BUD":"Будапешт", "VIE":"Вена",     "BTS":"Братислава",
    "BER":"Берлин",   "MUC":"Мюнхен",   "FRA":"Франкфурт","HAM":"Гамбург",
    "DUS":"Дюссельдорф","STR":"Штутгарт","CGN":"Кёльн",
    "BRU":"Брюссель", "GVA":"Женева",   "ZRH":"Цюрих",
    "CPH":"Копенгаген","OSL":"Осло",    "ARN":"Стокгольм","HEL":"Хельсинки",
    "DUB":"Дублин",   "LCA":"Ларнака",  "PFO":"Пафос",
    "IST":"Стамбул",  "SAW":"Стамбул",  "ADB":"Измир",    "AYT":"Анталья",
    "TLV":"Тель-Авив","CAI":"Каир",     "HRG":"Хургада",  "SSH":"Шарм-эш-Шейх",
    "CMN":"Касабланка","RAK":"Марракеш", "TUN":"Тунис",
    "BKK":"Бангкок",  "HKT":"Пхукет",   "CMB":"Коломбо",  "KUL":"Куала-Лумпур",
    "SIN":"Сингапур", "HAN":"Ханой",    "SGN":"Хошимин",
    "JFK":"Нью-Йорк", "LAX":"Лос-Анджелес","MIA":"Майами","ORD":"Чикаго",
    "DBV":"Дубровник","SPU":"Сплит",    "ZAD":"Задар",    "PUY":"Пула",
    "OTP":"Бухарест", "SOF":"София",    "SKP":"Скопье",
    "RIX":"Рига",     "TLL":"Таллин",   "VNO":"Вильнюс",
    "KBP":"Киев",     "LWO":"Львов",
}

AIRLINE_NAMES = {
    "FR":"Ryanair",   "W6":"Wizz Air",  "VY":"Vueling",   "U2":"easyJet",
    "LO":"LOT",       "LH":"Lufthansa", "BA":"British Airways","AF":"Air France",
    "KL":"KLM",       "TK":"Turkish Airlines","EK":"Emirates","QR":"Qatar Airways",
    "TP":"TAP Portugal","SN":"Brussels Airlines","OS":"Austrian",
    "SK":"SAS",       "AY":"Finnair",   "IB":"Iberia",    "BT":"airBaltic",
    "PC":"Pegasus",   "XQ":"SunExpress","HV":"Transavia", "TO":"Transavia France",
    "V7":"Volotea",   "DY":"Norwegian", "D8":"Norwegian", "DE":"Condor",
    "FZ":"flydubai",  "G9":"Air Arabia","WY":"Oman Air",  "GF":"Gulf Air",
    "MS":"EgyptAir",  "RJ":"Royal Jordanian","ET":"Ethiopian","KQ":"Kenya Airways",
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

def _kiwi_link(origin, dest, date_str, ret=None):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        d_to = (dt + timedelta(days=90)).strftime("%Y-%m-%d")
    except Exception:
        d_to = date_str
    base = f"https://www.kiwi.com/en/search/results/{origin}/{dest}/{date_str}/{d_to}"
    if ret:
        base += f"/{ret}"
    return base

def _airline_link(code, origin, dest, date_str):
    c = code.upper() if code else ""
    o, d = origin.upper(), dest.upper()
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        d_fmt = dt.strftime("%Y-%m-%d")
    except Exception:
        d_fmt = date_str
    if c == "FR":
        return f"https://www.ryanair.com/en/cheap-flights/{o.lower()}-to-{d.lower()}/"
    if c == "W6":
        return f"https://wizzair.com/#/booking/select-flight/{o}/{d}/{d_fmt}/null/1/0/0/null"
    if c == "LO":
        return f"https://www.lot.com/en/en/flight-search#/results?from={o}&to={d}&departure={d_fmt}&adults=1&tripType=ONE_WAY"
    if c == "U2":
        return f"https://www.easyjet.com/en/cheap-flights/{o.lower()}-{d.lower()}"
    if c == "LH":
        return f"https://www.lufthansa.com/de/en/flight-search?origin={o}&destination={d}&outboundDate={d_fmt}&adults=1"
    if c == "TK":
        return f"https://www.turkishairlines.com/en-int/flights/find-flights/?origin={o}&destination={d}&departureDate={d_fmt}&adult=1"
    if c == "EK":
        return f"https://www.emirates.com/english/book/flights/?origin={o}&destination={d}&departureDate={d_fmt}&adults=1"
    if c == "QR":
        return f"https://www.qatarairways.com/en/flights.html?from={o}&to={d}&depart={d_fmt}&adult=1"
    if c == "KL":
        return f"https://www.klm.com/search/en/results?origin={o}&destination={d}&outboundDate={d_fmt}&adults=1"
    if c == "VY":
        return f"https://www.vueling.com/en/book-your-flights/search?dep={o}&arr={d}&depDate={d_fmt}&pax=1"
    if c == "PC":
        return f"https://www.flypgs.com/en/cheap-flights/{o.lower()}-{d.lower()}"
    if c in ("DY", "D8"):
        return f"https://www.norwegian.com/en/booking/flight-tickets/?D1={o}&A1={d}&DD1={d_fmt}&ADT=1&TYP=S"
    if c == "BT":
        return f"https://airbaltic.com/en/search-results?from={o}&to={d}&date={d_fmt}&adult=1"
    if c == "FZ":
        return f"https://www.flydubai.com/en/booking/search?from={o}&to={d}&date={d_fmt}&adults=1"
    return _aviasales_link(origin, dest, d_fmt)

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


# ── Source 1: Kiwi.com public API (без ключа) ─────────────────────────────────

def _kiwi(origin, dest, date_from, price_max=None, limit=20, max_stops=2):
    """
    Kiwi.com public search — работает для ЛЮБЫХ маршрутов включая дальние.
    Не требует API ключа для базовых запросов.
    """
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
        d1 = d0 + timedelta(days=90)
    except Exception:
        d0 = datetime.now() + timedelta(days=1)
        d1 = d0 + timedelta(days=90)

    url = "https://api.tequila.kiwi.com/v2/search"
    params = {
        "fly_from": origin,
        "fly_to": dest,
        "date_from": d0.strftime("%d/%m/%Y"),
        "date_to": d1.strftime("%d/%m/%Y"),
        "flight_type": "oneway",
        "adults": 1,
        "limit": 30,
        "sort": "price",
        "curr": "EUR",
        "max_stopovers": max_stops,
        "partner": "picky",
    }
    if price_max:
        params["price_to"] = price_max

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    # Try with and without apikey header
    for apikey in [None, "public"]:
        try:
            if apikey:
                headers["apikey"] = apikey
            qs = urllib.parse.urlencode(params)
            req = urllib.request.Request(f"{url}?{qs}", headers=headers)
            with urllib.request.urlopen(req, timeout=12) as r:
                data = json.loads(r.read())
            out = []
            for f in data.get("data", []):
                p = int(f.get("price", 0))
                if not p or (price_max and p > price_max):
                    continue
                # Parse departure/arrival
                dep_ts = f.get("dTime") or f.get("local_departure")
                arr_ts = f.get("aTime") or f.get("local_arrival")
                try:
                    if isinstance(dep_ts, (int, float)):
                        dt_d = datetime.fromtimestamp(dep_ts)
                    else:
                        dt_d = datetime.fromisoformat(str(dep_ts)[:16])
                    dep = dt_d.strftime("%d.%m %H:%M")
                    iso = dt_d.strftime("%Y-%m-%d")
                except Exception:
                    dep = ""; iso = d0.strftime("%Y-%m-%d")
                try:
                    if isinstance(arr_ts, (int, float)):
                        dt_a = datetime.fromtimestamp(arr_ts)
                    else:
                        dt_a = datetime.fromisoformat(str(arr_ts)[:16])
                    arr = dt_a.strftime("%d.%m %H:%M")
                except Exception:
                    arr = ""
                # Airlines
                airlines = []
                for route in f.get("route", []):
                    al = route.get("airline") or route.get("operating_carrier", "")
                    if al and al not in airlines:
                        airlines.append(al)
                code = airlines[0] if airlines else f.get("airlines", [""])[0] if f.get("airlines") else ""
                # Duration
                dur_raw = f.get("duration", {})
                dur_min = dur_raw.get("total", 0) if isinstance(dur_raw, dict) else 0
                stops = max(0, len(f.get("route", [])) - 1)
                # Deep link
                deep = f.get("deep_link", "")
                flight = _make(origin, dest, p, code, dep, arr, dur_min, stops, iso)
                if deep and deep.startswith("http"):
                    flight["link"] = deep
                out.append(flight)
            out.sort(key=lambda x: x["price"])
            print(f"[Kiwi] {origin}→{dest}: {len(out)}")
            return out[:limit]
        except Exception as e:
            print(f"[Kiwi] {origin}→{dest} (apikey={apikey}): {e}")
    return []


# ── Source 2: Ryanair farfnd API ──────────────────────────────────────────────

def _ryanair(origin, dest, date_from, price_max=None, limit=15):
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
        d1 = d0 + timedelta(days=120)
    except Exception:
        return []
    url = (f"https://www.ryanair.com/api/farfnd/v4/oneWayFares"
           f"?departureAirportIataCode={origin}&arrivalAirportIataCode={dest}"
           f"&outboundDepartureDateFrom={d0.strftime('%Y-%m-%d')}"
           f"&outboundDepartureDateTo={d1.strftime('%Y-%m-%d')}"
           f"&currency=EUR&priceValueTo={price_max or 500}&limit=30")
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
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


# ── Source 3: Wizz Air timetable ──────────────────────────────────────────────

def _wizzair(origin, dest, date_from, price_max=None, limit=15):
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
        d1 = d0 + timedelta(days=120)
    except Exception:
        return []
    url = (f"https://be.wizzair.com/14.3.0/Api/search/timetable"
           f"?departureStation={origin}&arrivalStation={dest}"
           f"&from={d0.strftime('%Y-%m-%d')}&to={d1.strftime('%Y-%m-%d')}"
           f"&priceType=regular&adultCount=1&childCount=0&infantCount=0")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "x-requestedwith": "XMLHttpRequest",
        "Referer": "https://wizzair.com/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
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


# ── Source 4: fast-flights (Google Flights) ───────────────────────────────────

def _fmt_dt(sdt):
    try:
        y, m, d = sdt.date; h, mi = sdt.time
        return f"{d:02d}.{m:02d} {h:02d}:{mi:02d}"
    except Exception:
        return ""

def _fast_flights(origin, dest, date_from, price_max=None, limit=15):
    if not FAST_FLIGHTS_OK:
        return []
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d0 = datetime.now() + timedelta(days=1)

    out, seen = [], set()
    for i in [0, 1, 2, 4, 6, 8, 10, 14]:
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
                k = f"{dep}:{p}:{code}"
                if k not in seen:
                    seen.add(k)
                    out.append(_make(origin, dest, p, code, dep, arr, dur, stops, date_str))
        except Exception as e:
            print(f"[FF] {origin}→{dest} {date_str}: {e}")
    out.sort(key=lambda x: x["price"])
    print(f"[FastFlights] {origin}→{dest}: {len(out)}")
    return out[:limit]


# ── Source 5: Aviasales open data ─────────────────────────────────────────────

def _aviasales_open(origin, dest, date_from, price_max=None, limit=15):
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
    except Exception:
        d0 = datetime.now() + timedelta(days=1)

    results = []
    for offset in range(3):
        month = (d0.replace(day=1) + timedelta(days=32 * offset)).replace(day=1).strftime("%Y-%m")
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
                    dep = dep_raw[:10]; iso = month + "-01"
                results.append(_make(origin, dest, p, item.get("airline", ""),
                                     dep, "", item.get("duration", 0),
                                     item.get("transfers", 0), iso))
        except Exception as e:
            print(f"[AviasalesOpen] {origin}→{dest} {month}: {e}")

    results.sort(key=lambda x: x["price"])
    seen, out = set(), []
    for f in results:
        k = f"{f['depart_at']}:{f['price']}"
        if k not in seen:
            seen.add(k); out.append(f)
    print(f"[AviasalesOpen] {origin}→{dest}: {len(out)}")
    return out[:limit]


# ── Merge & deduplicate ────────────────────────────────────────────────────────

def _merge(*lists):
    seen, out = set(), []
    for lst in lists:
        for f in lst:
            k = f"{f['depart_at']}:{f['airline_code']}:{f['price']}"
            if k not in seen:
                seen.add(k); out.append(f)
    out.sort(key=lambda x: x["price"])
    return out


def _fallback_links(origin, dest, date_from):
    """
    Когда реальных цен нет — возвращаем карточки со ссылками на поиск.
    Пользователь видит варианты и может кликнуть чтобы найти цену.
    """
    try:
        d0 = datetime.strptime(date_from, "%d/%m/%Y")
        iso = d0.strftime("%Y-%m-%d")
    except Exception:
        iso = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    dest_city = CITY_NAMES.get(dest, dest)
    origin_city = CITY_NAMES.get(origin, origin)

    # Предлагаем несколько дат и авиакомпаний
    results = []
    for weeks_offset, airline_code, airline_name in [
        (1, "EK", "Emirates"),
        (2, "TK", "Turkish Airlines"),
        (3, "LH", "Lufthansa"),
        (4, "QR", "Qatar Airways"),
        (6, "KL", "KLM"),
    ]:
        dt = d0 + timedelta(weeks=weeks_offset)
        iso_d = dt.strftime("%Y-%m-%d")
        dep = dt.strftime("%d.%m")
        results.append({
            "origin": origin, "destination": dest,
            "origin_city": origin_city, "dest_city": dest_city,
            "price": 0, "currency": "EUR",
            "airline": airline_name, "airline_code": airline_code,
            "depart_at": dep, "arrive_at": "",
            "duration": "", "stops": "с пересадкой",
            "link": _airline_link(airline_code, origin, dest, iso_d),
            "link_aviasales": _aviasales_link(origin, dest, iso_d),
            "_is_fallback": True,
        })
    return results


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
        threading.Thread(target=run, args=("kw",  _kiwi,           origin, destination, date_from, price_max, 20)),
        threading.Thread(target=run, args=("ry",  _ryanair,        origin, destination, date_from, price_max, 15)),
        threading.Thread(target=run, args=("wz",  _wizzair,        origin, destination, date_from, price_max, 15)),
        threading.Thread(target=run, args=("av",  _aviasales_open, origin, destination, date_from, price_max, 15)),
        threading.Thread(target=run, args=("ff",  _fast_flights,   origin, destination, date_from, price_max, 15)),
    ]
    for t in threads: t.start()
    for t in threads: t.join(timeout=20)

    merged = _merge(
        res.get("kw", []), res.get("ry", []),
        res.get("wz", []), res.get("av", []),
        res.get("ff", []),
    )

    print(f"[Search] {origin}→{destination}: {len(merged)} total")

    # Если ничего не нашли — возвращаем fallback ссылки
    if not merged:
        merged = _fallback_links(origin, destination, date_from)
        print(f"[Search] {origin}→{destination}: using fallback links")

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

    # Параллельно ищем туда и обратно
    out_res, ret_res = [], []

    def _fetch_out():
        nonlocal out_res
        out_res = search_flights(origin, destination, date_from, limit=limit)

    def _fetch_ret():
        nonlocal ret_res
        ret_res = search_flights(destination, origin, return_from, limit=5)

    t1 = threading.Thread(target=_fetch_out)
    t2 = threading.Thread(target=_fetch_ret)
    t1.start(); t2.start()
    t1.join(timeout=25); t2.join(timeout=25)

    if not out_res:
        return []

    ret_price = ret_res[0]["price"] if ret_res and ret_res[0].get("price") else 0
    ret_date  = ret_res[0]["depart_at"][:5] if ret_res else ""

    results = []
    for f in out_res[:limit]:
        c = dict(f)
        if ret_price:
            c["price"]     = f["price"] + ret_price
            c["return_at"] = ret_date
        try:
            d1 = datetime.strptime(date_from,   "%d/%m/%Y").strftime("%Y-%m-%d")
            d2 = datetime.strptime(return_from, "%d/%m/%Y").strftime("%Y-%m-%d")
            c["link"] = _google_link(origin, destination, d1, d2)
            c["link_aviasales"] = _aviasales_link(origin, destination, d1)
        except Exception:
            pass
        results.append(c)
    results.sort(key=lambda x: x["price"])
    return results[:limit]


def get_hot_deals(origins, price_max=80, limit=40):
    from config import POPULAR_DESTINATIONS
    dests     = [code for _, code in POPULAR_DESTINATIONS]
    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    all_deals = []
    lock = threading.Lock()

    def fetch(org, dst):
        if org == dst:
            return
        try:
            ry = _ryanair(org, dst, date_from, price_max=price_max, limit=3)
            wz = _wizzair(org, dst, date_from, price_max=price_max, limit=3)
            flights = _merge(ry, wz)[:3]
            with lock:
                all_deals.extend(flights)
        except Exception as e:
            print(f"[HotDeals] {org}→{dst}: {e}")

    threads = []
    for org in origins[:5]:
        for dst in dests[:12]:
            t = threading.Thread(target=fetch, args=(org, dst))
            threads.append(t); t.start()
    for t in threads:
        t.join(timeout=25)

    all_deals.sort(key=lambda x: x["price"])
    seen, out = set(), []
    for f in all_deals:
        k = f"{f['origin']}:{f['destination']}:{f['price']}"
        if k not in seen:
            seen.add(k); out.append(f)
    return out[:limit]


def get_cheapest_dates(origin, destination, months=3):
    date_from = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
    # Kiwi первый — он работает для любых маршрутов
    results = _kiwi(origin, destination, date_from, limit=30)
    if not results:
        results = _ryanair(origin, destination, date_from, limit=20)
    if not results:
        results = _wizzair(origin, destination, date_from, limit=20)
    if not results:
        results = _aviasales_open(origin, destination, date_from, limit=15)
    if not results and FAST_FLIGHTS_OK:
        results = _fast_flights(origin, destination, date_from, limit=10)
    results.sort(key=lambda x: x["price"])
    return results[:7]


def get_week_prices(origin, destination):
    out = []
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    now = datetime.now()
    for i in range(1, 8):
        day = now + timedelta(days=i)
        iso = day.strftime("%Y-%m-%d")
        d_from = day.strftime("%d/%m/%Y")
        flights = _kiwi(origin, destination, d_from, limit=1)
        if not flights:
            flights = _ryanair(origin, destination, d_from, limit=1)
        if not flights:
            flights = _wizzair(origin, destination, d_from, limit=1)
        entry = {
            "date": day.strftime("%d.%m"),
            "weekday": days_ru[day.weekday()],
            "price": flights[0]["price"] if flights and flights[0].get("price") else None,
            "link": flights[0]["link"] if flights else _google_link(origin, destination, iso),
            "link_aviasales": _aviasales_link(origin, destination, iso),
        }
        out.append(entry)
    return out
