# TradeSim

**Paper trading** simulator: **17 crypto markets**, virtual $10,000, live prices, self-learning bots.

## Markets (17)

| Tier | Coins | Strategy |
|------|-------|----------|
| **Majors** | BTC, ETH, SOL, BNB | DCA $25 / 24h + DIP |
| **Growth** | XRP, ADA, AVAX, LINK, ARB, SUI, NEAR, DOT, INJ, TON | Faster DCA + SPIKE + TP |
| **Meme** | DOGE, PEPE | Aggressive volatile params |
| **🔥 Viral** | WIF (dogwifhat) | Ultra-fast — trending coin slot |

Each market gets ~$588 virtual balance ($10k ÷ 17).

## Features

- **Live data** — Binance / Bybit / CoinGecko fallback (no API key)
- **17 parallel bots** — majors + 10 growth alts + memes + viral WIF
- **Persistence** — portfolio, trades, bot params survive server restart (SQLite WAL)
- **Shadow Lab** — 12 hidden mock bots per market (72 total) learn in parallel; winners promote to live bot
- **Central brain** — 11 agents with emergency halt and decision history
- **Analytics** — drawdown, Sharpe proxy, win rate, per-market breakdown
- **Manual paper trades** — buy/sell $25 from UI
- **Export** — JSON download of all trades; full DB reset option
- **Learning dashboard** — equity curve, activity feed, auto-tuning log
- **Chat assistant** — Russian Q&A (11 agents, analytics, stop-loss)

## Quick start

```bash
cd TradeSim
pip install -r requirements.txt
python main.py
```

Open http://localhost:8765

### Windows

```powershell
cd TradeSim
python -m pip install -r requirements.txt
python main.py
```

Or double-click `start.bat` (git pull + launch).

### SSL error (`CERTIFICATE_VERIFY_FAILED`)

```powershell
python -m pip install certifi
python main.py
```

Or: `$env:TRADESIM_INSECURE_SSL="1"`

## API

| Endpoint | Description |
|----------|-------------|
| `GET /api/bootstrap` | Full UI payload |
| `GET /api/ping` | Version + markets |
| `GET /api/brain` | Central brain cycle |
| `POST /api/assistant/chat` | Chat |
| `GET /api/learning/summary` | DB learning stats |
| `GET /api/learning/equity` | Portfolio equity curve |
| `GET /api/brain/history` | Recent brain decisions |

## Stack

Python · FastAPI · SQLite · Lightweight Charts · Multi-source crypto feeds
