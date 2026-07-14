@echo off
chcp 65001 >nul
echo === TradeSim — запуск (Windows) ===
cd /d "%~dp0"

echo.
echo [1/4] Обновление кода...
git fetch origin
git pull origin cursor/live-contingency-playbook-2631 2>nul
if errorlevel 1 (
  git pull origin main 2>nul || git pull
)

echo.
echo [2/4] Зависимости...
python -m pip install -r requirements.txt -q

echo.
echo [3/4] Файл .env...
python scripts\apply_testnet_env.py 2>nul
if not exist ".env" (
  if exist ".env.example" (
    copy /Y .env.example .env >nul
    python scripts\apply_testnet_env.py
    echo Создан .env — вставь ключи: notepad .env
  )
) else (
  echo .env проверен (testnet-настройки)
)

echo.
echo [4/4] Запуск сервера...
echo.
echo   ПК:      http://127.0.0.1:8765
echo   Телефон: та же Wi-Fi — после /open в Telegram
echo   Нужно в .env: TRADESIM_BIND_HOST=0.0.0.0 и TRADESIM_API_TOKEN
echo.
set TRADESIM_BIND_HOST=0.0.0.0
python main.py
pause
