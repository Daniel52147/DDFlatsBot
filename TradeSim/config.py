from pathlib import Path
import os

# Load .env from TradeSim/ (keys never go in git)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

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

GRID_STRATEGY = {
    **GROWTH_STRATEGY,
    "grid_spacing_pct": 1.8,
    "grid_buy_amount": 22.0,
    "grid_sell_fraction": 0.18,
    "grid_cooldown_minutes": 6,
    "dca_interval_hours": 10,
}

MOMENTUM_STRATEGY = {
    **VIRAL_STRATEGY,
    "breakout_pct": 1.8,
    "trailing_stop_pct": 4.5,
    "momentum_buy_amount": 38.0,
    "trail_sell_fraction": 0.35,
    "entry_cooldown_minutes": 18,
    "dca_interval_hours": 10,
}

RSI_STRATEGY = {
    **VOLATILE_STRATEGY,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "rsi_buy_amount": 28.0,
    "rsi_sell_fraction": 0.22,
    "rsi_buy_cooldown_minutes": 15,
    "rsi_sell_cooldown_minutes": 20,
    "dca_interval_hours": 14,
}

SCALPER_STRATEGY = {
    **VOLATILE_STRATEGY,
    "scalp_move_pct": 0.45,
    "scalp_tp_pct": 0.45,
    "scalp_buy_amount": 16.0,
    "scalp_sell_fraction": 0.28,
    "scalp_cooldown_seconds": 45,
    "dca_interval_hours": 4,
    "dca_amount": 12.0,
    "sma_period": 8,
    "take_profit_pct": 3.5,
    "stop_loss_pct": 8.0,
}

