@echo off
title Stop NagarLoop Server
cd /d "%~dp0"

echo ===================================================
echo     STOPPING NAGARLOOP SERVER
echo ===================================================
echo.

echo [+] Freeing port 5000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [+] Stopping background python processes running app.py...
powershell -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo.
echo ===================================================
echo  [OK] NagarLoop Server has been stopped successfully!
echo ===================================================
echo.
powershell -Command "Start-Sleep -Seconds 2"
