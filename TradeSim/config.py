from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "tradesim.db"

# Four markets — each bot learns in its own niche
MARKETS = [
    {"symbol": "BTCUSDT", "label": "BTC", "name": "Bitcoin", "demo_price": 63_000.0},
    {"symbol": "ETHUSDT", "label": "ETH", "name": "Ethereum", "demo_price": 3_400.0},
    {"symbol": "SOLUSDT", "label": "SOL", "name": "Solana", "demo_price": 145.0},
    {"symbol": "BNBUSDT", "label": "BNB", "name": "BNB", "demo_price": 600.0},
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

DEMO_FALLBACK_PRICE = 63_000.0
