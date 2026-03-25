"""
AgenticState — shared state for the LangGraph workflow.

This TypedDict is the central data structure that flows through every node
in the AI agency graph.  Every node reads from it and returns updates to it.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

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
    leader_score     : numeric quality score 0-100 assigned by leader reviewer
    leader_feedback  : human-readable feedback when score < SCORE_THRESHOLD
    status           : DRAFT | IN_PROGRESS | REVIEW | PASSED | FAILED
    conversation_history: list of {role, content} dicts for LLM memory
    errors           : list of error messages encountered along the way
    retry_count      : number of times this task has been re-routed after failure
    next_action      : routing hint for conditional edges
    email_sent       : bool flag indicating email was dispatched
    output_files     : list of file paths generated during the workflow
    metadata         : arbitrary extra context attached by any node
    """

    # ── Task Identification ─────────────────────────────────────────
    task_id: str
    task_description: str

    # ── Routing ─────────────────────────────────────────────────────
    from_department: NotRequired[str]
    to_department: NotRequired[str]

    # ── Policy Context ───────────────────────────────────────────────
    # Stored as dict so it is JSON-serialisable across graph nodes
    policy: NotRequired[dict[str, Any]]

    # ── Artifacts ────────────────────────────────────────────────────
    required_inputs: NotRequired[dict[str, Any]]
    research_results: NotRequired[dict[str, Any]]
    specialist_output: NotRequired[str]
    generated_outputs: NotRequired[dict[str, Any]]

    # ── Leader Review ────────────────────────────────────────────────
    leader_score: NotRequired[float]
    leader_feedback: NotRequired[str]

    # ── Workflow Status ─────────────────────────────────────────────
    status: NotRequired[Literal[
        "DRAFT",
        "IN_PROGRESS",
        "REVIEW",
        "PASSED",
        "FAILED",
        "REVIEW_FAILED",  # passed review but score < threshold
    ]]
    conversation_history: NotRequired[list[dict[str, str]]]

    # ── Error / Retry Tracking ───────────────────────────────────────
    errors: NotRequired[list[str]]
    retry_count: NotRequired[int]

    # ── Routing Hints ───────────────────────────────────────────────
    # Used by conditional edges to decide next node
    next_action: NotRequired[Literal[
        "valid",
        "invalid",
        "passed",
        "failed",
        "escalate",
        "retry",
        "done",
    ]]

    # ── Side Effects ────────────────────────────────────────────────
    email_sent: NotRequired[bool]
    output_files: NotRequired[list[str]]

    # ── Misc ─────────────────────────────────────────────────────────
    metadata: NotRequired[dict[str, Any]]
