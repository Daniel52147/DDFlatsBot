@echo off
echo === TradeSim: обновление и запуск ===
cd /d "%~dp0"
cd ..
echo.
echo [1/2] git pull...
git pull
echo.
echo [2/2] Запуск сервера...
cd TradeSim
echo Открой http://localhost:8765 и нажми Ctrl+Shift+R
echo.
python main.py
