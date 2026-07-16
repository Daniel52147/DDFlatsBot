# AGENTS.md

## Cursor Cloud specific instructions

Python 3.12 on the cloud VM (`runtime.txt` pins 3.11 for Render). Dependencies via `pip3` (no venv required).

### TradeSim (`TradeSim/`)

- **17 markets**: BTC, ETH, SOL, BNB + 10 growth alts + DOGE, PEPE + WIF
- **12 brain agents** (coordinator + trader watcher)
- Run: `cd TradeSim && python3 main.py` → http://127.0.0.1:8765 (default bind localhost)
- **Tests**: `cd TradeSim && python3 -m pytest tests/ -v` (CI: `.github/workflows/tradesim-tests.yml`)
- **Security**: set `TRADESIM_API_TOKEN` before binding `0.0.0.0`; write APIs need header `X-API-Token`
- SQLite: `TradeSim/data/tradesim.db` (WAL, `busy_timeout=30s`)
- **Binance geo-block (451)**: feed falls back to binance.us / Bybit / CoinGecko — expected on some VMs
- **SSL**: `certifi` or `TRADESIM_INSECURE_SSL=1` (`simulator/ssl_util.py`)

### Other products

- `DDFlatsBot/`, `FlightsBot/`, root `main.py` — Telegram bots (need `BOT_TOKEN`)
