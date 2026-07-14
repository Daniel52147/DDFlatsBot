# TradeSim на Render — пошагово: куда нажать и что написать

Цель: бот и дашборд работают **24/7 в облаке**, с телефона открываешь ссылку и смотришь портфель, сделки, мозг, Telegram-алерты.

---

## Что получится в итоге

| Что | Где |
|-----|-----|
| Дашборд в браузере | `https://tradesim-xxxx.onrender.com` |
| Боты крутятся | На сервере Render, ноут можно выключить |
| С телефона | Та же ссылка → «На экран Домой» |
| База сделок | Диск `/var/data` — не пропадает при рестарте |
| Кнопки (торговля, сброс) | Нужен API-токен внизу страницы |

---

## Важно заранее (честно)

| Тема | Реальность |
|------|------------|
| **Paper 24/7** | ✅ Идеально для Render |
| **Binance Testnet с Render** | ⚠️ Часто **HTTP 451** (geo/IP). Цены идут, ордера на testnet могут не пройти |
| **Testnet торговля** | Лучше с **домашнего ПК**; Render = мониторинг + Paper |
| **Бесплатный план** | Сервис **засыпает** без визитов (~15 мин). Для 24/7 нужен **Starter ~$7/мес** |
| **Безопасность** | Публичный URL **обязательно** с `TRADESIM_API_TOKEN` |

---

# ЧАСТЬ 1. Подготовка (один раз)

## 1.1. Аккаунт Render

1. Открой в браузере: **https://render.com**
2. Нажми **Get Started** (или **Sign Up**)
3. Выбери **Sign up with GitHub**
4. Разреши Render доступ к GitHub
5. После входа ты на **Dashboard** (главная панель Render)

## 1.2. Репозиторий на GitHub

Код должен быть в репозитории **Daniel52147/DDFlatsBot**.

Ветка с последним TradeSim (на момент написания):
- `cursor/live-contingency-playbook-2631` — playbook + Render
- или `main` после merge PR

Если репозиторий не виден в Render:
1. Dashboard → правый верх **Account Settings**
2. **Git Provider** → **Connect GitHub**
3. **Configure account** → дай доступ к **DDFlatsBot**

---

# ЧАСТЬ 2. Создание сервиса (каждое поле)

## 2.1. Начало

1. На **Dashboard** нажми синюю кнопку **+ New** (справа вверху)
2. Выбери **Web Service** (не Worker, не Static Site)
3. В списке репозиториев найди **Daniel52147 / DDFlatsBot**
4. Нажми **Connect**

## 2.2. Основные настройки (страница Create a Web Service)

Заполни **точно так**:

| Поле на экране | Что написать / выбрать |
|----------------|------------------------|
| **Name** | `tradesim` (или `tradesim-bot` — латиница, без пробелов) |
| **Region** | **Frankfurt (EU Central)** или ближайший к тебе |
| **Branch** | `cursor/live-contingency-playbook-2631` (или `main`) |
| **Root Directory** | `TradeSim` ← **обязательно!** Код бота в подпапке |
| **Runtime** | **Docker** |
| **Instance Type** | **Starter** ($7/мес) — для 24/7 без сна. Free — только для теста |

Остальное при Docker Render подхватит из `Dockerfile`.

| Поле | Значение |
|------|----------|
| **Dockerfile Path** | `./Dockerfile` (по умолчанию) |
| **Docker Build Context** | `.` (точка) |

## 2.3. Переменные окружения (Environment)

Прокрути до блока **Environment Variables**.

Нажми **Add Environment Variable** для **каждой** строки ниже.

### Обязательные (без них не запустится или небезопасно)

| Key | Value | Secret? |
|-----|-------|---------|
| `TRADESIM_API_TOKEN` | Придумай длинный пароль, минимум 32 символа. Пример генерации: открой PowerShell → `[guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()` | ✅ **Да** (галочка Secret) |
| `TRADESIM_BIND_HOST` | `0.0.0.0` | Нет |
| `DATA_DIR` | `/var/data` | Нет |
| `TRADING_MODE_DEFAULT` | `paper` | Нет |
| `AUTO_APPLY_TRADING_MODE_ON_START` | `false` | Нет |
| `EXCHANGE_ENABLED` | `false` | Нет |
| `PAPER_LEARN_ENABLED` | `true` | Нет |
| `PYTHONUNBUFFERED` | `1` | Нет |

