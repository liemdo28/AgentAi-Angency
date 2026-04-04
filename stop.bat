@echo off
REM ============================================
REM Stop all Agency System services
REM ============================================

echo Stopping Agency System services...

REM Kill by PID files if they exist
if exist ".agency.pid" (
    for /f %%i in (.agency.pid) do taskkill /PID %%i /F >nul 2>&1
    del .agency.pid
)

if exist ".unified.pid" (
    for /f %%i in (.unified.pid) do taskkill /PID %%i /F >nul 2>&1
    del .unified.pid
)

if exist ".dashboard.pid" (
    for /f %%i in (.dashboard.pid) do taskkill /PID %%i /F >nul 2>&1
    del .dashboard.pid
)

REM Also kill by window title
taskkill /FI "WINDOWTITLE eq AgencyAPI" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq UnifiedAPI" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Dashboard" /F >nul 2>&1

REM Kill Python processes running uvicorn or http.server in this folder
powershell -Command "Get-Process python | Where-Object {$_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*http.server*'} | Stop-Process -Force" >nul 2>&1

echo.
echo All services stopped.
pause
