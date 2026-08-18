@echo off
title SwachhLoop 4R — Circular Economy Server
cd /d "%~dp0"

echo ===================================================
echo     SWACHHLOOP 4R - MUNICIPAL CIRCULAR PLATFORM
echo     Smart India Hackathon 2026 (SIH 2026)
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
echo [+] Starting SwachhLoop 4R Server on http://127.0.0.1:5000/ ...
echo [+] Citizen Portal   : http://127.0.0.1:5000/
echo [+] Dispatch Center  : http://127.0.0.1:5000/admin/dispatch
echo [+] Command Center   : http://127.0.0.1:5000/admin
echo.

:: Open browser after 2 seconds in a background thread so server is fully bound
start /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:5000/"

"%PYTHON_EXE%" app.py

pause
