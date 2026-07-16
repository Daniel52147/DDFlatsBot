@echo off
chcp 65001 >nul
echo === TradeSim — запуск (Windows) ===
cd /d "%~dp0"

set BRANCH=cursor/live-contingency-playbook-2631

echo.
echo [1/5] Обновление кода (%BRANCH%)...
git fetch origin
git checkout %BRANCH% 2>nul
if errorlevel 1 (
  echo Переключаюсь на ветку %BRANCH%...
  git checkout -B %BRANCH% origin/%BRANCH% 2>nul
  if errorlevel 1 (
    echo WARN: не удалось checkout %BRANCH% — пробую pull в текущую ветку
  )
)
git pull origin %BRANCH%
if errorlevel 1 (
  echo WARN: git pull %BRANCH% не удался — пробую main
  git pull origin main 2>nul || git pull
)

echo.
echo [2/5] Версия кода...
python -c "import config; print('  >>> TradeSim v' + str(config.APP_VERSION) + ' <<<')"
if errorlevel 1 (
  echo  WARN: не прочитал config.APP_VERSION
)

echo.
echo [3/5] Зависимости...
python -m pip install -r requirements.txt -q

echo.
echo [4/5] Файл .env + сброс старых sync-сбоев...
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
python scripts\reset_sync_stats.py 2>nul

echo.
echo [5/5] Запуск сервера...
echo.
echo   ПК:      http://127.0.0.1:8765
echo   Телефон: та же Wi-Fi — после /open в Telegram
echo   Нужно в .env: TRADESIM_BIND_HOST=0.0.0.0 и TRADESIM_API_TOKEN
echo   Если в шапке НЕ v67+ — Ctrl+C, git pull, снова start.bat
echo.
set TRADESIM_BIND_HOST=0.0.0.0
python main.py
pause
