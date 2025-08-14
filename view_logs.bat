@echo off
chcp 65001 >nul
title Просмотр логов документов

echo ========================================
echo    ПРОСМОТР ЛОГОВ ДОКУМЕНТОВ
echo ========================================
echo.

if not exist "logs\documents.log" (
    echo Файл логов не найден: logs\documents.log
    echo Убедитесь, что приложение запущено и создало логи
    pause
    exit /b
)

:menu
echo Выберите действие:
echo 1. Показать последние 20 записей
echo 2. Показать последние 50 записей
echo 3. Показать статистику
echo 4. Поиск по пользователю
echo 5. Поиск по действию
echo 6. Поиск по дате
echo 7. Поиск по тексту
echo 8. Открыть файл логов в блокноте
echo 9. Выход
echo.
set /p choice="Введите номер (1-9): "

if "%choice%"=="1" goto recent20
if "%choice%"=="2" goto recent50
if "%choice%"=="3" goto stats
if "%choice%"=="4" goto search_user
if "%choice%"=="5" goto search_action
if "%choice%"=="6" goto search_date
if "%choice%"=="7" goto search_text
if "%choice%"=="8" goto open_notepad
if "%choice%"=="9" goto exit
echo Неверный выбор. Попробуйте снова.
goto menu

:recent20
echo.
echo Последние 20 записей:
echo ----------------------------------------
python view_logs.py -c 20
echo.
pause
goto menu

:recent50
echo.
echo Последние 50 записей:
echo ----------------------------------------
python view_logs.py -c 50
echo.
pause
goto menu

:stats
echo.
echo Статистика по логам:
echo ----------------------------------------
python view_logs.py --stats
echo.
pause
goto menu

:search_user
set /p username="Введите имя пользователя: "
echo.
echo Поиск по пользователю "%username%":
echo ----------------------------------------
python view_logs.py -u "%username%"
echo.
pause
goto menu

:search_action
echo.
echo Доступные действия:
echo - добавил штрихкод
echo - удалил штрихкод
echo - создал документ
echo - закрыл документ
echo - удалил документ
echo - обновил комментарий
echo - вошел в систему
echo - АДМИНИСТРАТОР
echo.
set /p action="Введите действие: "
echo.
echo Поиск по действию "%action%":
echo ----------------------------------------
python view_logs.py -a "%action%"
echo.
pause
goto menu

:search_date
set /p date="Введите дату (YYYY-MM-DD): "
echo.
echo Поиск по дате "%date%":
echo ----------------------------------------
python view_logs.py -d "%date%"
echo.
pause
goto menu

:search_text
set /p text="Введите текст для поиска: "
echo.
echo Поиск по тексту "%text%":
echo ----------------------------------------
python view_logs.py -s "%text%"
echo.
pause
goto menu

:open_notepad
echo Открываю файл логов в блокноте...
notepad "logs\documents.log"
goto menu

:exit
echo Выход из программы...
exit /b
