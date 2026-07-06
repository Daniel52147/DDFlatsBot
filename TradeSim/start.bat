@echo off
echo === TradeSim: обновление и запуск ===
cd /d "%~dp0"
cd ..
echo.
echo [1/3] git pull...
git pull origin cursor/trade-sim-paper-trading-2631
echo.
echo [2/3] Проверка версии...
findstr "dca_amount.: 25" TradeSim\config.py >nul
if errorlevel 1 (
    echo ОШИБКА: config.py старый! DCA должен быть 25, не 100.
    pause
    exit /b 1
)
echo OK: config.py новая версия (DCA 25$
echo.
echo [3/3] Запуск сервера...
cd TradeSim
echo Открой http://localhost:8765 и нажми Ctrl+Shift+R
echo.
python main.py
