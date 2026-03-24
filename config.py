import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8655267832:AAHG9jPbmT3UmT4TeHA4xy3IuHSPjJiY4cI")

FREE_VIEWS = 5
VIP_PRICE = 19          # zł / month

# DB path — find a writable persistent location
# Priority: /var/data (Render disk) → project dir
_RENDER_DISK = "/var/data"
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def _find_db_path() -> str:
    # Try /var/data first (Render persistent disk)
    try:
        os.makedirs(_RENDER_DISK, exist_ok=True)
        test = os.path.join(_RENDER_DISK, ".write_test")
        with open(test, "w") as f:
            f.write("ok")
        os.remove(test)
        return os.path.join(_RENDER_DISK, "Flats.db")
    except Exception as e:
        print(f"[Config] /var/data not writable: {e}")

    # Fallback: DATA_DIR env var
    data_dir = os.environ.get("DATA_DIR", "")
    if data_dir:
        try:
            os.makedirs(data_dir, exist_ok=True)
            return os.path.join(data_dir, "Flats.db")
        except Exception:
            pass

    # Last resort: same directory as config.py (works on Render too)
    # On Render: /opt/render/project/src/DDFlatsBot/config.py
    return os.path.join(_PROJECT_DIR, "Flats.db")

DB_PATH = _find_db_path()
print(f"[Config] DB_PATH = {DB_PATH}")

ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "2066158453").split(",") if x.strip()]
MODERATOR_IDS = []

CHANNEL_LINK = "https://t.me/ddflots"
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@ddflots")

EARLY_ADOPTER_LIMIT = 50

REFERRAL_REWARD_DAYS = 7
REFERRAL_REQUIRED = 3

VIP_EARLY_ACCESS_MINUTES = 0

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
]

DISTRICTS = [
    "Mokotów", "Ursynów", "Wilanów", "Wola", "Śródmieście",
    "Praga-Południe", "Praga-Północ", "Żoliborz", "Bielany",
    "Bemowo", "Ochota", "Targówek", "Białołęka", "Ursus", "Włochy",
]
