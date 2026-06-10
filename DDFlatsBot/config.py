import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Fully free bot — no paid tier in UI
BOT_FREE_MODE = True
FREE_VIEWS = 7          # used only when BOT_FREE_MODE is False
VIP_PRICE = 19          # legacy — admin stats only

# Include nearby cities in search (0 = selected city only)
SEARCH_RADIUS_KM_DEFAULT = 100

# Sentinel for "all districts" in callbacks/DB (avoid Cyrillic in callback_data)
DISTRICT_ALL = "__all__"
_LEGACY_DISTRICT_ALL = "все"


def is_all_district(district: str | None) -> bool:
    if district is None or district == "":
        return True
    return district in (DISTRICT_ALL, _LEGACY_DISTRICT_ALL)


def normalize_district(district: str) -> str:
    return DISTRICT_ALL if is_all_district(district) else district

# Smart alerts — same limit for everyone
FREE_ALERT_LIMIT = 5
VIP_ALERT_LIMIT = 5

# DB path — find a writable persistent location
_RENDER_DISK = "/var/data"
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_db_path() -> str:
    try:
        os.makedirs(_RENDER_DISK, exist_ok=True)
        test = os.path.join(_RENDER_DISK, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return os.path.join(_RENDER_DISK, "Flats.db")
    except Exception as e:
        print(f"[Config] /var/data not writable: {e}")

    data_dir = os.environ.get("DATA_DIR", "")
    if data_dir:
        try:
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "Flats.db")
        except Exception:
            pass

    return os.path.join(_PROJECT_DIR, "Flats.db")


DB_PATH = _find_db_path()
print(f"[Config] DB_PATH = {DB_PATH}")

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "2066158453").split(",") if x.strip()]
MODERATOR_IDS = []

CHANNEL_LINK = "https://t.me/ddflots"
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@ddflots")

EARLY_ADOPTER_LIMIT = 100

REFERRAL_REWARD_DAYS = 7
REFERRAL_REQUIRED = 3

VIP_EARLY_ACCESS_MINUTES = 0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

# Districts per city
CITY_DISTRICTS = {
    "Warszawa": [
        "Mokotów", "Ursynów", "Wilanów", "Wola", "Śródmieście",
        "Praga-Południe", "Praga-Północ", "Żoliborz", "Bielany",
        "Bemowo", "Ochota", "Targówek", "Białołęka", "Ursus", "Włochy",
        "Rembertów", "Wesoła", "Wawer",
    ],
    "Kraków": [
        "Stare Miasto", "Kazimierz", "Krowodrza", "Bronowice",
        "Prądnik Biały", "Prądnik Czerwony", "Grzegórzki", "Dębniki",
        "Podgórze", "Nowa Huta", "Mistrzejowice", "Bieżanów",
    ],
    "Wrocław": [
        "Stare Miasto", "Śródmieście", "Krzyki", "Fabryczna",
        "Psie Pole", "Nadodrze", "Biskupin", "Gaj", "Ołtaszyn",
    ],
    "Gdańsk": [
        "Śródmieście", "Wrzeszcz", "Oliwa", "Przymorze", "Zaspa",
        "Chełm", "Morena", "Piecki-Migowo", "Suchanino",
    ],
    "Poznań": [
        "Stare Miasto", "Grunwald", "Jeżyce", "Nowe Miasto",
        "Wilda", "Winogrady", "Rataje", "Piątkowo",
    ],
    "Łódź": [
        "Śródmieście", "Bałuty", "Górna", "Polesie",
        "Widzew", "Retkinia", "Mileszki",
    ],
    "Katowice": [
        "Śródmieście", "Bogucice", "Koszutka", "Ligota",
        "Murcki", "Zawodzie", "Dąb", "Janów",
    ],
    "Lublin": [
        "Śródmieście", "Czuby", "Sławin", "Wieniawa",
        "Tatary", "Bronowice", "Szerokie", "Węglin",
    ],
    "Szczecin": [
        "Śródmieście", "Prawobrzeże", "Północ", "Zachód",
        "Bukowo", "Niebuszewo", "Gumieńce",
    ],
    "Białystok": [
        "Centrum", "Bojary", "Piaski", "Skorupy",
        "Antoniuk", "Dojlidy", "Wygoda",
    ],
}

