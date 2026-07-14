# Live Playbook — план А и план Б

Полная матрица ситуаций для TradeSim на **Testnet** и **Live**.  
В UI: панель **«Биржа · путь к Live»** → **Live Playbook**.  
API: `GET /api/live-playbook`.

**План А** — что делает бот автоматически (protections, brain, risk_gate, лимиты биржи).  
**План Б** — что делаешь ты, если автоматики недостаточно.

---

## Быстрые правила

1. `/pause` проще, чем `/resume all` — не снимай protections без причины.
2. На Testnet/Live: `EXCHANGE_SYNC_FROM_PAPER=true`.
3. Перед каждым этапом: **Smoke test** (`POST /api/smoke-test`).
4. Лимиты по умолчанию: ордер ≤$25, дневной убыток ≤3%, просадка ≤8%.
5. Paper +47% ≠ гарантия Live — эталон Testnet + reconcile.

---

## Категории (краткий указатель)

| Категория | Примеры | План А (бот) | План Б (ты) |
|-----------|---------|--------------|-------------|
| Рынок | flash crash, pump, боковик | brain halt, TP, STALE-LOSS | /pause, не догонять дном |
| Портфель | дневной лимит, просадка 8% | portfolio_halt, биржа блокирует buy | testnet, Live Micro |
| Биржа | API down, 429, 451, bad keys | retry, alerts | stability-check, новые ключи |
| Sync | reconcile красный | sync после ордера | sync-paper-all, стоп торговли |
| Инфра | краш, нет тиков, нет сети | restore из DB | main.py, reconcile |
| Защиты | emergency_halt, 3 стопа | пауза 4ч / cooldown 30м | ждать, не clear_all |
| Пользователь | паника, случайный Live | readiness gate | testnet, smoke test |
| Мониторинг | Telegram молчит | UI alerts | /api/telegram/test |
| Эскалация | Micro → Live | лимиты $10 | откат при −3%/день |
| Ордера | limit висит, slippage | sync partial | cancel, conservative |

Полный список (**35+ сценариев**) — в `learning/live_playbook.py` и в UI.

---

## Telegram-команды (план Б)

| Команда | Действие |
|---------|----------|
| `/status` | Портфель, режим, P&L |
| `/balance` | Paper + биржа USDT |
| `/pause` или `/pause BTC` | Пауза всех или одного бота |
| `/resume all` | Возобновить + сброс protections |
| `/help` | Справка |

---

## Ключевые API

| Endpoint | Когда |
|----------|-------|
| `GET /api/live-playbook` | Все сценарии А/Б |
| `GET /api/exchange/reconcile` | Paper ≠ биржа |
| `POST /api/exchange/sync-paper-all` | Подогнать paper |
| `POST /api/smoke-test` | Сертификация перед Live |
| `POST /api/live-prep/start-micro` | Live Micro $10 |
| `POST /api/trading-mode` | paper / testnet / live |
| `GET /api/exchange/verify` | API, geo, ключи |
| `POST /api/protections/clear` | Только осознанно |

---

## Фазы перед Live (напоминание)

1. **Paper** — обучение, много сделок OK  
2. **Testnet дисциплина** — мелкие ордера, sync  
3. **Testnet стабильность** — sync ≥85%, не P&L  
4. **Live Micro** — $10, ≤3 сделки/день  
5. **Live полный** — после 7+ дней стабильности  

---

*TradeSim v54+ · источник данных: `learning/live_playbook.py`*
