# TradeSim v23

**Paper trading** with **bidirectional testnet sync**, **FeedHub REST fallback**, and **automatic per-coin tactics**.

## v23 — Sync + FeedHub

- **FeedHub REST fallback** — when multiplex WebSocket fails, polls via Bybit/Kraken/Coingecko (same chain as `PriceFeed`)
- **Paper → exchange sync** — bot/manual paper trades mirror to testnet when `EXCHANGE_SYNC_FROM_PAPER=true` (opt-in, default `false`)
- **No sync loops** — exchange-originated fills skip paper→exchange; paper-originated orders skip paper re-sync (`from_paper_sync`)
- **Shared strategy presets** — `learning/strategy_presets.py` used by API and auto-tactics (no duplicate tables)

| Setting | Default | Direction |
|---------|---------|-----------|
| `EXCHANGE_SYNC_TO_PAPER` | true | testnet → paper |
| `EXCHANGE_SYNC_FROM_PAPER` | false | paper → testnet (opt-in) |

## v22 — Polish

- **Mirror fix** — `sync-paper` deducts USDT when aligning base (no portfolio inflation)
- **Sync warnings** — exchange order can succeed while paper sync fails (UI + API `warning`)
- **Auto-tactics panel** — sidebar shows last switches and trader plays
- **Strategy-aware status** — bot card shows Grid/Momentum/RSI/Scalper params, not only DCA
- **Testnet buttons hidden** in pure paper mode (`EXCHANGE_ENABLED=false`)
- **Config env** — `AUTO_TACTICS_*` overridable like `EXCHANGE_SYNC_TO_PAPER`

## v21 — Exchange → Paper sync

Testnet fills mirror into the paper wallet (one-way: exchange → paper):

| Setting | Default | Meaning |
|---------|---------|---------|
| `EXCHANGE_SYNC_TO_PAPER` | true | Auto-sync after `POST /api/exchange/order` |
| `EXCHANGE_ENABLED` | false | Enable Binance testnet |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | — | Testnet credentials |

Manual mirror: `POST /api/exchange/sync-paper?symbol=BTCUSDT` or **🔗 Sync paper** button.

Paper bot trades do **not** go to the exchange unless `EXCHANGE_SYNC_FROM_PAPER=true`.

## v20 — Auto Tactics

The brain (every 45s) automatically:

1. **Picks strategy per coin** — DCA / Grid / Momentum / RSI / Scalper based on trend, volatility, vs-hold performance
2. **Copies popular traders** — when confidence ≥68%, applies Ansem/PlanB/Hsaka/etc. style to matching coins
3. **Resets Shadow Lab** clones after each switch
4. **Persists** all changes to SQLite

Config (`config.py` or env):

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

## Features

- **17 parallel bots** + **12 brain agents** + Shadow Lab
- **FeedHub** — one multiplexed Binance WebSocket; hot-add via `POST /api/sync-markets`
- **Persistence** — SQLite WAL, `bot_state` column, full trade history
- **Backtest** — compare all 5 strategies on same candles
- **Exchange panel** — balances + per-market base reconcile in UI
- **JSON health** — `GET /api/health`
- **Docker** — `docker compose up`
- **50+ unit/API tests** + GitHub Actions CI

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

## API

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/health` | — | JSON status (version, markets, portfolio) |
| `GET /health` | — | HTML health page |
| `GET /api/ping` | — | Version, markets, `auth_required` |
| `GET /api/bootstrap` | — | Full UI payload (includes `auto_tactics`) |
| `GET /api/trades` | — | SQLite trade history |
| `GET /api/auto-tactics` | — | Auto strategy + trader copy status |
| `POST /api/backtest` | token* | Historical strategy run |
| `POST /api/backtest/compare` | token* | Compare 5 strategies |
| `POST /api/deposit` | token* | Paper top-up |
| `POST /api/sync-markets` | token* | Hot-add new markets + FeedHub |
| `POST /api/market/sync-strategy` | token* | Re-apply config strategy + refresh feed |
| `POST /api/shadow-lab/reset` | token* | Reset shadow clones |
| `GET /api/exchange/status` | — | Exchange enabled/testnet flags |
| `GET /api/exchange/balances` | — | Exchange wallet balances |
| `GET /api/exchange/reconcile` | — | Paper base vs exchange (per symbol) |
| `POST /api/exchange/order` | token* | Testnet market order (+ optional paper sync) |
| `POST /api/exchange/sync-paper` | token* | Mirror exchange base into paper |
| `GET /api/shadow-lab` | — | Shadow Lab status |

\* Required when `TRADESIM_API_TOKEN` is set (header `X-API-Token`).
