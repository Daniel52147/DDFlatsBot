@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Настройка .env для Binance TESTNET ===
echo.
if not exist ".env" (
  copy /Y .env.example .env >nul
  echo Создан .env из шаблона
) else (
  echo .env уже есть — откроем для редактирования
)
echo.
echo Вставь ключи с https://testnet.binance.vision/
echo   BINANCE_API_KEY=...
echo   BINANCE_API_SECRET=...
echo   EXCHANGE_ENABLED=true
echo   EXCHANGE_TESTNET=true
echo.
notepad .env
echo.
echo Готово. Запусти:  .\start.bat
echo (в PowerShell всегда .\ перед .bat файлами)
