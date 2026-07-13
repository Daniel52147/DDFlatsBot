# TradeSim на Render + доступ с телефона

## Зачем

Ноут выключен — боты и дашборд работают в облаке. С телефона открываешь ссылку Render и смотришь портфель, сделки, мозг.

## Важно заранее

| Тема | Реальность |
|------|------------|
| **Paper 24/7** | ✅ Отлично работает на Render |
| **Binance Testnet API** | ⚠️ Часто **блокируется** с IP облака (HTTP 451). Цены идут через fallback (Bybit/Kraken), но **ордера на testnet с Render могут не пройти** |
| **Лучший вариант для Testnet** | Домашний ПК 24/7 или Render только для **мониторинга Paper**, торговля testnet — дома |
| **Бесплатный Render** | Сервис **засыпает** без трафика (~15 мин). Для постоянной работы нужен **Starter ~$7/мес** |
| **Безопасность** | Публичный URL **обязательно** с `TRADESIM_API_TOKEN` |

## Быстрый деплой

### 1. GitHub

Код уже в `Daniel52147/DDFlatsBot`, ветка `cursor/tradesim-render-deploy-2631` (или `main` после merge).

### 2. Render Dashboard

1. [render.com](https://render.com) → **New** → **Web Service**
2. Подключи репозиторий **DDFlatsBot**
3. Настройки:
   - **Root Directory:** `TradeSim`
   - **Runtime:** Docker
   - **Plan:** Starter (для 24/7 без сна)
4. **Environment** → добавь секреты:

```env
TRADESIM_API_TOKEN=придумай-длинный-секрет-минимум-32-символа
DATA_DIR=/var/data
TRADESIM_BIND_HOST=0.0.0.0
TRADING_MODE_DEFAULT=paper
PAPER_LEARN_ENABLED=true
```

5. **Disks** → Add Disk:
   - Mount: `/var/data`
   - 1 GB

6. **Deploy**

После деплоя URL будет вида: `https://tradesim-xxxx.onrender.com`

### 3. Телефон

1. Открой URL в Chrome/Safari
2. Внизу страницы: поле **API-токен** → вставь тот же `TRADESIM_API_TOKEN` → **🔐**
3. Добавь на главный экран (Share → «На экран Домой») — как приложение
4. Дашборд адаптивный — график, портфель, сделки видны

**Только смотреть** — токен не нужен для чтения. **Кнопки** (торговля, сброс, режим) — нужен токен.

## Testnet на Render (опционально)

Если хочешь попробовать:

```env
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
EXCHANGE_ENABLED=true
EXCHANGE_TESTNET=true
```

Проверка: `https://твой-url.onrender.com/api/exchange/verify`

Если `geo-block` или `451` — оставь `EXCHANGE_ENABLED=false`, бот учится на **Paper** в облаке, testnet торгуй с домашнего ПК.

## Альтернатива без Render

| Способ | Плюсы |
|--------|--------|
| **Домашний ПК 24/7** + `start.bat` | Testnet без блокировок |
| **Tailscale** на ПК | Телефон заходит на `http://100.x.x.x:8765` без публичного URL |
| **ngrok** | Быстрый туннель с ноута, пока он включён |

## Перенос данных с ноута

Скопируй папку `TradeSim/data/` на диск Render (`/var/data`) через SSH/shell или начни с чистого Paper на облаке.

## Проверка что жив

- `GET /api/health` — JSON со статусом
- `GET /api/ping` — версия и портфель
