# TradeSim v20 Auto

**Paper trading** with **automatic per-coin tactics** and **popular trader idea copying**.

## v20 — Auto Tactics

The brain (every 45s) automatically:

1. **Picks strategy per coin** — DCA / Grid / Momentum / RSI / Scalper based on trend, volatility, vs-hold performance
2. **Copies popular traders** — when confidence ≥68%, applies Ansem/PlanB/Hsaka/etc. style to matching coins
3. **Resets Shadow Lab** clones after each switch
4. **Persists** all changes to SQLite

Config (`config.py`):

| Setting | Default | Meaning |
|---------|---------|---------|
| `AUTO_TACTICS_ENABLED` | true | Heuristic auto strategy pick |
| `AUTO_TRADER_COPY_ENABLED` | true | Copy trader ideas |
| `AUTO_TACTICS_MIN_INTERVAL_SEC` | 1200 | Cooldown per market (20 min) |
| `AUTO_TRADER_MIN_CONFIDENCE` | 0.68 | Min confidence to copy trader |

API: `GET /api/auto-tactics` — status, trader plays, copy candidates.

Chat: ask **авто**, **трейдеры**, **тактики**.

## Markets (17)

| Tier | Coins | Default strategy |
|------|-------|------------------|
| **Majors** | BTC, ETH, BNB | DCA |
| **Majors** | SOL | Momentum |
| **Growth** | XRP, ADA, AVAX, ARB, SUI, TON | Grid |
| **Growth** | LINK, INJ | DCA / Momentum |
| **Growth** | NEAR, DOT | Scalper |
| **Meme** | DOGE, PEPE | RSI |
| **Viral** | WIF | Momentum |

## Strategies (5)

| Type | Description |
|------|-------------|
| **DCA** | Planned buys + DIP below SMA + SPIKE + take-profit |
| **Grid** | Buy/sell on grid levels vs SMA |
| **Momentum** | Breakout entry + trailing stop |
| **RSI** | Mean-reversion on RSI oversold/overbought |
| **Scalper** | Micro-moves with tight TP (NEAR, DOT) |

## Features (v19)

- **FeedHub dedupe** — no duplicate ticks when syncing strategy/markets
- **Shadow resync** — clones rebuild when live strategy type changes
- **Brain persist** — micro-tunes from brain cycle saved to SQLite
- **Strategy presets** — aggressive/balanced/conservative per strategy type
- **17 parallel bots** + **12 brain agents** + Shadow Lab
- **FeedHub** — one multiplexed Binance WebSocket; hot-add via `POST /api/sync-markets`
- **Persistence** — SQLite WAL, `bot_state` column, full trade history
- **Backtest** — compare all 5 strategies on same candles
- **Exchange panel** — balances + per-market base reconcile in UI
- **JSON health** — `GET /api/health`
- **Docker** — `docker compose up`
- **30+ unit/API tests** + GitHub Actions CI

## Quick start

```bash
cd TradeSim
python -m pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:8765

### Docker

```bash
cd TradeSim
docker compose up --build
```

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
| `GET /api/health` | — | JSON status (version, markets, portfolio) |
| `GET /health` | — | HTML health page |
| `GET /api/ping` | — | Version, markets, `auth_required` |
| `GET /api/bootstrap` | — | Full UI payload |
| `GET /api/trades` | — | SQLite trade history |
| `POST /api/backtest` | token* | Historical strategy run |
| `POST /api/backtest/compare` | token* | Compare 5 strategies |
| `POST /api/deposit` | token* | Paper top-up |
| `POST /api/sync-markets` | token* | Hot-add new markets + FeedHub |
| `POST /api/market/sync-strategy` | token* | Re-apply config strategy + refresh feed |
| `POST /api/shadow-lab/reset` | token* | Reset shadow clones |
| `GET /api/exchange/balances` | — | Exchange wallet balances |
| `GET /api/exchange/reconcile` | — | Paper base vs exchange (per symbol) |
| `GET /api/shadow-lab` | — | Shadow Lab status |

\* Required when `TRADESIM_API_TOKEN` is set (header `X-API-Token`).

## Tests

```bash
cd TradeSim && python3 -m pytest tests/ -v
```

## Windows

See [WINDOWS.md](WINDOWS.md) for setup notes.
