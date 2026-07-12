from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "tradesim.db"

# Markets: majors + memes + growth alts + 1 viral trending coin
# Paper $10k split evenly across all markets

GROWTH_STRATEGY = {
    "dca_amount": 18.0,
    "dca_interval_hours": 16,
    "dip_threshold_pct": 4.0,
    "dip_extra_amount": 32.0,
    "sma_period": 16,
    "spike_threshold_pct": 9.0,
    "spike_extra_amount": 28.0,
    "take_profit_pct": 8.0,
    "take_profit_cost_pct": 6.5,
    "take_profit_fraction": 0.20,
    "take_profit_cooldown_hours": 4,
    "dip_cooldown_minutes": 20,
    "spike_cooldown_minutes": 35,
    "stop_loss_pct": 14.0,
    "stop_loss_fraction": 0.22,
}

VOLATILE_STRATEGY = {
    "dca_amount": 15.0,
    "dca_interval_hours": 12,
    "dip_threshold_pct": 5.0,
    "dip_extra_amount": 25.0,
    "sma_period": 14,
    "spike_threshold_pct": 10.0,
    "spike_extra_amount": 35.0,
    "take_profit_pct": 6.0,
    "take_profit_cost_pct": 5.0,
    "take_profit_fraction": 0.25,
    "take_profit_cooldown_hours": 3,
    "dip_cooldown_minutes": 15,
    "spike_cooldown_minutes": 30,
    "stop_loss_pct": 15.0,
    "stop_loss_fraction": 0.25,
}

VIRAL_STRATEGY = {
    "dca_amount": 10.0,
    "dca_interval_hours": 6,
    "dip_threshold_pct": 7.0,
    "dip_extra_amount": 28.0,
    "sma_period": 10,
    "spike_threshold_pct": 12.0,
    "spike_extra_amount": 45.0,
    "take_profit_pct": 7.0,
    "take_profit_cost_pct": 5.5,
    "take_profit_fraction": 0.32,
    "take_profit_cooldown_hours": 2,
    "dip_cooldown_minutes": 8,
    "spike_cooldown_minutes": 15,
    "stop_loss_pct": 18.0,
    "stop_loss_fraction": 0.30,
}

