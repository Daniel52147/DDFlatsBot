import os

BOT_NAME = "SkyCheap"
BOT_USERNAME = os.environ.get("BOT_USERNAME", "DDSkyCheapBot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8611527220:AAFH5ClovMuUp7h3-rXscWPucEVQwNacYFs")

# Aviasales partner API (optional affiliate links)
AVIASALES_TOKEN = os.environ.get("AVIASALES_TOKEN", "")
AVIASALES_MARKER = os.environ.get("AVIASALES_MARKER", "")

# DB path — Render disk → project dir fallback
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_RENDER_DISK = "/var/data"


def _find_db_path() -> str:
    # On Render: /var/data is the persistent disk
    if os.path.exists(_RENDER_DISK) or os.environ.get("RENDER"):
        try:
            os.makedirs(_RENDER_DISK, exist_ok=True)
            test = os.path.join(_RENDER_DISK, ".write_test")
            with open(test, "w") as f:
                f.write("ok")
            os.remove(test)
            return os.path.join(_RENDER_DISK, "skycheap.db")
        except Exception:
            pass
    # DATA_DIR env override
    data_dir = os.environ.get("DATA_DIR", "")
    if data_dir:
        try:
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "skycheap.db")
        except Exception:
            pass
    # Local dev: same folder as config.py
    return os.path.join(_PROJECT_DIR, "skycheap.db")

DB_PATH = _find_db_path()
print(f"[Config] DB_PATH = {DB_PATH}")

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "2066158453").split(",") if x.strip()]

FREE_SEARCHES = 5       # free searches per day
VIP_PRICE_PLN = 19      # zł/month
VIP_PRICE_STARS = 50    # Telegram Stars

CHANNEL_ID = os.environ.get("CHANNEL_ID", "@DDSkyCheapBot")
CHANNEL_LINK = os.environ.get("CHANNEL_LINK", "https://t.me/DDSkyCheapBot")

# Popular departure airports (IATA)
POPULAR_ORIGINS = ["WAW", "KRK", "WRO", "GDN", "KTW", "POZ"]

# Popular destinations with emoji flags
POPULAR_DESTINATIONS = [
    ("Barcelona 🇪🇸",  "BCN"),
    ("Rome 🇮🇹",        "FCO"),
    ("London 🇬🇧",      "LTN"),
    ("Paris 🇫🇷",       "CDG"),
    ("Dubai 🇦🇪",       "DXB"),
    ("Milan 🇮🇹",       "MXP"),
    ("Amsterdam 🇳🇱",   "AMS"),
    ("Lisbon 🇵🇹",      "LIS"),
    ("Athens 🇬🇷",      "ATH"),
    ("Tenerife 🇪🇸",    "TFS"),
    ("Prague 🇨🇿",      "PRG"),
    ("Vienna 🇦🇹",      "VIE"),
]

HOT_DEAL_MAX_PRICE = 100  # EUR

# Rate limiting
RATE_LIMIT_REQUESTS = 8
RATE_LIMIT_WINDOW = 10  # seconds

# Webhook
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN.split(':')[0]}" if BOT_TOKEN else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
WEBAPP_PORT = int(os.environ.get("PORT", 8080))
