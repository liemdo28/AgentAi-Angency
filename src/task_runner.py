"""
task_runner.py — Bridge between FastAPI and the LangGraph AI pipeline.

Responsibilities:
  1. Persist a Task to the DB before execution
  2. Build an AgenticState from the Task
  3. Invoke the compiled LangGraph
  4. Save results back to the Task record
  5. Return a clean result dict to the caller
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.agents.graph import get_graph
from src.agents.state import AgenticState
from src.config.settings import SETTINGS
from src.db.connection import init_db
from src.db.repositories.task_repo import TaskRepository
from src.tasks.models import Task, TaskStatus, now_iso

logger = logging.getLogger(__name__)


def _build_initial_state(task: Task, context: dict[str, Any] | None = None) -> AgenticState:
    """Construct the initial AgenticState from a Task record."""
    description = "\n\n".join(filter(None, [task.goal, task.description]))
    state: AgenticState = {
        "task_id": task.id,
        "task_description": description,
        "task_type": task.task_type or "",
        "account_id": task.account_id or "",
        "campaign_id": task.campaign_id or "",
        "quality_threshold": SETTINGS.SCORE_THRESHOLD,
        "retry_count": task.retry_count,
        "status": "IN_PROGRESS",
        "errors": [],
        "metadata": {
            "kpis": task.kpis,
            "priority": int(task.priority),
            "department": task.current_department,
            **(context or {}),
        },
    }
    return state


def run_task_sync(task: Task, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Execute a task through the full LangGraph AI pipeline synchronously.

    Steps:
      1. Init DB
      2. Mark task IN_PROGRESS and persist
      3. Build AgenticState
      4. Run graph.invoke(state)
      5. Persist results to Task record
      6. Return summary dict

    Returns a result dict with keys:
      task_id, status, score, final_output, review_history, errors
    """
    init_db()
    repo = TaskRepository()

    # ── 1. Mark as IN_PROGRESS ──────────────────────────────────────────
    task.status = TaskStatus.IN_PROGRESS
    task.started_at = now_iso()
    repo.upsert(task)

    try:
        # ── 2. Build initial state and invoke graph ─────────────────────
        initial_state = _build_initial_state(task, context)
        graph = get_graph()
        logger.info("Running task %s through LangGraph pipeline", task.id)
        result_state: AgenticState = graph.invoke(initial_state)

        # ── 3. Extract results from final state ─────────────────────────
        graph_status = result_state.get("status", "FAILED")
        score = float(result_state.get("leader_score", 0.0))
        final_output = result_state.get("specialist_output", "") or ""
        final_output_json = result_state.get("generated_outputs") or {}
        review_history = result_state.get("review_history") or []
        errors = result_state.get("errors") or []
        retry_count = int(result_state.get("retry_count", task.retry_count))

        # ── 4. Map graph status to TaskStatus ───────────────────────────
        _STATUS_MAP = {
            "PASSED": TaskStatus.PASSED,
            "REVIEW_FAILED": TaskStatus.ESCALATED,
            "FAILED": TaskStatus.FAILED,
            "IN_PROGRESS": TaskStatus.FAILED,  # should not end in this state
            "REVIEW": TaskStatus.FAILED,        # stuck in review = failure
        }
        if graph_status in _STATUS_MAP:
            new_status = _STATUS_MAP[graph_status]
        elif errors:
            new_status = TaskStatus.FAILED
        elif final_output and score > 0:
            new_status = TaskStatus.DONE
        else:
            # Unknown status: treat as failure, not success
            new_status = TaskStatus.FAILED
            errors.append(f"Unexpected graph status: {graph_status}")
            logger.warning("Task %s ended with unexpected status: %s", task.id, graph_status)

        # ── 5. Persist updated task ─────────────────────────────────────
        task.status = new_status
        task.score = score
        task.final_output_text = final_output
        task.final_output_json = final_output_json if isinstance(final_output_json, dict) else {}
        task.retry_count = retry_count
        task.completed_at = now_iso()
        repo.update(task)

        logger.info(
            "Task %s completed: status=%s score=%.1f",
            task.id, new_status.value, score,
        )

        return {
            "task_id": task.id,
            "status": new_status.value,
            "score": score,
            "final_output": final_output,
            "final_output_json": task.final_output_json,
            "review_history": review_history,
            "retry_count": retry_count,
            "errors": errors,
        }

    except Exception as exc:
        logger.exception("Task %s failed with exception: %s", task.id, exc)
        task.status = TaskStatus.FAILED
        task.notes = str(exc)
        task.completed_at = now_iso()
        try:
            repo.update(task)
        except Exception:
            pass
        return {
            "task_id": task.id,
            "status": TaskStatus.FAILED.value,
            "score": 0.0,
            "final_output": "",
            "final_output_json": {},
            "review_history": [],
            "retry_count": task.retry_count,
            "errors": [str(exc)],
        }
