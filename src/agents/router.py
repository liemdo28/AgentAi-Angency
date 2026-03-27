"""
Router node — analyses the task description and selects the matching
handoff policy from the inter-department routes.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from src.agents.state import AgenticState
from src.llm import get_llm
from src.policies.interdepartment_policies import POLICIES
from src.utils.json_utils import extract_first_json_object

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the Agency Router. Your job is to analyse a task description
and determine the correct department routing within the agency workflow.

You have access to the full list of valid inter-department routes.
Each route is defined as:
  from_department -> to_department
    inputs : what the sending department must provide
    outputs: what the receiving department must deliver
    SLA: maximum hours allowed
    approver: which leader approves the output

Return a JSON object with:
  from_department : str (e.g. "sales", "strategy")
  to_department   : str
  reasoning       : str (brief explanation of why this route was chosen)

If the task is ambiguous, pick the most reasonable route and explain
the ambiguity in the reasoning field.
"""

DEPARTMENT_HINTS: dict[str, tuple[str, ...]] = {
    "account": ("account", "client", "brief", "scope", "feedback"),
    "strategy": ("strategy", "positioning", "audience", "persona", "funnel"),
    "creative": ("creative", "copy", "visual", "asset", "concept"),
    "media": ("media", "channel", "budget", "roas", "ads"),
    "tech": ("tech", "tracking", "landing", "implementation", "website"),
    "data": ("data", "dashboard", "metrics", "analysis", "report"),
    "production": ("production", "shoot", "video", "raw footage", "delivery"),
    "sales": ("sales", "pipeline", "pricing", "lead", "deal"),
    "operations": ("operations", "resource", "capacity", "process", "staffing"),
    "finance": ("finance", "margin", "invoice", "budget", "profit"),
    "crm_automation": ("crm", "lifecycle", "retention", "automation", "segment"),
}


def _find_policy(from_department: str, to_department: str):
    """Find a HandoffPolicy by from/to department pair."""
    for policy in POLICIES:
        if policy.from_department == from_department and policy.to_department == to_department:
            return policy
    return None


def _policy_to_dict(policy) -> dict[str, Any]:
    """Serialise a HandoffPolicy to a plain dict."""
    return {
        "from_department": policy.from_department,
        "to_department": policy.to_department,
        "required_inputs": list(policy.required_inputs),
        "expected_outputs": list(policy.expected_outputs),
        "sla_hours": policy.sla_hours,
        "approver_role": policy.approver_role,
    }


def _score_policy(task_desc: str, policy) -> int:
    """Score how well a policy matches a task description (heuristic)."""
    score = 0
    haystack = task_desc.lower()

    for hint in DEPARTMENT_HINTS.get(policy.from_department, ()):
        if hint in haystack:
            score += 2
    for hint in DEPARTMENT_HINTS.get(policy.to_department, ()):
        if hint in haystack:
            score += 3
    for token in (*policy.required_inputs, *policy.expected_outputs):
        if token in haystack or token.replace("_", " ") in haystack:
            score += 4

    return score


def _heuristic_route(state: AgenticState) -> AgenticState:
    """Fallback routing using keyword scoring when LLM is unavailable."""
    task_desc = state.get("task_description", "")
    specified_from = state.get("from_department", "").strip().lower()
    specified_to = state.get("to_department", "").strip().lower()

    # If both departments are explicitly provided, use them directly
    if specified_from and specified_to:
        matched = _find_policy(specified_from, specified_to)
        if matched:
            return {
                **state,
                "policy": _policy_to_dict(matched),
                "routing_reasoning": "Used explicitly provided route.",
                "quality_threshold": float(
                    state.get("quality_threshold")
                    or state.get("current_step", {}).get("quality_threshold", 98.0)
                ),
                "status": "IN_PROGRESS",
                "next_action": "valid",
            }

    # Score all policies and pick the best
    ranked = sorted(POLICIES, key=lambda p: _score_policy(task_desc, p), reverse=True)
    best = ranked[0] if ranked else None
    if best is None or _score_policy(task_desc, best) == 0:
        return {
            **state,
            "next_action": "invalid",
            "errors": [*state.get("errors", []), "Router could not infer a valid route"],
        }

    return {
        **state,
        "from_department": best.from_department,
        "to_department": best.to_department,
        "policy": _policy_to_dict(best),
        "routing_reasoning": "Selected via keyword matching heuristic.",
        "quality_threshold": float(
            state.get("quality_threshold")
            or state.get("current_step", {}).get("quality_threshold", 98.0)
        ),
        "status": "IN_PROGRESS",
        "next_action": "valid",
    }


