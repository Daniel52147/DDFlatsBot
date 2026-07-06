from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "tradesim.db"

# Market: BTC/USDT on Binance (real-time public data, no API key needed)
SYMBOL = "BTCUSDT"
QUOTE = "USDT"
BASE = "BTC"

# Paper trading defaults
INITIAL_BALANCE = 10_000.0
FEE_RATE = 0.001          # 0.1% per trade
SLIPPAGE_RATE = 0.0005    # 0.05% worse fill

# Strategy parameters (bot learns by tuning these in one niche)
STRATEGY = {
    "dca_amount": 100.0,           # USDT per scheduled buy
    "dca_interval_hours": 24,
    "dip_threshold_pct": 3.0,      # extra buy if price below SMA by this %
    "dip_extra_amount": 150.0,
    "sma_period": 20,              # candles for moving average
}

# Candle aggregation
CANDLE_INTERVAL = "1m"   # 1m, 5m, 15m, 1h
MAX_CANDLES = 500

# Learning
LEARNING_CHECK_HOURS = 24
MIN_TRADES_FOR_TUNING = 5

# Fallback BTC price when all APIs unreachable (SSL/network)
DEMO_FALLBACK_PRICE = 63_000.0
