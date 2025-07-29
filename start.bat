@echo off
echo Запуск системы мобильной инвентаризации...
echo.
echo Приложение будет доступно по адресу: http://localhost:8000
echo Для остановки нажмите Ctrl+C
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause