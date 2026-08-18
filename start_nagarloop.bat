@echo off
title NagarLoop — Municipal Circular Waste Platform Server
cd /d "%~dp0"

echo ===================================================
echo     NAGARLOOP - MUNICIPAL CIRCULAR WASTE PLATFORM
echo     Zero-Mixing 4-Stream Doorstep Recovery System
echo ===================================================
echo.

if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    echo [+] Python virtual environment detected.
) else (
    set "PYTHON_EXE=python"
    echo [!] Using system Python.
)

echo.
echo [+] Starting NagarLoop Server on http://127.0.0.1:5000/ ...
echo [+] Citizen Portal     : http://127.0.0.1:5000/
echo [+] Doorstep Booking   : http://127.0.0.1:5000/book
echo [+] Driver Portal      : http://127.0.0.1:5000/driver
echo [+] Command Center     : http://127.0.0.1:5000/admin
echo [+] Dispatch Hub       : http://127.0.0.1:5000/admin/dispatch
echo [+] Operations Report  : http://127.0.0.1:5000/admin/reports
echo.

:: Open browser after 2 seconds in background thread
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000/"

"%PYTHON_EXE%" app.py

pause