# Keep DISTRICTS as alias for Warszawa (backward compat)
DISTRICTS = CITY_DISTRICTS["Warszawa"]

# Other Polish cities — separate from Warsaw
CITIES = {
    "Warszawa": {
        "label": "🏙 Warszawa",
        "url_olx": "warszawa",
        "url_otodom": "warszawa",
        "city_id_olx": 39610,
        "region_id_olx": 7,
    },
    "Kraków": {
        "label": "🏰 Kraków",
        "url_olx": "krakow",
        "url_otodom": "krakow",
        "city_id_olx": 8,
        "region_id_olx": 5,
    },
    "Wrocław": {
        "label": "🌉 Wrocław",
        "url_olx": "wroclaw",
        "url_otodom": "wroclaw",
        "city_id_olx": 9,
        "region_id_olx": 14,
    },
    "Gdańsk": {
        "label": "⚓ Gdańsk",
        "url_olx": "gdansk",
        "url_otodom": "gdansk",
        "city_id_olx": 40,
        "region_id_olx": 4,
    },
    "Poznań": {
        "label": "🎓 Poznań",
        "url_olx": "poznan",
        "url_otodom": "poznan",
        "city_id_olx": 42,
        "region_id_olx": 11,
    },
    "Łódź": {
        "label": "🏭 Łódź",
        "url_olx": "lodz",
        "url_otodom": "lodz",
        "city_id_olx": 106,
        "region_id_olx": 2,
    },
    "Katowice": {
        "label": "⛏ Katowice",
        "url_olx": "katowice",
        "url_otodom": "katowice",
        "city_id_olx": 87,
        "region_id_olx": 6,
    },
    "Lublin": {
        "label": "🌳 Lublin",
        "url_olx": "lublin",
        "url_otodom": "lublin",
        "city_id_olx": 101,
        "region_id_olx": 8,
    },
    "Szczecin": {
        "label": "🚢 Szczecin",
        "url_olx": "szczecin",
        "url_otodom": "szczecin",
        "city_id_olx": 131,
        "region_id_olx": 3,
    },
    "Białystok": {
        "label": "🌲 Białystok",
        "url_olx": "bialystok",
        "url_otodom": "bialystok",
        "city_id_olx": 352,
        "region_id_olx": 9,
    },
}

MIN_LISTINGS_PER_CITY = 100
# Show «Search on sites» hint when city has fewer listings than this
MIN_LISTINGS_PLATFORM_HINT = 20


def city_slug(city: str) -> str:
    """URL slug used on OLX, Gratka, Morizon, Adresowo, etc."""
    return CITIES.get(city, CITIES["Warszawa"]).get("url_olx", "warszawa")


