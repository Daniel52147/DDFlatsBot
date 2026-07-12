# Запуск на Windows (PowerShell)

## 1. Обновить код (важно — у тебя была старая версия с 4 монетами)

```powershell
cd C:\Users\de381\DDFlatsBot
git pull origin cursor/trade-sim-paper-trading-2631
cd TradeSim
```

## 2. Зависимости (pip через python)

```powershell
python -m pip install -r requirements.txt
```

> Если `python` не найден — установи Python с https://python.org (галочка "Add to PATH")

## 3. Файл .env с Binance ключами

```powershell
copy .env.example .env
notepad .env
```

Вставь:
```env
BINANCE_API_KEY=твой_ключ
BINANCE_API_SECRET=твой_секрет
EXCHANGE_ENABLED=true
```

## 4. Запуск

```powershell
python main.py
```

**Не закрывай окно PowerShell** — пока оно открыто, сервер работает.

## 5. Открыть в браузере

**Локально на твоём ПК (скопируй точно):**
```
http://127.0.0.1:8765
```

**Важно:**
- Используй **`127.0.0.1`**, не `localhost` — на Windows `localhost` иногда идёт через IPv6 и не открывается
- Только **`http://`**, не `https://`
- **НЕ** используй `agent.cvm.dev` — это облако Cursor, не твой ПК
- Если видишь **502** — окно PowerShell закрыто или сервер упал

### Сайт не открывается?

1. Подожди 10–20 сек после старта (17 рынков грузятся)
2. В логе должно быть: `Application startup complete` и `Uvicorn running`
3. Проверь в PowerShell (второе окно):
   ```powershell
   curl http://127.0.0.1:8765/api/ping
   ```
   Должно вернуть JSON, не ошибку
4. Разреши Python в брандмауэре Windows, если спросит

## Быстрый способ

Двойной клик по `start.bat` в папке TradeSim.

## Проверка

В логе должно быть **17 рынков**, не 4. И:
```
Uvicorn running on http://127.0.0.1:8765
Application startup complete.
```
Без строки `Shutting down` сразу после старта.
