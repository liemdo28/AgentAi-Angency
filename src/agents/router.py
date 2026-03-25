"""
Router node — analyses the task description and selects the matching
HandoffPolicy from the 29 inter-department routes.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from src.agents.state import AgenticState
from src.llm import get_llm
from src.config import SETTINGS

from src.policies.interdepartment_policies import POLICIES

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the Agency Router. Your job is to analyse a task description
and determine the correct department routing within the agency workflow.

You have access to the full list of valid inter-department routes.
Each route is defined as:
  from_department → to_department
    required_inputs : what the sending department must provide
    expected_outputs : what the receiving department must deliver
    sla_hours       : maximum hours allowed
    approver_role   : which leader approves the output

Return a JSON object with:
  from_department  : str (e.g. "sales", "strategy")
  to_department    : str
  reasoning        : str (brief explanation of why this route was chosen)

If the task is ambiguous, pick the most reasonable route and explain
the ambiguity in the reasoning field.
"""


def route_task(state: AgenticState) -> AgenticState:
    """
    Router node — reads task_description, picks HandoffPolicy.
    Updates state with from_department, to_department, policy dict.
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

    # Build policy summary for the LLM to reason over
    policy_lines = []
    for p in POLICIES:
        policy_lines.append(
            f"  {p.from_department} → {p.to_department}\n"
            f"    inputs: {', '.join(p.required_inputs)}\n"
            f"    outputs: {', '.join(p.expected_outputs)}\n"
            f"    SLA: {p.sla_hours}h | approver: {p.approver_role}"
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
        response = llm.complete(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=512,
        )

        import json, re
        # Extract JSON block
        match = re.search(r"\{[\s\S]+?\}", response)
        if not match:
            raise ValueError("No JSON found in LLM response")

        parsed: dict[str, Any] = json.loads(match.group())

        from_dept = parsed.get("from_department", "").strip().lower()
        to_dept = parsed.get("to_department", "").strip().lower()

        # Validate the route exists
        matched_policy = None
        for p in POLICIES:
            if p.from_department == from_dept and p.to_department == to_dept:
                matched_policy = p
                break

        if matched_policy is None:
            logger.warning(
                f"Router: LLM selected invalid route {from_dept}→{to_dept}. "
                f"Falling back to scanning for best match."
            )
            return {
                **state,
                "task_id": task_id,
                "next_action": "invalid",
                "errors": [
                    *state.get("errors", []),
                    f"Router: no valid route for {from_dept}→{to_dept}",
                ],
            }

        # Serialise HandoffPolicy to dict for LangGraph state
        policy_dict = {
            "from_department": matched_policy.from_department,
            "to_department": matched_policy.to_department,
            "required_inputs": list(matched_policy.required_inputs),
            "expected_outputs": list(matched_policy.expected_outputs),
            "sla_hours": matched_policy.sla_hours,
            "approver_role": matched_policy.approver_role,
        }

        logger.info(
            f"Router: routed '{task_desc[:50]}...' → "
            f"{matched_policy.from_department}→{matched_policy.to_department}"
        )

        return {
            **state,
            "task_id": task_id,
            "from_department": matched_policy.from_department,
            "to_department": matched_policy.to_department,
            "policy": policy_dict,
            "status": "IN_PROGRESS",
            "next_action": "valid",
        }

    except Exception as exc:
        logger.exception(f"Router node failed: {exc}")
        return {
            **state,
            "task_id": task_id,
            "next_action": "invalid",
            "errors": [*state.get("errors", []), f"Router error: {exc}"],
        }
