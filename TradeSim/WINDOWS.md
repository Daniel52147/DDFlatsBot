# Запуск на Windows

## Быстро: обновить и запустить

1. **Закрой** старый бот (окно с `python main.py` → Ctrl+C)
2. Двойной клик **`UPDATE.bat`** (в папке TradeSim)
3. Двойной клик **`start.bat`**
4. Браузер: **Ctrl+Shift+R** — в шапке должно быть **TradeSim v67+**
5. Кнопка **🧪 Smoke test**

## Важно: ветка git

Все фиксы sync (v65–v67) только в ветке:

`cursor/live-contingency-playbook-2631`

Ветка **`main`** — другой проект (DDFlatsBot), **без TradeSim v67**.  
Если в шапке **v65** — ты на старом коде.

### Вручную (PowerShell)

```powershell
cd C:\Users\de381\DDFlatsBot
git fetch origin
git checkout cursor/live-contingency-playbook-2631
git pull origin cursor/live-contingency-playbook-2631
cd TradeSim
python -c "import config; print('v', config.APP_VERSION)"
python scripts\reset_sync_stats.py
.\start.bat
```

Должно вывести: `v 67` (или выше).

## Почему sync 49% и сбои 167

Paper grid покупает **$80**, лимит testnet **$25** → каждый sync падал.  
**v67** обрезает ордер до $25 и сбрасывает старые сбои.

## .env (testnet)

```env
EXCHANGE_ENABLED=true
EXCHANGE_TESTNET=true
EXCHANGE_SYNC_FROM_PAPER=true
EXCHANGE_SYNC_TO_PAPER=true
EXCHANGE_MAX_ORDER_USD=25
TRADING_MODE_DEFAULT=testnet
PAPER_LEARN_ENABLED=false
TRADE_MODE=normal
```

Или: `.\setup-env.bat`

## Диагностика

Если после UPDATE всё ещё v65:

```powershell
cd C:\Users\de381\DDFlatsBot
git branch --show-current
git log -1 --oneline
cd TradeSim
python -c "import config; print(config.APP_VERSION)"
```

Пришли вывод этих трёх команд.

## Smoke test

После v67: **🧹 Сброс sync** (если есть) → **🧪 Smoke test**  
Sync должен быть ≥85%. Live — только после зелёного Smoke.
