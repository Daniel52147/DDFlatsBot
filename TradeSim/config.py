from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "tradesim.db"

# Six markets — majors + volatile memecoins for learning
MARKETS = [
    {"symbol": "BTCUSDT", "label": "BTC", "name": "Bitcoin", "demo_price": 63_000.0},
    {"symbol": "ETHUSDT", "label": "ETH", "name": "Ethereum", "demo_price": 3_400.0},
    {"symbol": "SOLUSDT", "label": "SOL", "name": "Solana", "demo_price": 145.0},
    {"symbol": "BNBUSDT", "label": "BNB", "name": "BNB", "demo_price": 600.0},
    {
        "symbol": "DOGEUSDT",
        "label": "DOGE",
        "name": "Dogecoin",
        "demo_price": 0.15,
        "volatile": True,
        "strategy": {
            "dca_amount": 15.0,
            "dca_interval_hours": 12,
            "dip_threshold_pct": 5.0,
            "dip_extra_amount": 25.0,
            "sma_period": 14,
            "spike_threshold_pct": 10.0,
            "spike_extra_amount": 35.0,
        },
    },
    {
        "symbol": "PEPEUSDT",
        "label": "PEPE",
        "name": "Pepe",
        "demo_price": 0.00001,
        "volatile": True,
        "strategy": {
            "dca_amount": 12.0,
            "dca_interval_hours": 8,
            "dip_threshold_pct": 8.0,
            "dip_extra_amount": 30.0,
            "sma_period": 10,
            "spike_threshold_pct": 15.0,
            "spike_extra_amount": 40.0,
        },
    },
]

SYMBOL = MARKETS[0]["symbol"]  # backward compat
QUOTE = "USDT"

# Paper trading — $2 500 per market = $10 000 total
INITIAL_BALANCE = 10_000.0
BALANCE_PER_MARKET = INITIAL_BALANCE / len(MARKETS)
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005

STRATEGY = {
    "dca_amount": 25.0,
    "dca_interval_hours": 24,
    "dip_threshold_pct": 3.0,
    "dip_extra_amount": 40.0,
    "sma_period": 20,
}

CANDLE_INTERVAL = "1m"
MAX_CANDLES = 500

LEARNING_CHECK_HOURS = 24
MIN_TRADES_FOR_TUNING = 5

PRICE_DECIMALS = {
    "BTC": 0, "ETH": 2, "SOL": 2, "BNB": 2, "DOGE": 4, "PEPE": 8,
}

APP_VERSION = 5
