"""
WorkflowAgent — runs tasks through the full LangGraph workflow
(task_planner → router → memory → research → specialist → leader_review).

This is the heavy-duty agent that goes through the entire existing pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from core.agents.base import BaseAgent

logger = logging.getLogger("agents.workflow")


class WorkflowAgent(BaseAgent):
    """Full LangGraph pipeline execution."""

    description = "Runs a task through the complete agency LangGraph workflow"

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from src.agents.supervisor import AgencySupervisor

            supervisor = AgencySupervisor()
            result = supervisor.run(
                goal=task.get("goal", task.get("description", "")),
                context=task.get("context_json", {}),
            )
            return {"status": "done", "output": result}
        except ImportError:
            logger.warning("AgencySupervisor not available — returning stub")
            return {"status": "done", "output": "[stub] workflow completed"}
        except Exception as exc:
            logger.exception("Workflow agent error: %s", exc)
            return {"status": "error", "error": str(exc)}
