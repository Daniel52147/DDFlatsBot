import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

FREE_VIEWS = 7
VIP_PRICE = 19          # zł / month

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

DISTRICTS = [
    "Mokotów", "Ursynów", "Wilanów", "Wola", "Śródmieście",
    "Praga-Południe", "Praga-Północ", "Żoliborz", "Bielany",
    "Bemowo", "Ochota", "Targówek", "Białołęka", "Ursus", "Włochy",
    "Rembertów", "Wesoła", "Wawer",
]

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
}
