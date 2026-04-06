@echo off
REM AgentAI Agency — One-Click Launcher (Windows)
cd /d "%~dp0"

set PYTHONPATH=%cd%;%cd%\src

echo ============================================
echo   AgentAI Agency — Starting All Services
echo ============================================
echo.

echo [1/4] Starting Control Plane API on :8002...
start /B "" cmd /c "uvicorn apps.api.main:app --port 8002 >nul 2>&1"

echo [2/4] Starting Unified API on :8001...
start /B "" cmd /c "uvicorn src.unified.api:app --port 8001 >nul 2>&1"

echo [3/4] Checking npm dependencies...
if not exist "apps\web\node_modules" (
    echo      Installing npm deps in apps/web...
    cd apps\web && npm install --silent && cd ..\..
) else (
    echo      node_modules found, skipping install.
)

echo [4/4] Starting React dev server on :3000...
start /B "" cmd /c "cd apps\web && npm run dev >nul 2>&1"

echo.
echo Waiting for services to start...
timeout /t 3 /nobreak >nul

echo Opening dashboard in browser...
start "" http://localhost:3000

echo.
echo ============================================
echo   All services running:
echo     Control Plane API:  http://localhost:8002
echo     Unified API:        http://localhost:8001
echo     Dashboard:          http://localhost:3000
echo ============================================
echo.
echo Press any key to stop all services...
pause >nul

echo.
echo Shutting down...
taskkill /F /FI "WINDOWTITLE eq uvicorn*" >nul 2>&1
taskkill /F /IM node.exe >nul 2>&1
echo Done.
