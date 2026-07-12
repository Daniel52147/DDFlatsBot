# TradeSim v40

**Security & audit fixes** — Live gate, honest drawdown, sync integrity, API consistency.

## v40 — Security & audit fixes

- **Live gate** — `force:true` работает только с `LIVE_ALLOW_FORCE=true` в `.env`
- **Auth** — `/api/trading-mode`, week-prep, paper-learn, active защищены `TRADESIM_API_TOKEN`
- **Drawdown** — просадка считается от пика **всего портфеля** (equity curve)
- **Exchange risk** — дневной стоп по P&L портфеля, не одного рынка
- **Paper sync** — `ok:false` при расхождении кошельков
- **Defaults** — `TRADING_MODE_DEFAULT=paper`, без авто-Testnet при старте

## v39 — Paper Learn (faster training)

**Paper Learn** — on 📄 Paper mode: max trades, faster optimizer, no profit-focus pause.

- **Paper only** — DCA ≤1.5h, scalp cooldown 20s, grid 3min
- **Auto on boot** when mode is Paper (`PAPER_LEARN_ON_START=true`)
- **`POST /api/strategy/paper-learn`** + UI **📚 Paper учёба**
- **Learning** — tune after 2 trades (was 5), fast retune every 2 trades
- **No blocks in Paper** — correlation block off, profit-focus pause off
- **Testnet/Live** — unchanged (safer limits)

| Setting | Paper | Testnet/Live |
|---------|-------|--------------|
| DCA interval | ≤1.5h | 8h+ active |
| Scalp cooldown | 20s | 45s+ |
| Min trades to tune | 2 | 5 |
| Profit focus pause | off | on |

## v38 — vs Hold fix

- **Candle anchor** — hold baseline = oldest loaded 1m candle (~8h), not `start_price` from months ago
- **Per-market vs Hold** — ETH +46% / WIF +92% artifacts fixed via `benchmark_hold_price`
- **Equity curve hold** — new snapshots use corrected hold (~$10k not ~$4k)
- **1970 dates** — `strategy_versions` now includes `ts` in learning panel
- **Banner** — warns when vs Hold was misleading

## v37 — Fixes + week to Live

- **Honest vs Hold** — uses candle anchor when no trades; flags misleading +58% vs −0.04% P&L cases
- **Auto Testnet** — `TRADING_MODE_DEFAULT=testnet` when `EXCHANGE_ENABLED` + keys
- **`POST /api/week-prep/start`** — one click: active trading + Testnet mode
- **UI** — `🚀 Неделя Testnet` button, vs Hold warning in header
- **Live readiness** — blocks Live if vs Hold is misleading

## v36 — Live Prep (7 days to real money)

- **Live Readiness** — `GET /api/live-readiness` scores paper/testnet history before Live
- **Live gate** — `POST /api/trading-mode` blocks Live until checks pass (`LIVE_REQUIRE_READINESS=true`)
- **Stricter Live limits** — $25/order, 3% daily stop, 10% max position (separate from testnet $100)
- **7-day plan UI** — sidebar checklist: Paper → Testnet → stability → Live
- **vs Hold warning** — explains when high vs_hold is cash vs crashed hold, not profit

| Setting | Default | Meaning |
|---------|---------|---------|
| `LIVE_MIN_DAYS_TESTNET` | 3 | Min days on testnet before Live |
| `LIVE_MIN_TRADES` | 30 | Min trades in DB |
| `LIVE_MAX_ORDER_USD` | 25 | Max order on Live |
| `LIVE_REQUIRE_READINESS` | true | Block Live without checks |
| `LIVE_BYPASS_READINESS` | false | Emergency override (dangerous) |

### Week plan

| Days | Action |
|------|--------|
| 1–2 | Paper on v36, watch vs Hold and trades |
| 3–4 | Switch to 🧪 Testnet, small orders |
| 5–6 | ≥30 trades, stable P&L, Profit Focus OK |
| 7 | Live only if readiness 100% + `EXCHANGE_TESTNET=false` |

## v35 — Profit Focus

- **ProfitFocusEngine** — every 5 min reviews all markets; pauses bots with vs_hold ≤ -2% and ≥2 trades; resumes on recovery
- **Leader boost** — top 25% vs-hold markets get `aggressive` preset + 1.2× buy size
- **Profit Max on start** — `PROFIT_MAX_ON_START=true` applies active trading profile on boot
- **Looser gates** — `REGIME_FILTER_ENABLED=false` by default; correlation bearish threshold 8; allocator boost 1.25
- **UI** — sidebar **💎 Profit Focus** panel; WS toasts on pause/resume/boost
- **`GET /api/profit-focus`** — leaders, laggards, paused bots, last actions

| Setting | Default | Meaning |
|---------|---------|---------|
| `PROFIT_FOCUS_ENABLED` | true | Auto pause/boost cycle |
| `PROFIT_FOCUS_PAUSE_VS_HOLD` | -2.0 | Pause bot if vs hold below this |
| `PROFIT_FOCUS_BOOST_MIN_VS_HOLD` | 0.5 | Min vs hold to qualify as leader |
| `PROFIT_FOCUS_LEADER_MULT` | 1.2 | Buy size multiplier for leaders |
| `PROFIT_MAX_ON_START` | true | Active trading + focus-friendly boot |
| `REGIME_FILTER_ENABLED` | false | Bear-market buy filter (off = more trades) |
| `AUTO_TACTICS_BACKTEST_MIN_EDGE` | 0.3 | Lower bar for strategy switches |

## v34 — Chart + exchange menu

- Brighter/taller chart (480px), trade markers on chart
- Paper / Testnet / Live menu with persisted mode
- `GET /api/exchange/verify` — connection check with clear 401/403/451 messages

