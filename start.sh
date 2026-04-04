#!/bin/bash
# ============================================
# Agency System - Quick Start Script
# Starts all services needed for the dashboard
# ============================================

set -e

echo "======================================"
echo "Agency System - Starting Services"
echo "======================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo -e "${RED}Error: Python not found!${NC}"
        exit 1
    fi
    PYTHON=python
else
    PYTHON=python3
fi

# Check pip
if ! $PYTHON -m pip --version &> /dev/null; then
    echo -e "${YELLOW}Warning: pip not found. Installing dependencies may fail.${NC}"
fi

# Project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${GREEN}[1/4]${NC} Installing dependencies..."
$PYTHON -m pip install -r requirements.txt -q 2>/dev/null || true

echo -e "${GREEN}[2/4]${NC} Starting AgentAI Agency API (port 8000)..."
# Start in background
export PYTHONPATH="${SCRIPT_DIR}:${SCRIPT_DIR}/src"
nohup $PYTHON -m uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload > logs/agency.log 2>&1 &
AGENCY_PID=$!
echo "Agency API started (PID: $AGENCY_PID)"
echo $AGENCY_PID > .agency.pid

sleep 2

echo -e "${GREEN}[3/4]${NC} Starting Unified Dashboard API (port 8001)..."
nohup $PYTHON -m uvicorn src.unified.api:app --host 0.0.0.0 --port 8001 --reload > logs/unified.log 2>&1 &
UNIFIED_PID=$!
echo "Unified API started (PID: $UNIFIED_PID)"
echo $UNIFIED_PID > .unified.pid

sleep 2

echo -e "${GREEN}[4/4]${NC} Starting Dashboard Web Server (port 8080)..."
cd dashboard
nohup $PYTHON -m http.server 8080 > ../logs/dashboard.log 2>&1 &
cd ..
DASHBOARD_PID=$!
echo "Dashboard started (PID: $DASHBOARD_PID)"
echo $DASHBOARD_PID > .dashboard.pid

echo ""
echo "======================================"
echo -e "${GREEN}All services started!${NC}"
echo "======================================"
echo ""
echo "Services:"
echo -e "  ${GREEN}Agency API${NC}:       http://localhost:8000"
echo -e "  ${GREEN}Unified API${NC}:      http://localhost:8001"
echo -e "  ${GREEN}Dashboard${NC}:         http://localhost:8080"
echo ""
echo "API Docs:"
echo "  Agency:    http://localhost:8000/docs"
echo "  Unified:   http://localhost:8001/docs"
echo ""
echo "To stop all services:"
echo "  ./stop.sh"
echo ""
echo "To view logs:"
echo "  tail -f logs/*.log"
echo ""

# Open browser
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8080 2>/dev/null || true
elif command -v open &> /dev/null; then
    open http://localhost:8080 2>/dev/null || true
fi

echo -e "${YELLOW}Dashboard should open in your browser.${NC}"
