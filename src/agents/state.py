"""
AgenticState — shared state for the LangGraph workflow.

This TypedDict is the central data structure that flows through every node
in the AI agency graph.  Every node reads from it and returns updates to it.
"""
from __future__ import annotations

from typing import Any, Literal

from typing_extensions import NotRequired, TypedDict


class AgenticState(TypedDict, total=False):
    """
    Central state passed through the LangGraph workflow.

    Fields
    ------
    task_id          : unique identifier for this workflow run
    task_description : raw user/caller description of what needs to be done
    from_department  : department that originates the task
    to_department    : department that should receive/process the task
    policy           : the matched HandoffPolicy (serialised to dict)
    required_inputs  : dict of input artifacts available for this task
    research_results : results from the web/data research node
    specialist_output: raw text/artifact produced by the dept specialist
    generated_outputs: structured outputs (per policy.expected_outputs)
    final_outputs    : accumulated outputs from all steps in a multi-step task
    artifacts        : accumulated working artifacts across all completed steps
    leader_score     : numeric quality score 0-100 assigned by leader reviewer
    leader_feedback  : human-readable feedback when score < SCORE_THRESHOLD
    quality_threshold: per-step quality threshold (default 98.0)
    quality_breakdown: dict of per-criterion scores
    status           : DRAFT | IN_PROGRESS | REVIEW | PASSED | FAILED
    conversation_history: list of {role, content} dicts for LLM memory
    errors           : list of error messages encountered along the way
    retry_count      : number of times this task has been re-routed after failure
    next_action      : routing hint for conditional edges
    email_sent       : bool flag indicating email was dispatched
    output_files     : list of file paths generated during the workflow
    metadata         : arbitrary extra context attached by any node

    Business task layer
    task_type        : type of task (from task templates)
    task_plan        : ordered list of step definitions
    current_step_index: index of the currently-executing step
    current_step    : dict describing the current step
    completed_steps : list of completed step records with outputs + scores
    review_history  : list of review decisions for audit trail
    planning_mode   : how the plan was created (template | llm_generated | router_only)
    routing_reasoning: explanation from the router
    """

    # ── Task Identification ─────────────────────────────────────────
    task_id: str
    task_description: str

    # ── Routing ─────────────────────────────────────────────────────
    from_department: NotRequired[str]
    to_department: NotRequired[str]

    # ── Policy Context ───────────────────────────────────────────────
    policy: NotRequired[dict[str, Any]]

    # ── Artifacts ────────────────────────────────────────────────────
    required_inputs: NotRequired[dict[str, Any]]
    research_results: NotRequired[dict[str, Any]]
    specialist_output: NotRequired[str]
    generated_outputs: NotRequired[dict[str, Any]]
    final_outputs: NotRequired[dict[str, Any]]
    artifacts: NotRequired[dict[str, Any]]

    # ── Leader Review ────────────────────────────────────────────────
    leader_score: NotRequired[float]
    leader_feedback: NotRequired[str]
    quality_threshold: NotRequired[float]
    quality_breakdown: NotRequired[dict[str, float]]

    # ── Workflow Status ─────────────────────────────────────────────
    status: NotRequired[Literal[
        "DRAFT",
        "IN_PROGRESS",
        "REVIEW",
        "PASSED",
        "FAILED",
        "REVIEW_FAILED",
    ]]
    conversation_history: NotRequired[list[dict[str, str]]]

    # ── Business Task Layer ─────────────────────────────────────────
    task_type: NotRequired[str]
    task_plan: NotRequired[list[dict[str, Any]]]
    current_step_index: NotRequired[int]
    current_step: NotRequired[dict[str, Any]]
    completed_steps: NotRequired[list[dict[str, Any]]]
    review_history: NotRequired[list[dict[str, Any]]]
    planning_mode: NotRequired[str]
    routing_reasoning: NotRequired[str]

    # ── Error / Retry Tracking ───────────────────────────────────────
    errors: NotRequired[list[str]]
    retry_count: NotRequired[int]

    # ── Routing Hints ───────────────────────────────────────────────
    next_action: NotRequired[Literal[
        "valid",
        "invalid",
        "passed",
        "failed",
        "escalate",
        "retry",
        "continue",
        "done",
    ]]

    # ── Side Effects ────────────────────────────────────────────────
    email_sent: NotRequired[bool]
    output_files: NotRequired[list[str]]

    # ── Misc ─────────────────────────────────────────────────────────
    metadata: NotRequired[dict[str, Any]]