> **Запиши `TRADESIM_API_TOKEN` в блокнот** — он понадобится в браузере на телефоне.

### Telegram (опционально, но у тебя уже работает)

| Key | Value | Secret? |
|-----|-------|---------|
| `TELEGRAM_ENABLED` | `true` | Нет |
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather | ✅ Secret |
| `TELEGRAM_CHAT_ID` | `2066158453` | Нет |
| `TELEGRAM_ALERT_HALT` | `true` | Нет |
| `TELEGRAM_ALERT_SYNC_FAIL` | `true` | Нет |

### Binance Testnet на Render (опционально — часто не работает)

Пробуй только если нужно. Если verify даст 451 — оставь `EXCHANGE_ENABLED=false`.

| Key | Value | Secret? |
|-----|-------|---------|
| `BINANCE_API_KEY` | Ключ с testnet.binance.vision | ✅ Secret |
| `BINANCE_API_SECRET` | Секрет testnet | ✅ Secret |
| `EXCHANGE_ENABLED` | `true` | Нет |
| `EXCHANGE_TESTNET` | `true` | Нет |
| `EXCHANGE_SYNC_TO_PAPER` | `true` | Нет |

## 2.4. Диск (чтобы база не терялась)

1. На той же странице найди **Disks** (или после создания: сервис → **Disks** → **Add Disk**)
2. Нажми **Add Disk**
3. Заполни:

| Поле | Значение |
|------|----------|
| **Name** | `tradesim-data` |
| **Mount Path** | `/var/data` |
| **Size** | `1` GB |

Диск должен совпадать с `DATA_DIR=/var/data`.

## 2.5. Health Check (обычно автоматически)

| Поле | Значение |
|------|----------|
| **Health Check Path** | `/api/health` |

## 2.6. Деплой

1. Нажми внизу **Create Web Service**
2. Render начнёт **Build** → **Deploy** (5–10 минут первый раз)
3. Следи за логами во вкладке **Logs**

### Успешный лог выглядит так:

```
Uvicorn running on http://0.0.0.0:10000
TradeSim v55 ...
```

(Порт может быть не 8765 — Render сам задаёт `PORT`, это нормально.)

### Ошибка в логах

| Текст | Что сделать |
|-------|-------------|
| `TRADESIM_API_TOKEN обязателен` | Добавь `TRADESIM_API_TOKEN` в Environment → **Manual Deploy** |
| `Build failed` | Проверь **Root Directory** = `TradeSim` |
| `Port scan timeout` | Убедись что в коде используется `PORT` (ветка с Render-фиксом) |

## 2.7. Твой URL

После деплоя вверху страницы сервиса:

**`https://tradesim-xxxx.onrender.com`**

Скопируй и сохрани.

---

# ЧАСТЬ 3. Проверка в браузере (ПК)

## 3.1. Открыть дашборд

1. Вставь URL в Chrome/Edge
2. Должна загрузиться страница TradeSim с графиком и портфелем

## 3.2. Проверка API

Открой в новой вкладке:

```
https://ТВОЙ-URL.onrender.com/api/health
```

Должен быть JSON с `"ok": true` и версией.

```
https://ТВОЙ-URL.onrender.com/api/ping
```

## 3.3. Ввести API-токен (для кнопок)

1. На главной странице **прокрути вниз до footer** (подвал)
2. Поле **«API-токен»** (серое поле ввода)
3. Вставь **тот же** `TRADESIM_API_TOKEN`, что в Render Environment
4. Нажми кнопку **🔐** справа от поля
5. Токен сохранится в браузере — кнопки (Testnet, Smoke test, сброс) заработают

**Без токена** можно только **смотреть** (график, сделки, мозг). **С токеном** — нажимать кнопки.

## 3.4. Что нажать на дашборде (основное)

