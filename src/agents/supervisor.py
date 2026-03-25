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
from src.config import SETTINGS

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
    ) -> dict[str, Any]:
        """
        Run the full workflow for a task.

        Parameters
        ----------
        task_description : Human-readable task description
        required_inputs   : Optional dict of input artifacts (e.g. {"lead_profile": {...}})
        task_id          : Optional override for the task ID
        from_department  : Optional pre-specified source dept (skips router)
        to_department    : Optional pre-specified target dept (skips router)

        Returns
        -------
        Final AgenticState dict after the workflow completes
        """
        task_id = task_id or str(uuid.uuid4())

        initial_state: AgenticState = {
            "task_id": task_id,
            "task_description": task_description,
            "from_department": from_department or "",
            "to_department": to_department or "",
            "required_inputs": required_inputs or {},
            "research_results": {},
            "generated_outputs": {},
            "leader_score": 0.0,
            "leader_feedback": "",
            "status": "DRAFT",
            "conversation_history": [],
            "errors": [],
            "retry_count": 0,
            "next_action": "",
            "email_sent": False,
            "output_files": [],
            "metadata": {},
        }

        logger.info(f"[{task_id}] Starting workflow: {task_description[:80]}...")

        start = time.time()
        try:
            # Invoke the compiled LangGraph
            final_state: dict[str, Any] = self._graph.invoke(initial_state)
        except Exception as exc:
            logger.exception(f"[{task_id}] Graph invocation failed: {exc}")
            final_state = {
                **initial_state,
                "status": "FAILED",
                "errors": [*initial_state.get("errors", []), f"Graph error: {exc}"],
            }

        elapsed = time.time() - start
        logger.info(
            f"[{task_id}] Workflow done in {elapsed:.1f}s — "
            f"status={final_state.get('status')} "
            f"score={final_state.get('leader_score', 0):.0f}/100"
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
            "required_inputs": required_inputs or {},
            "status": "DRAFT",
            "errors": [],
            "retry_count": 0,
        }

        logger.info(f"[{task_id}] Starting STREAM workflow")
        for state_update in self._graph.stream(initial_state):
            yield state_update
