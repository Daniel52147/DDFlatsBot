@echo off
chcp 65001 >nul
echo === TradeSim — запуск (Windows) ===
cd /d "%~dp0"

echo.
echo [1/4] Обновление кода...
git fetch origin
git pull origin cursor/tradesim-v39-paper-learn-2631 2>nul
if errorlevel 1 (
  git pull origin cursor/tradesim-v38-hold-fix-2631 2>nul
)
if errorlevel 1 (
  git pull origin cursor/tradesim-v32-more-trades-2631 2>nul
)
if errorlevel 1 (
  git pull origin cursor/tradesim-v30-candle-fix-2631 2>nul
)
if errorlevel 1 (
  echo Ветка v32 не найдена — пробуем main...
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
echo   Должна быть версия v39 в заголовке (Paper Learn)
echo   Ctrl+Shift+R в браузере если старая версия
echo   НЕ закрывай это окно — иначе сайт не откроется
echo.
set TRADESIM_BIND_HOST=127.0.0.1
python main.py
pause
