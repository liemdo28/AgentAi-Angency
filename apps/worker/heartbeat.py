"""
Heartbeat Worker — runs the orchestrator loop as a background process.

This is the daemon that makes the system autonomous.
Start it alongside the API:
    python -m apps.worker.heartbeat
"""

from __future__ import annotations

import logging
import os
import signal
import sys

# Ensure project root is on PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.orchestrator.engine import Orchestrator
from core.orchestrator.registry import AgentRegistry
from core.policies.engine import PolicyEngine
from core.agents import (
    DepartmentAgent,
    WorkflowAgent,
    MarketingAgent,
    ReviewAgent,
    TaskFlowAgent,
    DevAgent,
)
from db.repository import ControlPlaneDB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("worker.heartbeat")

# ── Department list (matches your existing 11 departments) ────────────
DEPARTMENTS = [
    "account", "creative", "crm_automation", "data", "finance",
    "media", "operations", "production", "sales", "strategy", "tech",
]


def build_registry() -> AgentRegistry:
    """Register all known agents."""
    registry = AgentRegistry()

    # 1) Full workflow agent
    registry.register("workflow", WorkflowAgent())

    # 2) Department agents (wrapping existing department modules)
    for dept in DEPARTMENTS:
        registry.register(f"dept-{dept}", DepartmentAgent(dept))

    # 3) Connector agents
    registry.register("connector-marketing", MarketingAgent())
    registry.register("connector-review", ReviewAgent())
    registry.register("connector-taskflow", TaskFlowAgent())

    # 4) Dev agent (code read/write/deploy)
    registry.register("dev-agent", DevAgent())

    logger.info("Registry built: %d agents", len(registry))
    return registry


def main() -> None:
    db = ControlPlaneDB()
    registry = build_registry()
    policy = PolicyEngine()

    cycle_interval = float(os.getenv("ORCHESTRATOR_INTERVAL", "10"))

    orchestrator = Orchestrator(
        db=db,
        agent_registry=registry,
        policy_engine=policy,
        cycle_interval=cycle_interval,
    )

    # Graceful shutdown on SIGINT / SIGTERM
    def _shutdown(sig, frame):
        logger.info("Shutting down heartbeat worker...")
        orchestrator.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("=== Heartbeat Worker Started (interval=%ss) ===", cycle_interval)
    orchestrator.run_forever()


if __name__ == "__main__":
    main()
