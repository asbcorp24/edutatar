@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==========================================
echo        EduTatar Publisher
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Создаю виртуальное окружение...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo.
        echo ОШИБКА: не удалось создать виртуальное окружение.
        echo Убедитесь, что Python установлен и команда py доступна.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Виртуальное окружение уже существует.
)

echo.
echo [2/4] Проверяю зависимости...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось установить зависимости.
    pause
    exit /b 1
)

echo.
echo [3/4] Проверяю Chromium для Playwright...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось установить Chromium.
    pause
    exit /b 1
)

echo.
echo [4/4] Запускаю EduTatar Publisher...
echo.
".venv\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo Приложение завершилось с ошибкой.
    pause
)

endlocal
