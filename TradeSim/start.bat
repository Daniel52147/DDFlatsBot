@echo off
chcp 65001 >nul
echo === TradeSim v15 — запуск (Windows) ===
cd /d "%~dp0"

echo.
echo [1/4] Обновление кода...
git pull origin cursor/trade-sim-paper-trading-2631 2>nul || git pull

echo.
echo [2/4] Зависимости...
python -m pip install -r requirements.txt -q

echo.
echo [3/4] Файл .env...
if not exist ".env" (
  if exist ".env.example" (
    copy /Y .env.example .env >nul
    echo Создан .env — открой блокнотом и вставь BINANCE ключи:
    echo   notepad .env
  ) else (
    echo ВНИМАНИЕ: нет .env.example — сделай git pull ещё раз
  )
) else (
  echo .env уже есть
)

echo.
echo [4/4] Запуск сервера...
echo.
echo   ЛОКАЛЬНО открой:  http://127.0.0.1:8765
echo   НЕ используй localhost и НЕ agent.cvm.dev
echo   НЕ закрывай это окно — иначе сайт не откроется
echo   Ctrl+Shift+R в браузере если пустая страница
echo.
set TRADESIM_BIND_HOST=127.0.0.1
python main.py
pause
