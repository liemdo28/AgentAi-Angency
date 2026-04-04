@echo off
REM Start all services locally (Windows)
cd /d "%~dp0\.."

set PYTHONPATH=%cd%;%cd%\src

echo === Starting AgentAI Agency — Full Stack ===

echo [1/4] Starting Agency API on :8000...
start /B "AgencyAPI" cmd /c "uvicorn src.api:app --host 0.0.0.0 --port 8000"

echo [2/4] Starting Control Plane API on :8002...
start /B "ControlPlaneAPI" cmd /c "uvicorn apps.api.main:app --host 0.0.0.0 --port 8002"

echo [3/4] Starting Heartbeat Worker...
start /B "HeartbeatWorker" cmd /c "python -m apps.worker.heartbeat"

echo [4/4] Starting Dashboard on :3000...
cd apps\web
start /B "Dashboard" cmd /c "npm install && npm run dev"
cd ..\..

echo.
echo === All services running ===
echo   Agency API:        http://localhost:8000
echo   Control Plane API: http://localhost:8002
echo   Dashboard:         http://localhost:3000
echo.
echo Close this window to stop background services.
pause
