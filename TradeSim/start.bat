@echo off
chcp 65001 >nul
echo === TradeSim — запуск (Windows) ===
cd /d "%~dp0"

set BRANCH=cursor/live-contingency-playbook-2631
set ROOT=%CD%
if not exist ".git" (
  if exist "..\.git" (
    set ROOT=%~dp0..
  )
)

echo.
echo [1/5] Обновление кода (%BRANCH%)...
cd /d "%ROOT%"
git fetch origin 2>nul
git checkout %BRANCH% 2>nul
if errorlevel 1 git checkout -B %BRANCH% origin/%BRANCH% 2>nul
git pull origin %BRANCH%
if errorlevel 1 (
  echo.
  echo *** ОШИБКА: не удалось обновить %BRANCH% ***
  echo Запусти UPDATE.bat — двойной клик в папке TradeSim
  echo НЕ используй main — там нет TradeSim v67
  pause
  exit /b 1
)

cd /d "%~dp0"

echo.
echo [2/5] Версия...
python -c "import config; v=config.APP_VERSION; print('  >>> TradeSim v'+str(v)+' <<<'); exit(0 if v>=67 else 1)"
if errorlevel 1 (
  echo Старая версия! Запусти UPDATE.bat перед start.bat
  pause
  exit /b 1
)

echo.
echo [3/5] Зависимости...
python -m pip install -r requirements.txt -q

echo.
echo [4/5] .env + sync...
python scripts\apply_testnet_env.py 2>nul
if not exist ".env" (
  if exist ".env.example" (
    copy /Y .env.example .env >nul
    python scripts\apply_testnet_env.py
    echo Создан .env — вставь ключи: notepad .env
  )
)
python scripts\reset_sync_stats.py 2>nul

echo.
echo [5/5] Сервер...
echo   http://127.0.0.1:8765  ^|  Ctrl+Shift+R после старта
echo.
set TRADESIM_BIND_HOST=0.0.0.0
python main.py
pause
