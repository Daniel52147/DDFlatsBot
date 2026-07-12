@echo off
chcp 65001 >nul
echo === TradeSim — запуск (Windows) ===
cd /d "%~dp0"

echo.
echo [1/4] Обновление кода...
git fetch origin
git pull origin cursor/tradesim-v43-testnet-discipline-2631 2>nul
if errorlevel 1 (
  git pull origin cursor/tradesim-v42-scorecard-2631 2>nul
)
if errorlevel 1 (
  git pull origin main 2>nul || git pull
)

echo.
echo [2/4] Зависимости...
python -m pip install -r requirements.txt -q

echo.
echo [3/4] Файл .env...
if not exist ".env" (
  if exist ".env.example" (
    copy /Y .env.example .env >nul
    echo Создан .env — открой блокнотом:
    echo   notepad .env
    echo Задай TRADESIM_API_TOKEN и BINANCE ключи (testnet)
  ) else (
    echo ВНИМАНИЕ: нет .env.example
  )
) else (
  echo .env уже есть
)

echo.
echo [4/4] Запуск сервера...
echo.
echo   Открой:  http://127.0.0.1:8765
echo   Версия v41 в заголовке
echo   Ctrl+Shift+R если старый кэш
echo.
set TRADESIM_BIND_HOST=127.0.0.1
python main.py
pause
