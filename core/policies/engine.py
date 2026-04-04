"""
Policy Engine — validates tasks against budget, retry, and approval rules
before the orchestrator dispatches them.

Reads configuration from core/policies/config.yaml.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from core.agents.base import BaseAgent

logger = logging.getLogger("policies.engine")

_DEFAULT_CONFIG = {
    "cost": {"default_limit": 50.0},
    "retry": {"max": 3},
    "approval": {"required_for": ["send_email", "deploy"]},
}


class PolicyEngine:
    """Gate-keeper that sits between the orchestrator and execution."""

    def __init__(self, config_path: str | None = None):
        self.config = self._load_config(config_path)

    # ── public ────────────────────────────────────────────────────────

    def validate(self, task: Dict[str, Any], agent: BaseAgent) -> bool:
        """Return True if the task is allowed to run."""
        if not self._check_budget(task, agent):
            logger.warning("Budget exceeded for agent on task %s", task.get("id"))
            return False

        if not self._check_retry(task):
            logger.warning("Max retries exceeded for task %s", task.get("id"))
            return False

        if not self._check_approval(task):
            logger.info("Task %s requires approval and is not yet approved", task.get("id"))
            return False

        return True

    # ── checks ────────────────────────────────────────────────────────

    def _check_budget(self, task: dict, agent: BaseAgent) -> bool:
        limit = self.config.get("cost", {}).get("default_limit", 50.0)
        agent_limit = getattr(agent, "budget_limit", limit)
        return agent.cost <= min(limit, agent_limit)

    def _check_retry(self, task: dict) -> bool:
        max_retries = self.config.get("retry", {}).get("max", 3)
        return task.get("retry_count", 0) <= max_retries

    def _check_approval(self, task: dict) -> bool:
        required_actions = self.config.get("approval", {}).get("required_for", [])
        task_type = task.get("task_type", "")

        if task_type in required_actions:
            return task.get("approval_status") == "approved"

        return True

    # ── config ────────────────────────────────────────────────────────

    def _load_config(self, config_path: str | None) -> dict:
        if config_path is None:
            config_path = os.path.join(
                Path(__file__).parent, "config.yaml"
            )

        try:
            with open(config_path, "r") as f:
                cfg = yaml.safe_load(f) or {}
            logger.info("Policy config loaded from %s", config_path)
            return cfg
        except FileNotFoundError:
            logger.warning("Policy config not found at %s — using defaults", config_path)
            return _DEFAULT_CONFIG
