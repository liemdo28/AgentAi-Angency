"""
DepartmentAgent — wraps the existing department leader/employee system
so the orchestrator can dispatch work to any of the 11 departments.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Dict

from core.agents.base import BaseAgent

logger = logging.getLogger("agents.department")


class DepartmentAgent(BaseAgent):
    """Generic adapter for an existing department module.

    Usage:
        agent = DepartmentAgent("creative")
        registry.register("dept-creative", agent)
    """

    def __init__(self, department_name: str):
        self.department_name = department_name
        self.description = f"Department agent for {department_name}"
        self._leader = None
        self._employees = []
        self._load_department()

    def _load_department(self) -> None:
        try:
            mod_leader = importlib.import_module(f"departments.{self.department_name}.leader")
            mod_employees = importlib.import_module(f"departments.{self.department_name}.employees")
            self._leader = getattr(mod_leader, "leader", None)
            self._employees = getattr(mod_employees, "employees", [])
            logger.info("Loaded department '%s' — leader=%s, employees=%d",
                        self.department_name,
                        getattr(self._leader, "full_name", "?"),
                        len(self._employees))
        except (ImportError, AttributeError) as exc:
            logger.warning("Could not load department '%s': %s", self.department_name, exc)

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Delegate to the existing LangGraph specialist node via task_runner."""
        # Import here to avoid circular deps at module load time
        try:
            from src.task_runner import run_task_sync
            result = run_task_sync(task)
            return {"status": "done", "department": self.department_name, "output": result}
        except ImportError:
            logger.warning("task_runner not available — returning stub")
            return {
                "status": "done",
                "department": self.department_name,
                "output": f"[stub] processed by {self.department_name}",
            }
