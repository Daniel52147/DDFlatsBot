import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Kiwi.com Tequila API — free, no approval needed
# Register at: https://tequila.kiwi.com/
KIWI_API_KEY = os.environ.get("KIWI_API_KEY", "")

# Aviasales partner API (optional, for affiliate links)
# Register at: https://www.aviasales.ru/api
AVIASALES_TOKEN = os.environ.get("AVIASALES_TOKEN", "")
AVIASALES_MARKER = os.environ.get("AVIASALES_MARKER", "")  # your partner marker

# DB
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
_RENDER_DISK = "/var/data"

def _find_db_path() -> str:
    try:
        os.makedirs(_RENDER_DISK, exist_ok=True)
        test = os.path.join(_RENDER_DISK, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return os.path.join(_RENDER_DISK, "flights.db")
    except Exception:
        pass
    data_dir = os.environ.get("DATA_DIR", "")
    if data_dir:
        try:
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "flights.db")
        except Exception:
            pass
    return os.path.join(_PROJECT_DIR, "flights.db")

DB_PATH = _find_db_path()
print(f"[Config] DB_PATH = {DB_PATH}")

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "2066158453").split(",") if x.strip()]

FREE_SEARCHES = 5          # free searches per day
VIP_PRICE_PLN = 19         # zł/month
VIP_PRICE_STARS = 50       # Telegram Stars

CHANNEL_ID = os.environ.get("CHANNEL_ID", "@ddflights")
CHANNEL_LINK = "https://t.me/ddflights"

# Popular departure airports (IATA codes)
POPULAR_ORIGINS = ["WAW", "KRK", "WRO", "GDN", "KTW", "POZ"]

# Popular destinations
POPULAR_DESTINATIONS = [
    ("Barcelona", "BCN"),
    ("Rome",      "FCO"),
    ("London",    "LTN"),
    ("Paris",     "CDG"),
    ("Dubai",     "DXB"),
    ("Milan",     "MXP"),
    ("Amsterdam", "AMS"),
    ("Lisbon",    "LIS"),
    ("Athens",    "ATH"),
    ("Tenerife",  "TFS"),
]

# Max price for "hot deals" alerts
HOT_DEAL_MAX_PRICE = 100   # EUR

# Webhook
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN.split(':')[0]}" if BOT_TOKEN else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else ""
WEBAPP_PORT = int(os.environ.get("PORT", 8080))