MARKETS = [
    {"symbol": "BTCUSDT", "label": "BTC", "name": "Bitcoin", "demo_price": 63_000.0, "tier": "major"},
    {"symbol": "ETHUSDT", "label": "ETH", "name": "Ethereum", "demo_price": 3_400.0, "tier": "major"},
    {"symbol": "SOLUSDT", "label": "SOL", "name": "Solana", "demo_price": 145.0, "tier": "major"},
    {"symbol": "BNBUSDT", "label": "BNB", "name": "BNB", "demo_price": 600.0, "tier": "major"},
    # — 10 growth / high-investment alts —
    {"symbol": "XRPUSDT", "label": "XRP", "name": "Ripple", "demo_price": 2.50, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "ADAUSDT", "label": "ADA", "name": "Cardano", "demo_price": 0.45, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "AVAXUSDT", "label": "AVAX", "name": "Avalanche", "demo_price": 25.0, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "LINKUSDT", "label": "LINK", "name": "Chainlink", "demo_price": 15.0, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "ARBUSDT", "label": "ARB", "name": "Arbitrum", "demo_price": 0.80, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "SUIUSDT", "label": "SUI", "name": "Sui", "demo_price": 2.50, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "NEARUSDT", "label": "NEAR", "name": "NEAR Protocol", "demo_price": 4.50, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "DOTUSDT", "label": "DOT", "name": "Polkadot", "demo_price": 5.50, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "INJUSDT", "label": "INJ", "name": "Injective", "demo_price": 15.0, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    {"symbol": "TONUSDT", "label": "TON", "name": "Toncoin", "demo_price": 5.50, "tier": "growth", "growth": True, "strategy": GROWTH_STRATEGY},
    # — memecoins —
    {
        "symbol": "DOGEUSDT",
        "label": "DOGE",
        "name": "Dogecoin",
        "demo_price": 0.15,
        "tier": "volatile",
        "volatile": True,
        "strategy": VOLATILE_STRATEGY,
    },
    {
        "symbol": "PEPEUSDT",
        "label": "PEPE",
        "name": "Pepe",
        "demo_price": 0.00001,
        "tier": "volatile",
        "volatile": True,
        "strategy": {
            **VOLATILE_STRATEGY,
            "dca_amount": 12.0,
            "dca_interval_hours": 8,
            "dip_threshold_pct": 8.0,
            "dip_extra_amount": 30.0,
            "sma_period": 10,
            "spike_threshold_pct": 15.0,
            "spike_extra_amount": 40.0,
            "take_profit_pct": 8.0,
            "take_profit_fraction": 0.30,
            "take_profit_cooldown_hours": 2,
            "dip_cooldown_minutes": 10,
            "spike_cooldown_minutes": 20,
            "stop_loss_pct": 18.0,
            "stop_loss_fraction": 0.3,
        },
    },
    # — EXTRA: viral coin that can spike overnight —
    {
        "symbol": "WIFUSDT",
        "label": "WIF",
        "name": "dogwifhat",
        "demo_price": 2.00,
        "tier": "viral",
        "volatile": True,
        "viral": True,
        "strategy": VIRAL_STRATEGY,
    },
]

SYMBOL = MARKETS[0]["symbol"]  # backward compat
QUOTE = "USDT"

# Paper trading — $10 000 total, split evenly per market
INITIAL_BALANCE = 10_000.0
BALANCE_PER_MARKET = INITIAL_BALANCE / len(MARKETS)
FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005

STRATEGY = {
    "dca_amount": 25.0,
    "dca_interval_hours": 24,
    "dip_threshold_pct": 3.0,
    "dip_extra_amount": 40.0,
    "dip_cooldown_minutes": 30,
    "spike_cooldown_minutes": 60,
    "sma_period": 20,
    "take_profit_pct": 10.0,
    "take_profit_cost_pct": 8.0,
    "take_profit_fraction": 0.15,
    "take_profit_cooldown_hours": 6,
    "stop_loss_pct": 12.0,
    "stop_loss_fraction": 0.2,
    "stop_loss_cooldown_hours": 12,
    "max_buy_pct_of_cash": 0.5,
}

CANDLE_INTERVAL = "1m"
MAX_CANDLES = 500

LEARNING_CHECK_SEC = 1800          # 30 min — majors
LEARNING_CHECK_VOLATILE_SEC = 600  # 10 min — DOGE/PEPE/WIF
LEARNING_CHECK_HOURS = LEARNING_CHECK_SEC / 3600  # backward compat
MIN_TRADES_FOR_TUNING = 2
MIN_TRADES_VOLATILE = 1
FAST_LEARN_EVERY_N_TRADES = 2     # retune every 2 trades if losing
BRAIN_CYCLE_SEC = 45

# Shadow Lab — hidden parallel mock bots (same crypto, many param variants)
SHADOW_LAB_ENABLED = True
SHADOW_CLONES_PER_MARKET = 12       # 12 mocks × N markets
SHADOW_BALANCE = 500.0              # virtual $ per clone
SHADOW_EVAL_SEC = 90                # pick winners every 90s
SHADOW_PARAM_JITTER = 0.18          # random extra variation
SHADOW_MIN_TRADES_PROMOTE = 3       # clone needs N trades before promotion
SHADOW_PROMOTE_MARGIN = 0.35        # must beat live by this many pp vs hold

PRICE_DECIMALS = {
    "BTC": 0, "ETH": 2, "SOL": 2, "BNB": 2,
    "XRP": 4, "ADA": 4, "AVAX": 2, "LINK": 3, "ARB": 4,
    "SUI": 4, "NEAR": 3, "DOT": 3, "INJ": 3, "TON": 3,
    "DOGE": 4, "PEPE": 8, "WIF": 4,
}

APP_VERSION = 15

# Security — default localhost; set TRADESIM_API_TOKEN for remote write access
BIND_HOST = os.environ.get("TRADESIM_BIND_HOST", "127.0.0.1")
API_TOKEN = os.environ.get("TRADESIM_API_TOKEN", "")

# Live exchange (optional — set env BINANCE_API_KEY + BINANCE_API_SECRET + EXCHANGE_ENABLED=true)
EXCHANGE_ENABLED = os.environ.get("EXCHANGE_ENABLED", "false").lower() in ("1", "true", "yes")
EXCHANGE_NAME = "binance"
EXCHANGE_TESTNET = True
EXCHANGE_MAX_ORDER_USD = 100.0
EXCHANGE_MAX_DAILY_LOSS_PCT = 5.0
EXCHANGE_MAX_POSITION_PCT = 0.25