| Где на экране | Кнопка | Зачем |
|---------------|--------|-------|
| Верх, меню режима | **📄 Paper** | Убедись что Paper (безопасно на Render) |
| Блок **🏦 Биржа · путь к Live** | **🎯 Путь к Live** | Обновить фазы |
| Там же | **🧪 Smoke test** | Проверка (нужен токен) |
| Там же | Раскрой **🔥 Обвалы и рынок** | Playbook план А/Б |
| Блок **📡 Интеграции** | **Обновить** | Статус Telegram |
| Footer | **🔐** | Сохранить токен |

---

# ЧАСТЬ 4. Телефон

## 4.1. Открыть

1. Safari (iPhone) или Chrome (Android)
2. Вставь тот же URL: `https://tradesim-xxxx.onrender.com`
3. Прокрути вниз → введи API-токен → **🔐**

## 4.2. Добавить на главный экран (как приложение)

**iPhone:**
1. Кнопка **Поделиться** (квадрат со стрелкой)
2. **На экран «Домой»**
3. Имя: `TradeSim` → **Добавить**

**Android:**
1. Меню ⋮ → **Добавить на главный экран**

## 4.3. Telegram на телефоне

Команды боту в Telegram работают **независимо** от Render:
- `/status` — портфель
- `/pause` — пауза
- `/resume all` — продолжить

Render шлёт алерты в тот же чат, если `TELEGRAM_*` заданы.

---

# ЧАСТЬ 5. Blueprint (альтернатива — из файла)

Если не хочешь вводить всё руками:

1. Dashboard → **+ New** → **Blueprint**
2. Подключи **DDFlatsBot**
3. Render найдёт `TradeSim/render.yaml`
4. **Apply** → потом в Dashboard сервиса **tradesim** добавь секреты:
   - `TRADESIM_API_TOKEN`
   - `TELEGRAM_BOT_TOKEN` (если нужен)
5. **Manual Deploy**

---

# ЧАСТЬ 6. Перенос данных с ноута (опционально)

Если на ПК уже есть `TradeSim/data/tradesim.db` с 621 сделкой:

**Простой путь:** начни с чистого Paper на Render (новая база).

**Перенос базы** (продвинуто):
1. Render Dashboard → сервис **tradesim** → **Shell** (на платных планах)
2. Или скопируй `tradesim.db` в `/var/data/` через поддержку Render

На старте проще **новый Paper в облаке**, домашний ПК оставить для Testnet.

---

# ЧАСТЬ 7. Обслуживание

| Действие | Где нажать |
|----------|------------|
| Обновить код с GitHub | Сервис → **Manual Deploy** → **Deploy latest commit** |
| Смотреть логи | Сервис → **Logs** |
| Изменить переменные | Сервис → **Environment** → Edit → **Save** (авто-редеплой) |
| Перезапуск | **Manual Deploy** |
| Удалить сервис | **Settings** → внизу **Delete Web Service** |

---

# ЧАСТЬ 8. Схема: домашний ПК + Render

Рекомендуемая схема для тебя:

```
┌─────────────────────┐     ┌──────────────────────┐
│  Render (облако)    │     │  Домашний ПК         │
│  Paper 24/7         │     │  Testnet торговля    │
│  Мониторинг с тел.  │     │  Binance без 451     │
│  Telegram алерты    │     │  start.bat           │
└─────────────────────┘     └──────────────────────┘
```

| Задача | Где |
|--------|-----|
| Смотреть ночью с телефона | Render URL |
| Testnet ордера | Домашний ПК |
| Обвал рынка — `/pause` | Telegram (работает везде) |

---

# Чеклист перед Live

- [ ] Render работает, `/api/health` OK
- [ ] API-токен введён на телефоне
- [ ] Telegram `/status` отвечает
- [ ] Режим **Paper** или **Testnet** (не Live на Render сразу)
- [ ] Smoke test на **домашнем ПК** с testnet
- [ ] Playbook «Обвалы и рынок» прочитан

---

*TradeSim v55+ · вопросы по логам — вкладка Logs на Render*
