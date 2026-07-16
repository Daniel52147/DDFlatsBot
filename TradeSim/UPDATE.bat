@echo off
chcp 65001 >nul
echo.
echo ============================================
echo   TradeSim — ОБНОВЛЕНИЕ до v67+
echo ============================================
echo.

cd /d "%~dp0"
set TSIM=%CD%
set ROOT=%CD%

REM .git может быть в родительской папке (DDFlatsBot)
if not exist ".git" (
  if exist "..\.git" (
    cd /d "%~dp0.."
    set ROOT=%CD%
  )
)

echo Папка TradeSim: %TSIM%
echo Корень git:      %ROOT%
echo.

cd /d "%ROOT%"
if not exist ".git" (
  echo ОШИБКА: git не найден. Клонируй репозиторий:
  echo   git clone https://github.com/Daniel52147/DDFlatsBot.git
  echo   cd DDFlatsBot
  echo   git checkout cursor/live-contingency-playbook-2631
  pause
  exit /b 1
)

set BRANCH=cursor/live-contingency-playbook-2631

echo [1/4] git fetch...
git fetch origin
if errorlevel 1 (
  echo ОШИБКА fetch — проверь интернет
  pause
  exit /b 1
)

echo [2/4] git checkout %BRANCH%...
git checkout %BRANCH%
if errorlevel 1 (
  git checkout -B %BRANCH% origin/%BRANCH%
  if errorlevel 1 (
    echo ОШИБКА checkout — пришли скрин этого окна
    pause
    exit /b 1
  )
)

echo [3/4] git pull...
git pull origin %BRANCH%
if errorlevel 1 (
  echo ОШИБКА pull
  pause
  exit /b 1
)

cd /d "%TSIM%"
echo [4/4] версия + сброс sync...
python -c "import config; v=config.APP_VERSION; print('  >>> TradeSim v'+str(v)+' <<<'); exit(0 if v>=67 else 1)"
if errorlevel 1 (
  echo.
  echo ВНИМАНИЕ: версия ниже 67 — что-то не так с веткой.
  echo Текущая ветка:
  cd /d "%ROOT%"
  git branch --show-current
  git log -1 --oneline
  pause
  exit /b 1
)

python scripts\reset_sync_stats.py 2>nul
python -m pip install -r requirements.txt -q

echo.
echo ============================================
echo   ГОТОВО. Теперь запусти start.bat
echo   В шапке сайта должно быть TradeSim v67+
echo   Ctrl+Shift+R в браузере, потом Smoke test
echo ============================================
echo.
pause
