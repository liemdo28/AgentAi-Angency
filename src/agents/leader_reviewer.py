"""
Leader Reviewer node — scores specialist output and decides pass/fail/retry.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgenticState
from src.config import SETTINGS
from src.llm import get_llm
from src.utils.json_utils import extract_first_json_object

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = SETTINGS.SCORE_THRESHOLD
MAX_RETRIES = SETTINGS.MAX_ROUTE_RETRIES


SYSTEM_PROMPT = """You are the **Leader Reviewer** for an agency department.

Your job: Evaluate the specialist's output against your department's quality rubric
and assign a numeric score from 0 to 100.

Scoring criteria (adjust weight per department):
1. **Completeness** (30%) — Does the output cover all required sections?
2. **Accuracy & Relevance** (30%) — Is the content accurate and relevant to the task?
3. **Actionability** (25%) — Can the team act on this output without extensive rework?
4. **Professional Quality** (15%) — Is it well-structured, clearly written, free of errors?

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
  "feedback": "<specific feedback if FAIL, empty string if PASS>"
}

Be honest. A score of 98/100 is genuinely excellent. Do not inflate scores.
The agency standard is 98% minimum quality."""


def _get_department_rubric(to_department: str) -> str:
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


def _heuristic_review(
    state: AgenticState,
    *,
    expected_outputs: list[str],
    retry_count: int,
    score_threshold: float,
    to_department: str,
    reason: str,
) -> AgenticState:
    """Fallback scoring when LLM is unavailable — uses structural heuristics."""
    specialist_output = state.get("specialist_output", "")
    specialist_text = specialist_output.lower()
    coverage_hits = 0
    for item in expected_outputs:
        if item.lower() in specialist_text or item.replace("_", " ").lower() in specialist_text:
            coverage_hits += 1

    coverage_ratio = coverage_hits / max(len(expected_outputs), 1)
    line_count = len(specialist_output.splitlines())
    structured_sections = specialist_output.count("## ")

    if coverage_ratio >= 1.0 and structured_sections >= max(len(expected_outputs), 1):
        completeness = 97.0
        accuracy = 96.0
        actionability = 96.0 if line_count >= 6 else 93.0
        professional_quality = 95.0 if line_count >= 6 else 91.0
    else:
        completeness = min(100.0, 55.0 + (coverage_ratio * 45.0))
        actionability = min(100.0, 65.0 + min(len(specialist_output), 3000) / 100.0)
        accuracy = 80.0 if specialist_output.strip() else 0.0
        professional_quality = 78.0 if line_count >= 4 else 60.0

    score = round(
        (completeness * 0.30)
        + (accuracy * 0.30)
        + (actionability * 0.25)
        + (professional_quality * 0.15),
        2,
    )
    decision = "PASS" if score >= score_threshold else "FAIL"
    next_action = "passed" if decision == "PASS" else ("failed" if retry_count < MAX_RETRIES else "escalate")
    status = "PASSED" if decision == "PASS" else ("REVIEW_FAILED" if next_action == "failed" else "FAILED")
    feedback = "" if decision == "PASS" else (
        "Raise coverage for the expected outputs, make the deliverable more concrete, "
        "and address missing sections before retry."
    )

    return {
        **state,
        "leader_score": score,
        "leader_feedback": feedback,
        "quality_threshold": score_threshold,
        "quality_breakdown": {
            "completeness": completeness,
            "accuracy": accuracy,
            "actionability": actionability,
            "professional_quality": professional_quality,
        },
        "review_history": [
            *state.get("review_history", []),
            {
                "step": state.get("current_step", {}).get("name", to_department),
                "score": score,
                "threshold": score_threshold,
                "decision": decision,
                "retry_count": retry_count,
                "mode": "heuristic",
            },
        ],
        "status": status,
        "next_action": next_action,
        "retry_count": retry_count + (1 if next_action == "failed" else 0),
        "errors": [*state.get("errors", []), f"Heuristic review reason: {reason}"],
    }


def review_output(state: AgenticState) -> AgenticState:
    """Score specialist output and set the next routing action."""
    task_desc = state.get("task_description", "")
    to_department = state.get("to_department", "")
    specialist_output = state.get("specialist_output", "")
    policy = state.get("policy", {})
    expected_outputs = list(policy.get("expected_outputs", []))
    retry_count = state.get("retry_count", 0)
    score_threshold = float(
        state.get("quality_threshold")
        or state.get("current_step", {}).get("quality_threshold", SCORE_THRESHOLD)
    )

    if not specialist_output:
        logger.warning("Leader review: no specialist output to review")
        return {
            **state,
            "leader_score": 0.0,
            "leader_feedback": "No specialist output available to review.",
            "quality_threshold": score_threshold,
            "status": "REVIEW_FAILED",
            "next_action": "escalate",
        }

    dept_rubric = _get_department_rubric(to_department)
    rubric_block = f"## DEPARTMENT RUBRIC NOTE\n{dept_rubric}" if dept_rubric else ""
    user_prompt = f"""## TASK
{task_desc}

## DEPARTMENT
{to_department}

## SPECIALIST OUTPUT
{specialist_output[:6000]}

## EXPECTED OUTPUTS
{', '.join(expected_outputs)}

## QUALITY THRESHOLD
{score_threshold}

{rubric_block}

Evaluate the specialist output using the rubric and return ONLY JSON.
"""

    try:
        llm = get_llm()
        if llm.primary_provider is None:
            raise RuntimeError("No configured LLM provider for review")

        raw_response = llm.complete(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=1024,
        )
        result: dict[str, Any] = extract_first_json_object(raw_response)

        score = float(result.get("score", 0))
        breakdown = {
            key: float(value)
            for key, value in dict(result.get("breakdown", {})).items()
            if isinstance(value, (int, float))
        }
        decision = str(result.get("decision", "FAIL")).upper()
        feedback = str(result.get("feedback", ""))

        logger.info("Leader review [%s]: score=%.1f decision=%s", to_department, score, decision)

        if decision == "PASS" or score >= score_threshold:
            next_action = "passed"
            status = "PASSED"
        elif retry_count >= MAX_RETRIES:
            logger.warning("Max retries (%s) exceeded - escalating to human", MAX_RETRIES)
            next_action = "escalate"
            status = "FAILED"
        else:
            next_action = "failed"
            status = "REVIEW_FAILED"

        return {
            **state,
            "leader_score": score,
            "leader_feedback": feedback,
            "quality_threshold": score_threshold,
            "quality_breakdown": breakdown,
            "review_history": [
                *state.get("review_history", []),
                {
                    "step": state.get("current_step", {}).get("name", to_department),
                    "score": score,
                    "threshold": score_threshold,
                    "decision": decision,
                    "retry_count": retry_count,
                },
            ],
            "status": status,
            "next_action": next_action,
            "retry_count": retry_count + (1 if next_action == "failed" else 0),
        }

    except Exception as exc:
        logger.warning("Leader review LLM failed, using heuristic review: %s", exc)
        return _heuristic_review(
            state,
            expected_outputs=expected_outputs,
            retry_count=retry_count,
            score_threshold=score_threshold,
            to_department=to_department,
            reason=str(exc),
        )
