# TradeSim

**Paper trading** simulator: 6 crypto markets, virtual $10,000, live prices, self-learning bots.

## Markets

| Pair | Type | Strategy |
|------|------|----------|
| BTC, ETH, SOL, BNB | Majors | DCA $25 / 24h + DIP below SMA |
| DOGE, PEPE | Volatile | Smaller DCA, shorter interval, SPIKE buys on deep dips |

Each market gets ~$1,667 virtual balance.

## Features

- **Live data** — Binance / Bybit / CoinGecko fallback (no API key)
- **6 parallel bots** — DCA + DIP + SPIKE (memecoins)
- **Central brain** — 5 agents: Наставник, Новостник, Исследователь, Волатильность, Риск
- **Learning** — SQLite logs trades, snapshots, auto-tuning
- **Chat assistant** — Russian Q&A (`помощь`, `как дела?`, `что с DOGE?`)
- **Web UI** — candlestick chart, portfolio grid, agent details

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

## Stack

Python · FastAPI · SQLite · Lightweight Charts · Multi-source crypto feeds