def route_task(state: AgenticState) -> AgenticState:
    """
    Router node — reads task_description, picks HandoffPolicy.
    Supports both multi-step (from task plan) and single-step (ad-hoc) tasks.
    """
    task_desc = state.get("task_description", "")
    task_id = state.get("task_id") or str(uuid.uuid4())

    if not task_desc:
        logger.warning("Router: empty task_description")
        return {
            **state,
            "task_id": task_id,
            "next_action": "invalid",
            "errors": [*(state.get("errors", [])), "Empty task description"],
        }

    # ── Multi-step mode: use the current planned step ────────────────
    current_step = state.get("current_step", {})
    if current_step:
        logger.info(
            "Router: using planned step '%s' (%s->%s)",
            current_step.get("name", "?"),
            current_step.get("from_department", "?"),
            current_step.get("to_department", "?"),
        )
        return {
            **state,
            "task_id": task_id,
            "from_department": current_step.get("from_department", ""),
            "to_department": current_step.get("to_department", ""),
            "policy": {
                "from_department": current_step.get("from_department", ""),
                "to_department": current_step.get("to_department", ""),
                "required_inputs": list(current_step.get("required_inputs", [])),
                "expected_outputs": list(current_step.get("expected_outputs", [])),
                "sla_hours": current_step.get("sla_hours", 0),
                "approver_role": current_step.get("approver_role", ""),
            },
            "quality_threshold": float(current_step.get("quality_threshold", 98.0)),
            "routing_reasoning": f"Using planned business step: {current_step.get('objective', '')}",
            "status": "IN_PROGRESS",
            "next_action": "valid",
        }

    # ── Single-step mode: LLM-based routing ───────────────────────────
    policy_lines = []
    for policy in POLICIES:
        policy_lines.append(
            f"  {policy.from_department} -> {policy.to_department}\n"
            f"    inputs: {', '.join(policy.required_inputs)}\n"
            f"    outputs: {', '.join(policy.expected_outputs)}\n"
            f"    SLA: {policy.sla_hours}h | approver: {policy.approver_role}"
        )
    policy_summary = "\n".join(policy_lines)

    user_prompt = f"""Task description:
{task_desc}

Available routes ({len(POLICIES)} total):
{policy_summary}

Return JSON only (no markdown):
{{"from_department": "...", "to_department": "...", "reasoning": "..."}}"""

    try:
        llm = get_llm()
        if llm.primary_provider is None:
            raise RuntimeError("No configured LLM provider for router")

        response = llm.complete(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            temperature=0.0,  # deterministic routing (RISK-009)
            max_tokens=512,
        )
        parsed: dict[str, Any] = extract_first_json_object(response)

        from_dept = parsed.get("from_department", "").strip().lower()
        to_dept = parsed.get("to_department", "").strip().lower()
        matched_policy = _find_policy(from_dept, to_dept)

        if matched_policy is None:
            raise ValueError(f"Router selected invalid route {from_dept}->{to_dept}")

        logger.info(
            "Router: routed '%s' -> %s->%s",
            task_desc[:50],
            matched_policy.from_department,
            matched_policy.to_department,
        )

        return {
            **state,
            "task_id": task_id,
            "from_department": matched_policy.from_department,
            "to_department": matched_policy.to_department,
            "policy": _policy_to_dict(matched_policy),
            "routing_reasoning": parsed.get("reasoning", ""),
            "quality_threshold": float(state.get("quality_threshold", 98.0)),
            "status": "IN_PROGRESS",
            "next_action": "valid",
        }

    except Exception as exc:
        logger.warning("Router LLM path failed, falling back to heuristic: %s", exc)
        heuristic_state = _heuristic_route({**state, "task_id": task_id})
        if heuristic_state.get("next_action") == "valid":
            heuristic_state["metadata"] = {
                **state.get("metadata", {}),
                "router_fallback_reason": str(exc),
            }
            return heuristic_state
        return {
            **heuristic_state,
            "errors": [*heuristic_state.get("errors", []), f"Router error: {exc}"],
        }
