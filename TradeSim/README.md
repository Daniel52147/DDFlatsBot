# TradeSim

**Paper trading** simulator: **17 crypto markets**, virtual $10,000, live prices, self-learning bots.

## Markets (17)

| Tier | Coins | Strategy |
|------|-------|----------|
| **Majors** | BTC, ETH, SOL, BNB | DCA $25 / 24h + DIP |
| **Growth** | XRP, ADA, AVAX, LINK, ARB, SUI, NEAR, DOT, INJ, TON | Faster DCA + SPIKE + TP |
| **Meme** | DOGE, PEPE | Aggressive volatile params |
| **Viral** | WIF (dogwifhat) | Ultra-fast trending slot |

## Features

- **17 parallel bots** + **12 brain agents** + Shadow Lab (12 clones × 17 markets)
- **Persistence** — SQLite WAL, full trade history, restore after restart
- **Backtest** — OHLC replay in minutes (`POST /api/backtest`)
- **Security** — `TRADESIM_API_TOKEN` for write APIs; default bind `127.0.0.1`
- **Optional Binance testnet** — `BINANCE_API_KEY` + `EXCHANGE_ENABLED=true`
- **13+ unit tests** + GitHub Actions CI

## Quick start

```bash
cd TradeSim
pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:8765

### Remote / production

```bash
export TRADESIM_API_TOKEN="your-secret-token"
export TRADESIM_BIND_HOST="0.0.0.0"   # only with token set
python main.py
```

UI: enter token in footer field → 🔐

### Binance testnet (optional)

```bash
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
export EXCHANGE_ENABLED=true
```

Paper bot and exchange are **separate** — testnet orders via 🏦 button or `POST /api/exchange/order`.

## API

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/ping` | — | Version, markets, `auth_required` |
| `GET /api/bootstrap` | — | Full UI payload |
| `GET /api/trades` | — | SQLite trade history |
| `GET /api/export/trades` | — | Export up to 5000 trades |
| `GET /api/candles` | — | OHLC for charts |
| `POST /api/backtest` | token* | Historical strategy run |
| `POST /api/deposit` | token* | Paper top-up |
| `POST /api/trade` | token* | Manual paper trade |
| `POST /api/reset` | token* | Portfolio / full DB reset |
| `POST /api/sync-markets` | token* | Hot-add new markets |
| `POST /api/assistant/chat` | token* | Chat |
| `GET /api/exchange/status` | — | Paper / testnet mode |
| `POST /api/exchange/order` | token* | Testnet market order |
| `GET /api/exchange/reconcile` | — | Paper vs exchange balance |
| `GET /api/learning/honesty` | — | What really learns |
| `GET /api/shadow-lab` | — | Shadow Lab status |

\* Required when `TRADESIM_API_TOKEN` is set (header `X-API-Token`).

## Tests

```bash
cd TradeSim && python3 -m pytest tests/ -v
```

## Stack

Python · FastAPI · SQLite WAL · Lightweight Charts · Binance/Bybit feeds