# City centers for radius search (lat, lon)
CITY_COORDS = {
    "Warszawa": (52.2297, 21.0122),
    "Kraków": (50.0647, 19.9450),
    "Wrocław": (51.1079, 17.0385),
    "Gdańsk": (54.3520, 18.6466),
    "Poznań": (52.4064, 16.9252),
    "Łódź": (51.7592, 19.4560),
    "Katowice": (50.2649, 19.0238),
    "Lublin": (51.2465, 22.5684),
    "Szczecin": (53.4285, 14.5528),
    "Białystok": (53.1325, 23.1688),
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def get_cities_in_radius(center: str, radius_km: float = SEARCH_RADIUS_KM_DEFAULT) -> list[str]:
    """Cities from our list within radius_km of center (center first, then by distance)."""
    if center not in CITY_COORDS or radius_km <= 0:
        return [center]
    lat0, lon0 = CITY_COORDS[center]
    nearby: list[tuple[float, str]] = []
    for city, (lat, lon) in CITY_COORDS.items():
        if city == center:
            continue
        dist = _haversine_km(lat0, lon0, lat, lon)
        if dist <= radius_km:
            nearby.append((dist, city))
    nearby.sort(key=lambda x: x[0])
    return [center] + [c for _, c in nearby]


def resolve_search_cities(city: str, radius_km: int | float | None = None) -> list[str]:
    """Primary city + neighbors when radius is enabled."""
    if radius_km is None:
        radius_km = SEARCH_RADIUS_KM_DEFAULT
    if radius_km <= 0:
        return [city]
    return get_cities_in_radius(city, float(radius_km))


# Domiporta fallback paths: voivodeship/city
DOMIPORTA_PATHS = {
    "Warszawa": "mazowieckie/warszawa",
    "Kraków": "malopolskie/krakow",
    "Wrocław": "dolnoslaskie/wroclaw",
    "Gdańsk": "pomorskie/gdansk",
    "Poznań": "wielkopolskie/poznan",
    "Łódź": "lodzkie/lodz",
    "Katowice": "slaskie/katowice",
    "Lublin": "lubelskie/lublin",
    "Szczecin": "zachodniopomorskie/szczecin",
    "Białystok": "podlaskie/bialystok",
}

# Visual menu style per city (different button layout in bot)
CITY_MENU_STYLE = {
    "Warszawa": "capital",
    "Kraków": "capital",
    "Wrocław": "culture",
    "Gdańsk": "coastal",
    "Poznań": "business",
    "Łódź": "industrial",
    "Katowice": "industrial",
    "Lublin": "quiet",
    "Szczecin": "coastal",
    "Białystok": "quiet",
}

# Nocowanie.pl URL slugs
NOCOWANIE_SLUGS = {
    "Warszawa": "warszawa",
    "Kraków": "krakow",
    "Wrocław": "wroclaw",
    "Gdańsk": "gdansk",
    "Poznań": "poznan",
    "Łódź": "lodz",
    "Katowice": "katowice",
    "Lublin": "lublin",
    "Szczecin": "szczecin",
    "Białystok": "bialystok",
}

# Flatio.pl short-term rental pages
FLATIO_SLUGS = {
    "Warszawa": "warszawa",
    "Kraków": "krakow",
    "Wrocław": "wroclaw",
    "Gdańsk": "gdansk",
    "Poznań": "poznan",
    "Łódź": "lodz",
    "Katowice": "katowice",
    "Lublin": "lublin",
    "Szczecin": "szczecin",
    "Białystok": "bialystok",
}


def flatio_daily_url(city: str) -> str:
    slug = FLATIO_SLUGS.get(city, "warszawa")
    return f"https://www.flatio.pl/najem-krotkoterminowy-{slug}"

# Booking / Airbnb location names
BOOKING_LOCATIONS = {
    "Warszawa": "Warszawa",
    "Kraków": "Krakow",
    "Wrocław": "Wroclaw",
    "Gdańsk": "Gdansk",
    "Poznań": "Poznan",
    "Łódź": "Lodz",
    "Katowice": "Katowice",
    "Lublin": "Lublin",
    "Szczecin": "Szczecin",
    "Białystok": "Bialystok",
}

AIRBNB_LOCATIONS = {
    "Warszawa": "Warsaw--Poland",
    "Kraków": "Krakow--Lesser-Poland-Poland",
    "Wrocław": "Wroclaw--Lower-Silesian--Poland",
    "Gdańsk": "Gdansk--Pomeranian--Poland",
    "Poznań": "Poznan--Greater-Poland--Poland",
    "Łódź": "Lodz--Lodz--Poland",
    "Katowice": "Katowice--Silesian--Poland",
    "Lublin": "Lublin--Lublin--Poland",
    "Szczecin": "Szczecin--West-Pomeranian--Poland",
    "Białystok": "Bialystok--Podlaskie--Poland",
}

# Parser cookie overrides — set via /admin in bot
# Format: {"Gratka": "cookie_string", "Morizon": "cookie_string"}
PARSER_COOKIES: dict = {}
