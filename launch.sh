#!/usr/bin/env bash
# AgentAI Agency — One-Click Launcher (Linux/Mac)
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT:$ROOT/src"

PIDS=()

cleanup() {
    echo ""
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo "Done."
    exit 0
}
trap cleanup INT TERM

echo "============================================"
echo "  AgentAI Agency — Starting All Services"
echo "============================================"
echo ""

echo "[1/4] Starting Control Plane API on :8002..."
uvicorn apps.api.main:app --port 8002 &
PIDS+=($!)

echo "[2/4] Starting Unified API on :8001..."
uvicorn src.unified.api:app --port 8001 &
PIDS+=($!)

echo "[3/4] Checking npm dependencies..."
if [ ! -d "apps/web/node_modules" ]; then
    echo "     Installing npm deps in apps/web..."
    (cd apps/web && npm install --silent)
else
    echo "     node_modules found, skipping install."
fi

echo "[4/4] Starting React dev server on :3000..."
(cd apps/web && npm run dev) &
PIDS+=($!)

echo ""
echo "Waiting for services to start..."
sleep 3

echo "Opening dashboard in browser..."
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:3000
elif command -v open &>/dev/null; then
    open http://localhost:3000
fi

echo ""
echo "============================================"
echo "  All services running:"
echo "    Control Plane API:  http://localhost:8002"
echo "    Unified API:        http://localhost:8001"
echo "    Dashboard:          http://localhost:3000"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop all services."

wait