MARKETS = [
    {"symbol": "BTCUSDT", "label": "BTC", "name": "Bitcoin", "demo_price": 63_000.0, "tier": "major", "strategy_type": "dca"},
    {"symbol": "ETHUSDT", "label": "ETH", "name": "Ethereum", "demo_price": 3_400.0, "tier": "major", "strategy_type": "dca"},
    {"symbol": "SOLUSDT", "label": "SOL", "name": "Solana", "demo_price": 145.0, "tier": "major", "strategy_type": "momentum", "strategy": MOMENTUM_STRATEGY},
    {"symbol": "BNBUSDT", "label": "BNB", "name": "BNB", "demo_price": 600.0, "tier": "major", "strategy_type": "dca"},
    # — 10 growth / high-investment alts —
    {"symbol": "XRPUSDT", "label": "XRP", "name": "Ripple", "demo_price": 2.50, "tier": "growth", "growth": True, "strategy_type": "grid", "strategy": GRID_STRATEGY},
    {"symbol": "ADAUSDT", "label": "ADA", "name": "Cardano", "demo_price": 0.45, "tier": "growth", "growth": True, "strategy_type": "grid", "strategy": GRID_STRATEGY},
    {"symbol": "AVAXUSDT", "label": "AVAX", "name": "Avalanche", "demo_price": 25.0, "tier": "growth", "growth": True, "strategy_type": "grid", "strategy": GRID_STRATEGY},
    {"symbol": "LINKUSDT", "label": "LINK", "name": "Chainlink", "demo_price": 15.0, "tier": "growth", "growth": True, "strategy_type": "dca", "strategy": GROWTH_STRATEGY},
    {"symbol": "ARBUSDT", "label": "ARB", "name": "Arbitrum", "demo_price": 0.80, "tier": "growth", "growth": True, "strategy_type": "grid", "strategy": GRID_STRATEGY},
    {"symbol": "SUIUSDT", "label": "SUI", "name": "Sui", "demo_price": 2.50, "tier": "growth", "growth": True, "strategy_type": "grid", "strategy": GRID_STRATEGY},
    {"symbol": "NEARUSDT", "label": "NEAR", "name": "NEAR Protocol", "demo_price": 4.50, "tier": "growth", "growth": True, "strategy_type": "scalper", "strategy": SCALPER_STRATEGY},
    {"symbol": "DOTUSDT", "label": "DOT", "name": "Polkadot", "demo_price": 5.50, "tier": "growth", "growth": True, "strategy_type": "scalper", "strategy": SCALPER_STRATEGY},
    {"symbol": "INJUSDT", "label": "INJ", "name": "Injective", "demo_price": 15.0, "tier": "growth", "growth": True, "strategy_type": "momentum", "strategy": MOMENTUM_STRATEGY},
    {"symbol": "TONUSDT", "label": "TON", "name": "Toncoin", "demo_price": 5.50, "tier": "growth", "growth": True, "strategy_type": "grid", "strategy": GRID_STRATEGY},
    # — memecoins —
    {
        "symbol": "DOGEUSDT",
        "label": "DOGE",
        "name": "Dogecoin",
        "demo_price": 0.15,
        "tier": "volatile",
        "volatile": True,
        "strategy_type": "rsi",
        "strategy": RSI_STRATEGY,
    },
    {
        "symbol": "PEPEUSDT",
        "label": "PEPE",
        "name": "Pepe",
        "demo_price": 0.00001,
        "tier": "volatile",
        "volatile": True,
        "strategy_type": "rsi",
        "strategy": {
            **RSI_STRATEGY,
            "rsi_oversold": 28,
            "rsi_overbought": 72,
            "rsi_buy_amount": 32.0,
            "dca_interval_hours": 8,
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
        "strategy_type": "momentum",
        "strategy": MOMENTUM_STRATEGY,
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
    "dca_interval_hours": 8,
    "dip_threshold_pct": 2.5,
    "dip_extra_amount": 40.0,
    "dip_cooldown_minutes": 12,
    "spike_threshold_pct": 5.0,
    "spike_extra_amount": 35.0,
    "spike_cooldown_minutes": 20,
    "sma_period": 20,
    "take_profit_pct": 10.0,
    "take_profit_cost_pct": 8.0,
    "take_profit_fraction": 0.15,
    "take_profit_cooldown_hours": 3,
    "stop_loss_pct": 12.0,
    "stop_loss_fraction": 0.2,
    "stop_loss_cooldown_hours": 6,
    "max_buy_pct_of_cash": 0.5,
}

CANDLE_INTERVAL = "1m"
MAX_CANDLES = 500


def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes")


LEARNING_CHECK_SEC = 1800          # 30 min — majors
LEARNING_CHECK_VOLATILE_SEC = 600  # 10 min — DOGE/PEPE/WIF
LEARNING_CHECK_HOURS = LEARNING_CHECK_SEC / 3600  # backward compat
MIN_TRADES_FOR_TUNING = 5
MIN_TRADES_VOLATILE = 3
FAST_LEARN_EVERY_N_TRADES = 3     # retune every 3 trades if losing
PAPER_LEARN_ENABLED = _env_bool("PAPER_LEARN_ENABLED", True)
PAPER_LEARN_ON_START = _env_bool("PAPER_LEARN_ON_START", True)
PAPER_LEARN_RESET_TIMERS = _env_bool("PAPER_LEARN_RESET_TIMERS", True)
PAPER_LEARN_MIN_TRADES_TUNING = int(os.environ.get("PAPER_LEARN_MIN_TRADES_TUNING", "2"))
PAPER_LEARN_FAST_EVERY_N = int(os.environ.get("PAPER_LEARN_FAST_EVERY_N", "2"))
PAPER_LEARN_DCA_MAX_HOURS = float(os.environ.get("PAPER_LEARN_DCA_MAX_HOURS", "1.5"))
PAPER_LEARN_SCALP_COOLDOWN_SEC = int(os.environ.get("PAPER_LEARN_SCALP_COOLDOWN_SEC", "20"))
PAPER_LEARN_GRID_COOLDOWN_MIN = float(os.environ.get("PAPER_LEARN_GRID_COOLDOWN_MIN", "3"))
PAPER_LEARN_MAX_DRAWDOWN_PCT = float(os.environ.get("PAPER_LEARN_MAX_DRAWDOWN_PCT", "18"))
PAPER_LEARN_DISABLE_PROFIT_PAUSE = _env_bool("PAPER_LEARN_DISABLE_PROFIT_PAUSE", True)
PAPER_LEARN_IGNORE_CORRELATION_BLOCK = _env_bool("PAPER_LEARN_IGNORE_CORRELATION_BLOCK", True)

# Testnet discipline (v43) — conservative after leaving paper
TESTNET_APPLY_CONSERVATIVE_ON_SWITCH = _env_bool("TESTNET_APPLY_CONSERVATIVE_ON_SWITCH", True)
TESTNET_MIN_DCA_HOURS = float(os.environ.get("TESTNET_MIN_DCA_HOURS", "6"))
TESTNET_MIN_DIP_COOLDOWN_MIN = float(os.environ.get("TESTNET_MIN_DIP_COOLDOWN_MIN", "15"))

BRAIN_CYCLE_SEC = 45

# Portfolio risk — brain + execution gate
PORTFOLIO_MAX_DRAWDOWN_PCT = float(os.environ.get("PORTFOLIO_MAX_DRAWDOWN_PCT", "12"))
REGIME_FILTER_ENABLED = _env_bool("REGIME_FILTER_ENABLED", False)

# Shadow Lab — hidden parallel mock bots (same crypto, many param variants)
SHADOW_LAB_ENABLED = _env_bool("SHADOW_LAB_ENABLED", True)
SHADOW_CLONES_PER_MARKET = 12       # 12 mocks × N markets
SHADOW_BALANCE = 500.0              # virtual $ per clone
SHADOW_EVAL_SEC = int(os.environ.get("SHADOW_EVAL_SEC", "300"))  # 5 min — less noise
SHADOW_PARAM_JITTER = 0.18          # random extra variation
SHADOW_MIN_TRADES_PROMOTE = int(os.environ.get("SHADOW_MIN_TRADES_PROMOTE", "8"))
SHADOW_PROMOTE_MARGIN = 0.35        # must beat live by this many pp vs hold

PRICE_DECIMALS = {
    "BTC": 0, "ETH": 2, "SOL": 2, "BNB": 2,
    "XRP": 4, "ADA": 4, "AVAX": 2, "LINK": 3, "ARB": 4,
    "SUI": 4, "NEAR": 3, "DOT": 3, "INJ": 3, "TON": 3,
    "DOGE": 4, "PEPE": 8, "WIF": 4,
}

EXCHANGE_MAX_POSITION_PCT = 0.25
EXCHANGE_SYNC_TO_PAPER = _env_bool("EXCHANGE_SYNC_TO_PAPER", True)
EXCHANGE_SYNC_FROM_PAPER = _env_bool("EXCHANGE_SYNC_FROM_PAPER", False)

AUTO_TACTICS_ENABLED = _env_bool("AUTO_TACTICS_ENABLED", True)
AUTO_TACTICS_MIN_INTERVAL_SEC = int(os.environ.get("AUTO_TACTICS_MIN_INTERVAL_SEC", "1200"))
AUTO_TACTICS_MIN_MARGIN = float(os.environ.get("AUTO_TACTICS_MIN_MARGIN", "1.5"))
AUTO_TACTICS_MIN_TRADES = int(os.environ.get("AUTO_TACTICS_MIN_TRADES", "2"))
AUTO_TRADER_COPY_ENABLED = _env_bool("AUTO_TRADER_COPY_ENABLED", True)
AUTO_TRADER_MIN_CONFIDENCE = float(os.environ.get("AUTO_TRADER_MIN_CONFIDENCE", "0.68"))
AUTO_TACTICS_BACKTEST_ENABLED = _env_bool("AUTO_TACTICS_BACKTEST_ENABLED", True)
AUTO_TACTICS_BACKTEST_CANDLES = int(os.environ.get("AUTO_TACTICS_BACKTEST_CANDLES", "200"))
AUTO_TACTICS_BACKTEST_MIN_EDGE = float(os.environ.get("AUTO_TACTICS_BACKTEST_MIN_EDGE", "0.3"))

# Shadow Lab walk-forward OOS gate (v27)
SHADOW_WALKFORWARD_ENABLED = _env_bool("SHADOW_WALKFORWARD_ENABLED", True)
SHADOW_WALKFORWARD_MIN_CANDLES = int(os.environ.get("SHADOW_WALKFORWARD_MIN_CANDLES", "80"))
SHADOW_WALKFORWARD_TRAIN_RATIO = float(os.environ.get("SHADOW_WALKFORWARD_TRAIN_RATIO", "0.7"))
SHADOW_WALKFORWARD_MIN_EDGE = float(os.environ.get("SHADOW_WALKFORWARD_MIN_EDGE", "0.3"))

# Correlation risk — block buys when many markets fall together
CORRELATION_RISK_ENABLED = _env_bool("CORRELATION_RISK_ENABLED", True)
CORRELATION_RISK_MOMENTUM_PCT = float(os.environ.get("CORRELATION_RISK_MOMENTUM_PCT", "0.8"))
CORRELATION_RISK_MIN_BEARISH = int(os.environ.get("CORRELATION_RISK_MIN_BEARISH", "8"))
CORRELATION_RISK_MIN_SYNC_PAIRS = int(os.environ.get("CORRELATION_RISK_MIN_SYNC_PAIRS", "10"))

# Candle sync — gap fill after restart (v29)
CANDLE_MAX_LAG_SEC = int(os.environ.get("CANDLE_MAX_LAG_SEC", "120"))
CANDLE_STARTUP_LIMIT = int(os.environ.get("CANDLE_STARTUP_LIMIT", "500"))
CANDLE_GAP_FETCH_LIMIT = int(os.environ.get("CANDLE_GAP_FETCH_LIMIT", "500"))
CANDLE_GAP_MAX_PAGES = int(os.environ.get("CANDLE_GAP_MAX_PAGES", "5"))
CANDLE_HEALTH_SEC = int(os.environ.get("CANDLE_HEALTH_SEC", "60"))
CANDLE_STARTUP_TIMEOUT_SEC = int(os.environ.get("CANDLE_STARTUP_TIMEOUT_SEC", "90"))

# Profit Focus — auto-pause losers, boost winners (v35)
PROFIT_FOCUS_ENABLED = _env_bool("PROFIT_FOCUS_ENABLED", True)
PROFIT_FOCUS_INTERVAL_SEC = int(os.environ.get("PROFIT_FOCUS_INTERVAL_SEC", "300"))
PROFIT_FOCUS_MIN_TRADES = int(os.environ.get("PROFIT_FOCUS_MIN_TRADES", "2"))
PROFIT_FOCUS_PAUSE_VS_HOLD = float(os.environ.get("PROFIT_FOCUS_PAUSE_VS_HOLD", "-2.0"))
PROFIT_FOCUS_PAUSE_PNL_PCT = float(os.environ.get("PROFIT_FOCUS_PAUSE_PNL_PCT", "-1.5"))
PROFIT_FOCUS_RESUME_VS_HOLD = float(os.environ.get("PROFIT_FOCUS_RESUME_VS_HOLD", "0.3"))
PROFIT_FOCUS_RESUME_PNL_PCT = float(os.environ.get("PROFIT_FOCUS_RESUME_PNL_PCT", "0.5"))
PROFIT_FOCUS_BOOST_MIN_VS_HOLD = float(os.environ.get("PROFIT_FOCUS_BOOST_MIN_VS_HOLD", "0.5"))
PROFIT_FOCUS_LEADER_MULT = float(os.environ.get("PROFIT_FOCUS_LEADER_MULT", "1.2"))
PROFIT_MAX_ON_START = _env_bool("PROFIT_MAX_ON_START", True)

# Capital allocator — tilt buy sizes to winners (v28)
CAPITAL_ALLOCATOR_ENABLED = _env_bool("CAPITAL_ALLOCATOR_ENABLED", True)
CAPITAL_ALLOCATOR_INTERVAL_SEC = int(os.environ.get("CAPITAL_ALLOCATOR_INTERVAL_SEC", "900"))
CAPITAL_ALLOCATOR_BOOST = float(os.environ.get("CAPITAL_ALLOCATOR_BOOST", "1.25"))
CAPITAL_ALLOCATOR_CUT = float(os.environ.get("CAPITAL_ALLOCATOR_CUT", "0.75"))
CAPITAL_ALLOCATOR_MIN_VS_HOLD = float(os.environ.get("CAPITAL_ALLOCATOR_MIN_VS_HOLD", "0.5"))

# Strategy switch outcome tracking (v28)
STRATEGY_OUTCOME_EVAL_SEC = int(os.environ.get("STRATEGY_OUTCOME_EVAL_SEC", "7200"))
EXCHANGE_PNL_SNAPSHOT_SEC = int(os.environ.get("EXCHANGE_PNL_SNAPSHOT_SEC", "300"))

# Trade frequency — normal | active (shorter cooldowns, more signals)
TRADE_MODE = os.environ.get("TRADE_MODE", "active").lower()
ACTIVE_TRADE_ON_START = _env_bool("ACTIVE_TRADE_ON_START", True)
ACTIVE_TRADE_RESET_TIMERS = _env_bool("ACTIVE_TRADE_RESET_TIMERS", False)

APP_VERSION = 49

# Limit orders (v49)
LIMIT_ORDERS_ENABLED = _env_bool("LIMIT_ORDERS_ENABLED", True)

# v47 — Telegram + TradingView + Protections
TELEGRAM_ENABLED = _env_bool("TELEGRAM_ENABLED", False)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_ALLOWED_USER_IDS = [
    int(x.strip()) for x in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if x.strip().isdigit()
]
TELEGRAM_ALERT_TRADES = _env_bool("TELEGRAM_ALERT_TRADES", True)
TELEGRAM_ALERT_HALT = _env_bool("TELEGRAM_ALERT_HALT", True)
TELEGRAM_ALERT_SYNC_FAIL = _env_bool("TELEGRAM_ALERT_SYNC_FAIL", True)
TELEGRAM_DAILY_SUMMARY = _env_bool("TELEGRAM_DAILY_SUMMARY", True)
TELEGRAM_COMMANDS_ENABLED = _env_bool("TELEGRAM_COMMANDS_ENABLED", True)

TRADINGVIEW_WEBHOOK_ENABLED = _env_bool("TRADINGVIEW_WEBHOOK_ENABLED", False)
TRADINGVIEW_WEBHOOK_SECRET = os.environ.get("TRADINGVIEW_WEBHOOK_SECRET", "")
TRADINGVIEW_DEFAULT_SIZE_USD = float(os.environ.get("TRADINGVIEW_DEFAULT_SIZE_USD", "10"))
TRADINGVIEW_MAX_SIZE_USD = float(os.environ.get("TRADINGVIEW_MAX_SIZE_USD", "50"))

PROTECTIONS_ENABLED = _env_bool("PROTECTIONS_ENABLED", True)
PROTECTION_STOPLOSS_COUNT = int(os.environ.get("PROTECTION_STOPLOSS_COUNT", "3"))
PROTECTION_STOPLOSS_WINDOW_SEC = int(os.environ.get("PROTECTION_STOPLOSS_WINDOW_SEC", "86400"))
PROTECTION_STOPLOSS_PAUSE_SEC = int(os.environ.get("PROTECTION_STOPLOSS_PAUSE_SEC", "14400"))
PROTECTION_COOLDOWN_LOSSES = int(os.environ.get("PROTECTION_COOLDOWN_LOSSES", "5"))
PROTECTION_COOLDOWN_WINDOW_SEC = int(os.environ.get("PROTECTION_COOLDOWN_WINDOW_SEC", "3600"))
PROTECTION_COOLDOWN_PAUSE_SEC = int(os.environ.get("PROTECTION_COOLDOWN_PAUSE_SEC", "1800"))
PROTECTION_MAX_TRADES_PER_DAY = int(os.environ.get("PROTECTION_MAX_TRADES_PER_DAY", "0"))
PROTECTION_MAX_TRADES_PAUSE_SEC = int(os.environ.get("PROTECTION_MAX_TRADES_PAUSE_SEC", "3600"))

# Live Micro — first real money ($10–15, rare trades)
LIVE_MICRO_MODE = _env_bool("LIVE_MICRO_MODE", False)
LIVE_MICRO_ORDER_USD = float(os.environ.get("LIVE_MICRO_ORDER_USD", "10"))
LIVE_MICRO_DCA_HOURS = float(os.environ.get("LIVE_MICRO_DCA_HOURS", "12"))
LIVE_MICRO_DIP_COOLDOWN_MIN = float(os.environ.get("LIVE_MICRO_DIP_COOLDOWN_MIN", "45"))
LIVE_MICRO_TAKE_PROFIT_PCT = float(os.environ.get("LIVE_MICRO_TAKE_PROFIT_PCT", "2.5"))
LIVE_MICRO_MAX_TRADES_PER_DAY = int(os.environ.get("LIVE_MICRO_MAX_TRADES_PER_DAY", "3"))

# Live trading prep — gate real money (v36)
LIVE_REQUIRE_READINESS = _env_bool("LIVE_REQUIRE_READINESS", True)
LIVE_BYPASS_READINESS = _env_bool("LIVE_BYPASS_READINESS", False)
LIVE_MIN_DAYS_PAPER = float(os.environ.get("LIVE_MIN_DAYS_PAPER", "2"))
LIVE_MIN_DAYS_TESTNET = float(os.environ.get("LIVE_MIN_DAYS_TESTNET", "3"))
LIVE_MIN_TRADES = int(os.environ.get("LIVE_MIN_TRADES", "30"))
LIVE_MIN_PNL_PCT = float(os.environ.get("LIVE_MIN_PNL_PCT", "-2.0"))
LIVE_MIN_VS_HOLD = float(os.environ.get("LIVE_MIN_VS_HOLD", "0.0"))
LIVE_MAX_DRAWDOWN_PCT = float(os.environ.get("LIVE_MAX_DRAWDOWN_PCT", "8.0"))
LIVE_MAX_ORDER_USD = float(os.environ.get("LIVE_MAX_ORDER_USD", "25"))
LIVE_MAX_DAILY_LOSS_PCT = float(os.environ.get("LIVE_MAX_DAILY_LOSS_PCT", "3"))
LIVE_MAX_POSITION_PCT = float(os.environ.get("LIVE_MAX_POSITION_PCT", "0.10"))

# Security — default localhost; cloud preview needs TRADESIM_BIND_HOST=0.0.0.0
def _default_bind_host() -> str:
    if os.environ.get("TRADESIM_BIND_HOST"):
        return os.environ["TRADESIM_BIND_HOST"]
    # Cursor Cloud / port-forward preview
    if any(os.environ.get(k) for k in ("PORT", "CURSOR_AGENT", "CURSOR_TRACE_ID")):
        return "0.0.0.0"
    return "127.0.0.1"


BIND_HOST = _default_bind_host()
API_TOKEN = os.environ.get("TRADESIM_API_TOKEN", "")

# Live exchange (optional — set env BINANCE_API_KEY + BINANCE_API_SECRET + EXCHANGE_ENABLED=true)
EXCHANGE_ENABLED = os.environ.get("EXCHANGE_ENABLED", "false").lower() in ("1", "true", "yes")
EXCHANGE_NAME = "binance"
EXCHANGE_TESTNET = os.environ.get("EXCHANGE_TESTNET", "true").lower() in ("1", "true", "yes")
EXCHANGE_MAX_ORDER_USD = float(os.environ.get("EXCHANGE_MAX_ORDER_USD", "100"))
EXCHANGE_MAX_DAILY_LOSS_PCT = float(os.environ.get("EXCHANGE_MAX_DAILY_LOSS_PCT", "5"))

# Wallet bridge — bots use exchange USDT on testnet/live via wallet_credit
WALLET_BRIDGE_ENABLED = os.environ.get("WALLET_BRIDGE_ENABLED", "true").lower() in ("1", "true", "yes")
WALLET_BRIDGE_INTERVAL_SEC = int(os.environ.get("WALLET_BRIDGE_INTERVAL_SEC", "45"))
EXCHANGE_MAX_WITHDRAW_USD = float(os.environ.get("EXCHANGE_MAX_WITHDRAW_USD", "500"))
EXCHANGE_DEPOSIT_NETWORK = os.environ.get("EXCHANGE_DEPOSIT_NETWORK", "TRC20")
EXCHANGE_WITHDRAW_NETWORK = os.environ.get("EXCHANGE_WITHDRAW_NETWORK", "TRC20")

# Trading mode default: paper | testnet | live (runtime override in data/trading_mode.json)
TRADING_MODE_DEFAULT = os.environ.get("TRADING_MODE_DEFAULT", "paper").lower()
AUTO_APPLY_TRADING_MODE_ON_START = _env_bool("AUTO_APPLY_TRADING_MODE_ON_START", False)
LIVE_ALLOW_FORCE = _env_bool("LIVE_ALLOW_FORCE", False)
