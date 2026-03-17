import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8655267832:AAHG9jPbmT3UmT4TeHA4xy3IuHSPjJiY4cI")

FREE_VIEWS = 5
VIP_PRICE = 19          # zł / month

# DB path — on Render use /var/data/ (persistent disk), locally use Flats.db
_data_dir = os.environ.get("DATA_DIR", "")
if _data_dir:
    os.makedirs(_data_dir, exist_ok=True)
    DB_PATH = os.path.join(_data_dir, "Flats.db")
else:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Flats.db")

print(f"[Config] DB_PATH = {DB_PATH}")

ADMIN_IDS = [2066158453]
MODERATOR_IDS = []

CHANNEL_LINK = "https://t.me/ddflots"
CHANNEL_ID = "@ddflots"

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
    "Bemowo", "Ochota", "Targówek", "Białołęka", "Ursus",
]
