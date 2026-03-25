"""
Task Progress node — advances the workflow to the next handoff step
or finalises the task when all steps are complete.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgenticState

logger = logging.getLogger(__name__)


def advance_task(state: AgenticState) -> AgenticState:
    """
    Task Progress node — check if there are more steps in the plan.

    If next step exists:
      - Mark current step as completed
      - Advance current_step_index
      - Set next_action = "continue" (graph loops back to router)

    If no more steps:
      - Mark task as PASSED
      - Set next_action = "done" (graph goes to email_notification -> END)
    """
    task_plan: list[dict[str, Any]] = state.get("task_plan", [])
    completed_steps: list[dict[str, Any]] = list(state.get("completed_steps", []))
    current_step: dict[str, Any] = dict(state.get("current_step", {}))
    current_step_index: int = int(state.get("current_step_index", 0))
    generated_outputs: dict[str, Any] = dict(state.get("generated_outputs", {}))

    # Build the completed step record
    completed_record: dict[str, Any] = {
        "index": current_step_index,
        "name": current_step.get("name", f"Step {current_step_index + 1}"),
        "from_department": current_step.get("from_department", state.get("from_department", "")),
        "to_department": current_step.get("to_department", state.get("to_department", "")),
        "objective": current_step.get("objective", ""),
        "outputs": dict(generated_outputs),
        "leader_score": float(state.get("leader_score", 0)),
        "leader_feedback": state.get("leader_feedback", ""),
    }
    completed_steps.append(completed_record)

    next_index = current_step_index + 1

    if next_index < len(task_plan):
        # More steps remain — advance to next step
        next_step = dict(task_plan[next_index])
        logger.info(
            "Task progress: step %d/%d done. Advancing to step %d: %s",
            current_step_index + 1,
            len(task_plan),
            next_index + 1,
            next_step.get("name", "?"),
        )

        # Merge outputs from this step into accumulated artifacts
        new_artifacts: dict[str, Any] = {
            **state.get("artifacts", {}),
            **state.get("required_inputs", {}),
            **generated_outputs,
        }

        return {
            **state,
            "current_step_index": next_index,
            "current_step": next_step,
            "completed_steps": completed_steps,
            "artifacts": new_artifacts,
            "specialist_output": "",   # reset for next specialist run
            "generated_outputs": {},    # reset for next specialist run
            "leader_score": 0.0,
            "leader_feedback": "",
            "retry_count": 0,
            "next_action": "continue",
            "metadata": {
                **state.get("metadata", {}),
                "steps_completed": len(completed_steps),
            },
        }
    else:
        # All steps done — finalise
        logger.info(
            "Task progress: all %d steps complete. Finalising task.",
            len(completed_steps),
        )

        # Build final_outputs: accumulated results from all steps
        final_outputs: dict[str, Any] = {
            **{},
        }
        for step_record in completed_steps:
            for key, value in step_record.get("outputs", {}).items():
                # Prefixed by step name to avoid collisions
                step_name = step_record.get("name", "step")
                final_key = f"[{step_name}] {key}"
                final_outputs[final_key] = value

        return {
            **state,
            "completed_steps": completed_steps,
            "final_outputs": final_outputs,
            "status": "PASSED",
            "next_action": "done",
            "artifacts": {
                **state.get("artifacts", {}),
                **generated_outputs,
            },
            "metadata": {
                **state.get("metadata", {}),
                "steps_completed": len(completed_steps),
                "all_steps_done": True,
            },
        }
