"""
Task templates — pre-defined multi-step workflows for common agency tasks.
Provides `build_task_plan` and `list_available_task_types` for CLI and supervisor.
"""
from __future__ import annotations

from typing import Any


# Re-export the templates from task_planner for convenience
from src.agents.task_planner import TASK_TEMPLATES


def build_task_plan(
    task_description: str,
    *,
    from_department: str = "",
    to_department: str = "",
    task_type: str = "",
) -> dict[str, Any]:
    """
    Build a task plan from a description and optional constraints.
    Uses the same template-matching + LLM logic as the task planner node.

    Returns a dict with: task_type, planning_mode, steps.
    """
    from src.agents.task_planner import _match_template, _llm_generate_plan

    if task_type and task_type in TASK_TEMPLATES:
        tmpl = TASK_TEMPLATES[task_type]
        return {
            "task_type": task_type,
            "planning_mode": "template",
            "steps": list(tmpl["steps"]),
        }

    matched_type, planning_mode, steps = _match_template(task_description)

    if planning_mode == "router_only" and not (from_department and to_department):
        llm_plan = _llm_generate_plan(task_description, from_department, to_department)
        return llm_plan

    return {
        "task_type": matched_type,
        "planning_mode": planning_mode,
        "steps": steps,
    }


def list_available_task_types() -> list[str]:
    """Return the list of available task-type template names."""
    return list(TASK_TEMPLATES.keys())
