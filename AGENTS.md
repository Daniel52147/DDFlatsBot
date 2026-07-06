# AGENTS.md

## Cursor Cloud specific instructions

This is a multi-product Python monorepo (Python 3.12 is available in the cloud VM; `runtime.txt` pins 3.11 for Render deploys). Dependencies install into the system `dist-packages` via `pip3` (no `python3-venv` in the image, so avoid `python -m venv`).

Products:
- `TradeSim/` — FastAPI paper-trading web app (BTC/USDT). This is the primary locally-runnable service; no API keys or external services required.
- `DDFlatsBot/` and root (`main.py`) — Warsaw flats Telegram bot.
- `FlightsBot/` — SkyCheap flights Telegram bot.

### TradeSim (run/build/lint/test)
- Run (dev): `cd TradeSim && python3 main.py` → serves on `http://localhost:8765` (host `0.0.0.0`, no reload). See `TradeSim/README.md`.
- No build step (server-rendered Jinja2 + static JS/CSS). No lint config or automated test suite exists; use `python3 -m py_compile` for a quick syntax check.
- SQLite DB (`TradeSim/data/tradesim.db`) is auto-created on startup; no DB server needed.
- Network gotcha: `api.binance.com` returns HTTP 451 from this VM. The feed code automatically falls back to `api.binance.us` (and to synthetic candles if both fail), so live data still works — the `451` warnings in logs are expected and non-fatal.

### Telegram bots (DDFlatsBot / FlightsBot / root)
- Require a valid `BOT_TOKEN` env var and outbound access to Telegram to run end-to-end; they default to long-polling (no inbound port). Not runnable end-to-end without a token.
- Install deps per project: `pip3 install -r requirements.txt` inside the relevant directory (root, `DDFlatsBot/`, `FlightsBot/` each have their own).
- Root deps include `primp`/`selectolax`/`fast-flights` which download prebuilt wheels; these are heavier than TradeSim's pure-Python stack.
