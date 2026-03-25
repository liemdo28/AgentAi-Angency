"""
Leader Reviewer node — scores specialist output and decides pass/fail/retry.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgenticState
from src.llm import get_llm
from src.config import SETTINGS

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = SETTINGS.SCORE_THRESHOLD  # 98.0
MAX_RETRIES = SETTINGS.MAX_ROUTE_RETRIES   # 3


SYSTEM_PROMPT = """You are the **Leader Reviewer** for an agency department.

Your job: Evaluate the specialist's output against your department's quality rubric
and assign a numeric score from 0 to 100.

Scoring criteria (adjust weight per department):
1. **Completeness** (30%) — Does the output cover all required sections?
2. **Accuracy & Relevance** (30%) — Is the content accurate and relevant to the task?
3. **Actionability** (25%) — Can the team act on this output without extensive rework?
4. **Professional Quality** (15%) — Is it well-structured, clearly written, free of errors?

For each criterion, score 0-100 and compute a weighted total.
Then decide:
- Score >= 98: PASS — output is ready for the client/stakeholder
- Score < 98: FAIL — provide specific, actionable feedback on what must be improved

Return a JSON object:
{
  "score": <float 0-100>,
  "breakdown": {
    "completeness": <float>,
    "accuracy": <float>,
    "actionability": <float>,
    "professional_quality": <float>
  },
  "decision": "PASS" | "FAIL",
  "feedback": "<specific bullet-point feedback if FAIL, empty string if PASS>"
}

Be honest. A score of 98/100 is genuinely excellent — do not inflate scores.
The agency standard is 98% minimum quality."""


def _get_department_rubric(to_department: str) -> str:
    """Return department-specific scoring rubric adjustments."""
    rubrics = {
        "strategy": "Focus extra on strategic coherence, competitive positioning, and testability of hypotheses.",
        "creative": "Focus extra on copy quality, brand voice alignment, and visual concept clarity.",
        "media": "Focus extra on channel rationale, budget allocation logic, and metric measurability.",
        "data": "Focus extra on data accuracy, attribution logic, and insight actionability.",
        "account": "Focus extra on client-facing clarity, accuracy of scope, and risk identification.",
        "tech": "Focus extra on technical feasibility, security considerations, and QA completeness.",
        "sales": "Focus extra on lead quality, pitch persuasiveness, and forecast realism.",
        "operations": "Focus extra on resource realism, risk mitigation, and process clarity.",
        "finance": "Focus extra on margin accuracy, compliance, and financial risk.",
        "crm_automation": "Focus extra on automation logic, segment accuracy, and retention metrics.",
        "production": "Focus extra on spec completeness, delivery timeline, and file compliance.",
    }
    return rubrics.get(to_department, "")


def review_output(state: AgenticState) -> AgenticState:
    """
    Leader reviewer node — scores specialist output.
    Updates state with leader_score, leader_feedback, and next_action.
    """
    task_desc = state.get("task_description", "")
    to_dept = state.get("to_department", "")
    specialist_output = state.get("specialist_output", "")
    policy = state.get("policy", {})
    expected_outputs = policy.get("expected_outputs", [])
    retry_count = state.get("retry_count", 0)

    if not specialist_output:
        logger.warning("Leader review: no specialist output to review")
        return {
            **state,
            "leader_score": 0.0,
            "leader_feedback": "No specialist output available to review.",
            "status": "REVIEW_FAILED",
            "next_action": "escalate",
        }

    dept_rubric = _get_department_rubric(to_dept)

    user_prompt = f"""## TASK
{task_desc}

## DEPARTMENT
{to_dept}

## SPECIALIST OUTPUT (to evaluate)
{specialist_output[:6000]}  <!-- truncate to avoid token limits -->

## EXPECTED OUTPUTS
{', '.join(expected_outputs)}

{f"## DEPARTMENT RUBRIC NOTE\n{dept_rubric}" if dept_rubric else ""}

## YOUR SCORING

Evaluate the specialist output using the 4-criterion rubric.
Return ONLY a JSON object (no markdown, no explanation).
"""

    try:
        llm = get_llm()
        raw_response = llm.complete(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=1024,
        )

        import json, re
        match = re.search(r"\{[\s\S]+?\}", raw_response)
        if not match:
            raise ValueError("No JSON in leader review response")

        result: dict[str, Any] = json.loads(match.group())

        score: float = float(result.get("score", 0))
        decision: str = result.get("decision", "FAIL")
        feedback: str = result.get("feedback", "")

        logger.info(
            f"Leader review [{to_dept}]: score={score:.1f}  decision={decision}"
        )

        # Determine next action
        if decision == "PASS" or score >= SCORE_THRESHOLD:
            next_action: str = "passed"
            status = "PASSED"
        elif retry_count >= MAX_RETRIES:
            logger.warning(
                f"Max retries ({MAX_RETRIES}) exceeded for task — escalating to human"
            )
            next_action = "escalate"
            status = "FAILED"
        else:
            next_action = "failed"
            status = "REVIEW_FAILED"

        return {
            **state,
            "leader_score": score,
            "leader_feedback": feedback,
            "status": status,
            "next_action": next_action,
            "retry_count": retry_count + (1 if next_action == "failed" else 0),
        }

    except Exception as exc:
        logger.exception(f"Leader review node failed: {exc}")
        return {
            **state,
            "leader_score": 0.0,
            "leader_feedback": f"Review error: {exc}",
            "status": "REVIEW_FAILED",
            "next_action": "escalate",
            "errors": [*state.get("errors", []), f"Leader review error: {exc}"],
        }
