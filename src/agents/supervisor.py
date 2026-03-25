"""
Supervisor — top-level entry point that wraps the LangGraph.
Receives a task and orchestrates the full workflow.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from src.agents.graph import get_graph
from src.agents.state import AgenticState

logger = logging.getLogger(__name__)


class AgencySupervisor:
    """
    High-level supervisor that runs the full AI agency workflow.

    Usage:
        supervisor = AgencySupervisor()
        result = supervisor.run(task_description="...", required_inputs={...})
    """

    def __init__(self) -> None:
        self._graph = get_graph()

    def run(
        self,
        task_description: str,
        *,
        required_inputs: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
        from_department: Optional[str] = None,
        to_department: Optional[str] = None,
        task_type: Optional[str] = None,
        quality_threshold: float = 98.0,
    ) -> dict[str, Any]:
        """
        Run the full workflow for a task.

        Parameters
        ----------
        task_description : Human-readable task description
        required_inputs  : Optional dict of input artifacts
        task_id          : Optional override for the task ID
        from_department : Optional pre-specified source dept (skips router)
        to_department   : Optional pre-specified target dept (skips router)
        task_type       : Optional task type template override
        quality_threshold: Per-step quality threshold (default 98.0)

        Returns
        -------
        Final AgenticState dict after the workflow completes
        """
        task_id = task_id or str(uuid.uuid4())
        initial_artifacts = dict(required_inputs or {})

        initial_state: AgenticState = {
            "task_id": task_id,
            "task_description": task_description,
            "from_department": from_department or "",
            "to_department": to_department or "",
            "required_inputs": initial_artifacts,
            "artifacts": initial_artifacts,
            "research_results": {},
            "generated_outputs": {},
            "final_outputs": {},
            "leader_score": 0.0,
            "leader_feedback": "",
            "quality_threshold": quality_threshold,
            "quality_breakdown": {},
            "status": "DRAFT",
            "conversation_history": [],
            "errors": [],
            "retry_count": 0,
            "next_action": "",
            "email_sent": False,
            "output_files": [],
            "task_type": task_type or "",
            "task_plan": [],
            "current_step_index": 0,
            "current_step": {},
            "completed_steps": [],
            "review_history": [],
            "metadata": {},
        }

        logger.info("[%s] Starting workflow: %s...", task_id, task_description[:80])

        start = time.time()
        try:
            final_state: dict[str, Any] = self._graph.invoke(initial_state)
        except Exception as exc:
            logger.exception("[%s] Graph invocation failed: %s", task_id, exc)
            final_state = {
                **initial_state,
                "status": "FAILED",
                "errors": [*initial_state.get("errors", []), f"Graph error: {exc}"],
            }

        elapsed = time.time() - start
        logger.info(
            "[%s] Workflow done in %.1fs - status=%s score=%.0f/100",
            task_id,
            elapsed,
            final_state.get("status"),
            final_state.get("leader_score", 0),
        )

        return final_state

    def run_stream(
        self,
        task_description: str,
        *,
        required_inputs: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ):
        """
        Streaming version — yields state updates as the graph runs.
        Useful for real-time UI updates.
        """
        task_id = task_id or str(uuid.uuid4())

        initial_state: AgenticState = {
            "task_id": task_id,
            "task_description": task_description,
            "required_inputs": dict(required_inputs or {}),
            "artifacts": dict(required_inputs or {}),
            "status": "DRAFT",
            "errors": [],
            "retry_count": 0,
            "task_plan": [],
            "completed_steps": [],
            "review_history": [],
        }

        logger.info("[%s] Starting STREAM workflow", task_id)
        for state_update in self._graph.stream(initial_state):
            yield state_update

    def run_as_ceo(
        self,
        goal: str,
        *,
        mode: str = "CREATE_TASK",
    ) -> dict[str, Any]:
        """
        Run the CEO Brain layer as the outer orchestrator.
        This wraps the LangGraph workflow with agency-wide goal interpretation,
        task creation, SLA monitoring, and intervention logic.

        Modes:
        - CREATE_TASK: interpret goal -> create Task -> run LangGraph
        - MONITOR    : scan active tasks -> check SLA/KPI/health -> decisions
        - INTERVENE  : handle SLA breaches and escalations

        Parameters
        ----------
        goal : Natural-language goal from the operator
        mode : CREATE_TASK | MONITOR | INTERVENE

        Returns
        -------
        dict with keys: action, tasks_affected, decisions, summary
        """
        from src.ceo.brain import CEOBrain

        ceo = CEOBrain()
        return ceo.run(goal, mode=mode)
