#!/usr/bin/env bash
# Start all services locally (without Docker)
set -e

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT:$ROOT/src"

echo "=== Starting AgentAI Agency — Full Stack ==="

# 1. Existing agency API (port 8000)
echo "[1/4] Starting Agency API on :8000..."
uvicorn src.api:app --host 0.0.0.0 --port 8000 &
PID_AGENCY=$!

# 2. Control Plane API (port 8002)
echo "[2/4] Starting Control Plane API on :8002..."
uvicorn apps.api.main:app --host 0.0.0.0 --port 8002 &
PID_CP=$!

# 3. Heartbeat Worker
echo "[3/4] Starting Heartbeat Worker..."
python -m apps.worker.heartbeat &
PID_WORKER=$!

# 4. React Dashboard (port 3000)
echo "[4/4] Starting Dashboard on :3000..."
cd apps/web && npm install --silent && npm run dev &
PID_WEB=$!
cd "$ROOT"

echo ""
echo "=== All services running ==="
echo "  Agency API:        http://localhost:8000"
echo "  Control Plane API: http://localhost:8002"
echo "  Dashboard:         http://localhost:3000"
echo ""
echo "PIDs: agency=$PID_AGENCY cp=$PID_CP worker=$PID_WORKER web=$PID_WEB"
echo "Press Ctrl+C to stop all."

trap "kill $PID_AGENCY $PID_CP $PID_WORKER $PID_WEB 2>/dev/null; exit" INT TERM
wait
