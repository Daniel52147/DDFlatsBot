# AGENTS.md

## Cursor Cloud specific instructions

This is a multi-product Python monorepo (Python 3.12 is available in the cloud VM; `runtime.txt` pins 3.11 for Render deploys). Dependencies install into the system `dist-packages` via `pip3` (no `python3-venv` in the image, so avoid `python -m venv`).

Products:
- `TradeSim/` — FastAPI paper-trading web app (6 crypto pairs: BTC, ETH, SOL, BNB, DOGE, PEPE). Primary locally-runnable service; no API keys required. Real prices via public exchange APIs.
- `DDFlatsBot/` and root (`main.py`) — Warsaw flats Telegram bot.
- `FlightsBot/` — SkyCheap flights Telegram bot.

### TradeSim (run/build/lint/test)
- Run (dev): `cd TradeSim && python3 main.py` → serves on `http://localhost:8765` (host `0.0.0.0`, no reload). Windows: `start.bat` (git pull + launch). See `TradeSim/README.md`.
- No build step (server-rendered Jinja2 + static JS/CSS). No lint config or automated test suite exists; use `python3 -m py_compile` for a quick syntax check.
- SQLite DB (`TradeSim/data/tradesim.db`) is auto-created on startup; no DB server needed.
- **Market data fallback** (`TradeSim/simulator/feed.py`): per-symbol `PriceFeed` tries sources in order — Binance REST/WS → Binance US → Bybit → Kraken → CoinGecko → REST poll → synthetic candles from last live price. No API keys.
- **Network gotcha (Cursor Cloud VM):** `api.binance.com` returns HTTP **451** (geo-block). The feed detects this once, logs a single info line, then skips `binance.com` for the rest of the session and prefers `api.binance.us`. This is expected and non-fatal.
- **Windows SSL:** if `CERTIFICATE_VERIFY_FAILED`, install `certifi` (`pip install certifi`) or set `TRADESIM_INSECURE_SSL=1`. `simulator/ssl_util.py` auto-retries without verify after the first SSL failure.

### Telegram bots (DDFlatsBot / FlightsBot / root)
- Require a valid `BOT_TOKEN` env var and outbound access to Telegram to run end-to-end; they default to long-polling (no inbound port). Not runnable end-to-end without a token.
- Install deps per project: `pip3 install -r requirements.txt` inside the relevant directory (root, `DDFlatsBot/`, `FlightsBot/` each have their own).
- Root deps include `primp`/`selectolax`/`fast-flights` which download prebuilt wheels; these are heavier than TradeSim's pure-Python stack.
