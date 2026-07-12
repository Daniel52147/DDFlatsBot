# Запуск на Windows (PowerShell)

## 1. Обновить код (ветка v36 — путь к Live)

```powershell
cd C:\Users\de381\DDFlatsBot\TradeSim
git fetch origin
git pull origin cursor/tradesim-v36-live-prep-2631
```

Или двойной клик **start.bat** — он сам подтянет последнюю ветку.

## 2. Зависимости

```powershell
python -m pip install -r requirements.txt
```

## 3. API ключи Binance TESTNET

1. Зайди на https://testnet.binance.vision/ → Log In → **Generate HMAC_SHA256 Key**
2. В PowerShell из папки TradeSim:

```powershell
.\setup-env.bat
```

(В PowerShell обязательно `.\` перед именем файла — иначе «не распознано».)

Или вручную: `copy .env.example .env` → `notepad .env`
3. Вставь ключи:

```env
BINANCE_API_KEY=твой_ключ
BINANCE_API_SECRET=твой_секрет
EXCHANGE_ENABLED=true
EXCHANGE_TESTNET=true
EXCHANGE_SYNC_TO_PAPER=true
EXCHANGE_SYNC_FROM_PAPER=true
TRADING_MODE_DEFAULT=testnet
```

⚠️ **Никогда не публикуй ключи в чат/GitHub.** Если засветил — перевыпусти на testnet.

## 4. Запуск

```powershell
python main.py
```

В логах должно быть:
```
Binance testnet OK — USDT ...
```

В браузере: http://127.0.0.1:8765 → **Ctrl+Shift+R** → меню **🧪 Testnet**

## 5. Проверка ключей

Открой: http://127.0.0.1:8765/api/exchange/verify

`"ok": true` — ключи работают.

## Частые ошибки

| Ошибка | Решение |
|--------|---------|
| Старый UI v28/v31 | `git pull` + Ctrl+Shift+R |
| HTTP 401/403 | Ключ не от testnet или опечатка в Secret |
| HTTP 451 | Регион блокирует Binance — запускай дома на Windows |
| Testnet режим не включается | `EXCHANGE_TESTNET=true` в .env |
