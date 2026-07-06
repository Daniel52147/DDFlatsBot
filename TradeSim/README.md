# TradeSim

**Paper trading** simulator: real BTC/USDT prices from Binance, virtual $10,000 wallet.

## What it does

- **Live market data** — WebSocket + REST fallback from Binance (no API key)
- **Virtual wallet** — fees 0.1%, slippage 0.05%
- **One niche bot** — DCA every 24h + extra buy when price dips below SMA
- **Candlestick chart** — real-time 1m candles + SMA-20
- **Learning** — logs trades, snapshots; auto-tunes dip threshold vs buy-and-hold
- **Assistant** — explains candles, bot actions, learning tips (Russian)

## Quick start

```bash
cd TradeSim
pip install -r requirements.txt
python main.py
```

Open http://localhost:8765

### Windows SSL error (`CERTIFICATE_VERIFY_FAILED`)

If APIs fail on Windows Python 3.13:

```powershell
python -m pip install certifi
python main.py
```

Or enable local workaround (paper trading only):

```powershell
$env:TRADESIM_INSECURE_SSL="1"
python main.py
```

The app also auto-retries without SSL verify after the first SSL failure.

## Monetization path (later)

- Subscription for alerts + paper accounts
- Premium strategy packs
- REST API access
- Telegram bot integration (same stack as your other bots)

## Stack

Python · FastAPI · SQLite · Lightweight Charts · Binance public API