## v33 — Chart + exchange menu (base)

- Brighter chart, buy/sell markers `▲$25` / `▼$18`
- `exchange/trading_mode.py` — Paper | Testnet | Live
- `POST/GET /api/trading-mode`, `GET /api/exchange/verify`

## v32 — Active trading

- `TRADE_MODE=active` — shorter cooldowns, more trades
- `POST /api/strategy/active` — UI button **📈 Больше сделок**

## v30 — Stronger candle sync

- **Blocking startup** — server loads & gap-fills all markets **before** trading loops start (up to 90s)
- **Paginated gap-fill** — up to 5 pages × 500 candles; Bybit fallback for `startTime`
- **Synthetic tail** — if APIs fail, builds current-minute candles from live price
- **UI** — ignores stale candles from `/api/status`; polls `/api/candles` until lag ≤ 2 min
- **Lag warning** — chart title shows hours+minutes when behind (not hidden after 1h)

| Setting | Default | Meaning |
|---------|---------|---------|
| `CANDLE_GAP_MAX_PAGES` | 5 | Paginated gap-fill rounds |
| `CANDLE_STARTUP_TIMEOUT_SEC` | 90 | Max boot wait for candles |

## v29 — Candle sync (fix lag after restart)

- **Parallel klines load** — all 17 markets fetch candles in parallel on startup (not sequential)
- **Gap-fill** — if last candle is >2 min behind clock, fetches missing candles via `startTime` API
- **Candle health loop** — every 60s detects stale charts and auto-refreshes
- **Tick timestamps** — live ticks use wall-clock time (not stale `last_update`)
- **UI** — always refreshes chart on market switch; shows lag warning in title
- **`GET /api/candles?refresh=1`** — force backfill + returns `candle_lag_sec`

| Setting | Default | Meaning |
|---------|---------|---------|
| `CANDLE_MAX_LAG_SEC` | 120 | Trigger gap-fill if older |
| `CANDLE_STARTUP_LIMIT` | 500 | Candles loaded on startup |
| `CANDLE_HEALTH_SEC` | 60 | Stale check interval |

## v28 — Allocator & testnet PnL

- **Testnet PnL dashboard** — `GET /api/exchange/pnl` compares exchange wallet vs paper; UI in exchange panel
- **Exchange snapshots** — logged every 5 min for 48h curve
- **Strategy outcomes** — tracks vs_hold before/after each strategy switch (auto + manual); `GET /api/strategy-outcomes`
- **Capital allocator** — top 25% vs-hold markets get +15% buy size; bottom laggards −15% (`CAPITAL_ALLOCATOR_*`)

| Setting | Default | Meaning |
|---------|---------|---------|
| `CAPITAL_ALLOCATOR_BOOST` | 1.15 | Buy size multiplier for leaders |
| `CAPITAL_ALLOCATOR_CUT` | 0.85 | Buy size cut for laggards |
| `STRATEGY_OUTCOME_EVAL_SEC` | 7200 | Hours before measuring switch outcome |
| `EXCHANGE_PNL_SNAPSHOT_SEC` | 300 | Exchange vs paper snapshot interval |

## v27 — Walk-forward & alpha report

- **Walk-forward Shadow Lab** — clone params promoted only if OOS backtest beats live (`SHADOW_WALKFORWARD_*`)
- **Strategy report** — `GET /api/strategy-report` + UI tab **🏆 Стратегии** (avg vs hold per strategy type)
- **Correlation risk** — blocks new buys when ≥6 markets fall together (configurable)
- **Daily report** — includes strategy leaderboard + correlation status

| Setting | Default | Meaning |
|---------|---------|---------|
| `SHADOW_WALKFORWARD_ENABLED` | true | OOS gate before shadow promote |
| `SHADOW_WALKFORWARD_MIN_EDGE` | 0.3 | Min OOS pp edge vs live params |
| `CORRELATION_RISK_MIN_BEARISH` | 6 | Bearish markets to block buys |
| `CORRELATION_RISK_MOMENTUM_PCT` | 0.8 | % move threshold |

## v26 — Profit engine

- **Backtest gate** — auto-tactics and trader-copy switches require proposed strategy to beat current on last ~200 candles (`AUTO_TACTICS_BACKTEST_*`)
- **Regime filter** — blocks DCA/Grid/RSI buys in bear market (price below SMA + falling momentum)
- **Portfolio drawdown halt** — at `PORTFOLIO_MAX_DRAWDOWN_PCT` (default 12%) brain triggers emergency halt and blocks new buys
- **Scalper fix** — TP from entry price, minimum edge covers fees+slippage (no negative-EV micro scalps)
- **RSI on candle closes** — RSI computed from 1m closes, not noisy ticks
- **Shadow Lab** — slower eval (5 min), more trades before promote (8); clones not reset on tactic switch
- **Tuning** — min 5 trades before optimizer (was 2); less overfitting
- **FeedHub** — no duplicate per-market REST poll when multiplex active
- **Exchange sync** — mirror fills include fees; paper→exchange errors shown in UI

| Setting | Default | Meaning |
|---------|---------|---------|
| `AUTO_TACTICS_BACKTEST_ENABLED` | true | Gate strategy switches with backtest |
| `AUTO_TACTICS_BACKTEST_MIN_EDGE` | 0.5 | Min pp vs-hold edge over current strategy |
| `PORTFOLIO_MAX_DRAWDOWN_PCT` | 12 | Block new buys + emergency brain halt |
| `REGIME_FILTER_ENABLED` | true | Skip counter-trend dip buys in bear |
| `SHADOW_MIN_TRADES_PROMOTE` | 8 | Clone needs more trades before promote |
| `SHADOW_EVAL_SEC` | 300 | Shadow eval every 5 min (less noise) |

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
