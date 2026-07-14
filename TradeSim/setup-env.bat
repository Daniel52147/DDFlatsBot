@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Настройка .env для Binance TESTNET ===
echo.
python scripts\apply_testnet_env.py
if errorlevel 1 (
  echo Ошибка apply_testnet_env.py
  pause
  exit /b 1
)
echo.
echo Откроем .env — вставь BINANCE_API_KEY и BINANCE_API_SECRET если пусто:
echo   https://testnet.binance.vision/
echo.
notepad .env
echo.
echo Готово. Запусти:  .\start.bat
echo (в PowerShell всегда .\ перед .bat файлами)
