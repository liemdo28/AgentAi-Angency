"""
Orchestrator Engine — the brain of the Control Plane.

Runs a continuous cycle:  fetch pending tasks → check policies → dispatch to agents → record results.
Connects into the existing LangGraph workflow and CEO brain as execution backends.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.agents.base import BaseAgent
    from core.orchestrator.registry import AgentRegistry
    from core.policies.engine import PolicyEngine
    from db.repository import ControlPlaneDB

logger = logging.getLogger("orchestrator.engine")


class Orchestrator:
    """Central loop that turns pending tasks into executed jobs."""

    def __init__(
        self,
        db: ControlPlaneDB,
        agent_registry: AgentRegistry,
        policy_engine: PolicyEngine,
        cycle_interval: float = 10.0,
    ):
        self.db = db
        self.agent_registry = agent_registry
        self.policy_engine = policy_engine
        self.cycle_interval = cycle_interval
        self._running = False

    # ── public ────────────────────────────────────────────────────────

    def run_forever(self) -> None:
        """Blocking loop — meant for the worker process."""
        self._running = True
        logger.info("Orchestrator started (interval=%ss)", self.cycle_interval)
        while self._running:
            try:
                self.run_cycle()
            except Exception:
                logger.exception("Orchestrator cycle error")
            time.sleep(self.cycle_interval)

    def stop(self) -> None:
        self._running = False

    def run_cycle(self) -> dict:
        """Single pass: fetch → check → execute → record.  Returns cycle stats."""
        stats = {"checked": 0, "dispatched": 0, "skipped": 0, "failed": 0}
        tasks = self.db.get_pending_tasks()
        stats["checked"] = len(tasks)

        for task in tasks:
            agent = self.agent_registry.get(task["assigned_agent_id"])
            if agent is None:
                logger.warning("No agent registered for %s", task["assigned_agent_id"])
                stats["skipped"] += 1
                continue

            # policy gate
            if not self._check_policy(task, agent):
                logger.info("Policy blocked task %s", task["id"])
                stats["skipped"] += 1
                continue

            ok = self._execute_task(task, agent)
            if ok:
                stats["dispatched"] += 1
            else:
                stats["failed"] += 1

        logger.debug("Cycle done: %s", stats)
        return stats

    # ── internals ─────────────────────────────────────────────────────

    def _check_policy(self, task: dict, agent: BaseAgent) -> bool:
        return self.policy_engine.validate(task, agent)

    def _execute_task(self, task: dict, agent: BaseAgent) -> bool:
        task_id = task["id"]
        self.db.update_task_status(task_id, "running")
        started = datetime.now(timezone.utc).isoformat()

        try:
            result = agent.run(task)
            self.db.save_job(
                task_id=task_id,
                agent_id=task["assigned_agent_id"],
                input_data=task.get("context_json", {}),
                output_data=result,
                started_at=started,
            )
            self.db.update_task_status(task_id, "success")
            return True

        except Exception as exc:
            logger.exception("Task %s failed: %s", task_id, exc)
            self.db.update_task_status(task_id, "failed")
            self._handle_retry(task)
            return False

    def _handle_retry(self, task: dict) -> None:
        max_retries = self.policy_engine.config.get("retry", {}).get("max", 3)
        if task.get("retry_count", 0) < max_retries:
            self.db.retry_task(task["id"])
            logger.info("Retrying task %s (attempt %d)", task["id"], task["retry_count"] + 1)
