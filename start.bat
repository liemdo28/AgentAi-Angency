@echo off
REM ============================================
REM Agency System - Quick Start Script (Windows)
REM Starts all services needed for the dashboard
REM ============================================

echo ======================================
echo Agency System - Starting Services
echo ======================================

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python not found!
    echo Please install Python from python.org
    pause
    exit /b 1
)

REM Project root
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Create logs folder if not exists
if not exist "logs" mkdir logs

echo [1/4] Installing dependencies...
python -m pip install -r requirements.txt -q 2>nul

echo [2/4] Starting AgentAI Agency API (port 8000)...
set PYTHONPATH=%SCRIPT_DIR%;%SCRIPT_DIR%\src
start "AgencyAPI" /min python -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

timeout /t 3 /nobreak >nul

echo [3/4] Starting Unified Dashboard API (port 8001)...
start "UnifiedAPI" /min python -m uvicorn src.unified.api:app --host 0.0.0.0 --port 8001 --reload

timeout /t 3 /nobreak >nul

echo [4/4] Starting Dashboard Web Server (port 8080)...
cd dashboard
start "Dashboard" /min python -m http.server 8080
cd ..

echo.
echo ======================================
echo All services started!
echo ======================================
echo.
echo Services:
echo   Agency API:       http://localhost:8000
echo   Unified API:      http://localhost:8001
echo   Dashboard:        http://localhost:8080
echo.
echo API Docs:
echo   Agency:    http://localhost:8000/docs
echo   Unified:   http://localhost:8001/docs
echo.
echo To stop all services:
echo   taskkill /FI "WINDOWTITLE eq AgencyAPI" /F
echo   taskkill /FI "WINDOWTITLE eq UnifiedAPI" /F
echo   taskkill /FI "WINDOWTITLE eq Dashboard" /F
echo.

REM Open browser
start http://localhost:8080

pause
