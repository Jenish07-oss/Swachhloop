@echo off
title Stop SwachhLoop 4R Server
cd /d "%~dp0"

echo ===================================================
echo     STOPPING SWACHHLOOP 4R SERVER
echo ===================================================
echo.

echo [+] Freeing port 5000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [+] Stopping background processes...
powershell -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo ===================================================
echo  [OK] SwachhLoop 4R Server has been stopped!
echo ===================================================
echo.
timeout /t 3 >nul
