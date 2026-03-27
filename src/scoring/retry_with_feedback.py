"""
Retry With Feedback — auto-retry specialist tasks with structured feedback injection.
Respects MAX_RETRIES=3 and MIN_ACCEPTABLE_SCORE=60.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.tasks.models import Task, TaskStatus
from src.db.repositories.task_repo import TaskRepository
from src.scoring.score_engine import ScoreEngine
from src.scoring.rubric_registry import RubricRegistry

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
MIN_ACCEPTABLE_SCORE = 60.0


@dataclass
class RetryDecision:
    should_retry: bool
    reason: str
    feedback: str
    attempt: int
    new_score: float
    final_decision: str  # "retry" | "escalate" | "accept"


class RetryWithFeedback:
    """
    Determines when to retry a failed task with structured feedback.

    Flow:
        1. score(output) -> score
        2. if score >= 98: ACCEPT
        3. if score < 60: ESCALATE (too low to be salvageable)
        4. if retries >= 3: ESCALATE (max attempts exhausted)
        5. else: RETRY with specific feedback

    Usage:
        retry_engine = RetryWithFeedback()
        decision = retry_engine.decide(task, department, output, score)
        if decision.should_retry:
            updated_output = specialist.retry_with_feedback(decision.feedback)
    """

    def __init__(
        self,
        task_repo: Optional[TaskRepository] = None,
        score_engine: Optional[ScoreEngine] = None,
    ) -> None:
        self._repo = task_repo or TaskRepository()
        self._engine = score_engine or ScoreEngine()

    def decide(
        self,
        task: Task,
        department: str,
        output: str,
        existing_score: float = 0.0,
    ) -> RetryDecision:
        """
        Decide whether to retry, escalate, or accept based on score and retry count.
        """
        attempt = task.retry_count + 1
        score = existing_score

        # Re-score if output is provided and score hasn't been computed yet
        if existing_score == 0.0 and output:
            result = self._engine.score(department, output, task.task_type)
            score = result.get("overall_score", 0.0)

        threshold = RubricRegistry().quality_threshold(department)
        min_score = RubricRegistry().min_acceptable(department)

        # Decision tree
        if score >= threshold:
            return RetryDecision(
                should_retry=False,
                reason=f"Score {score:.1f} >= threshold {threshold:.1f}",
                feedback="",
                attempt=attempt,
                new_score=score,
                final_decision="accept",
            )

        if score < MIN_ACCEPTABLE_SCORE:
            return RetryDecision(
                should_retry=False,
                reason=f"Score {score:.1f} below minimum {MIN_ACCEPTABLE_SCORE}",
                feedback="",
                attempt=attempt,
                new_score=score,
                final_decision="escalate",
            )

        if attempt > MAX_RETRIES:
            return RetryDecision(
                should_retry=False,
                reason=f"Max retries ({MAX_RETRIES}) exhausted",
                feedback="",
                attempt=attempt,
                new_score=score,
                final_decision="escalate",
            )

        # Generate feedback
        feedback = self._build_feedback(department, output, score, attempt)
        return RetryDecision(
            should_retry=True,
            reason=f"Score {score:.1f} < {threshold:.1f}, retry {attempt}/{MAX_RETRIES}",
            feedback=feedback,
            attempt=attempt,
            new_score=score,
            final_decision="retry",
        )

    def execute_retry(
        self,
        task: Task,
        department: str,
        specialist_fn: Callable[[str], str],
        output: str,
        score: float,
    ) -> tuple[str, float, RetryDecision]:
        """
        Full retry loop: decide -> inject feedback -> re-run specialist -> re-score.

        Includes score regression detection: if retry scores worse or equal,
        stop immediately and escalate (wasting LLM calls on declining quality).

        Returns: (new_output, new_score, decision)

        Raises: RuntimeError if specialist_fn fails after all retries.
        """
        decision = self.decide(task, department, output, score)

        if not decision.should_retry:
            logger.info(
                "Task %s: %s (score=%.1f, attempt=%d)",
                task.id,
                decision.final_decision,
                decision.new_score,
                decision.attempt,
            )
            return output, decision.new_score, decision

        # Inject feedback into specialist prompt
        retry_prompt = (
            f"PREVIOUS ATTEMPT SCORE: {decision.new_score:.1f}/100\n"
            f"FEEDBACK TO ADDRESS:\n{decision.feedback}\n\n"
            f"Re-do the following task, specifically addressing the feedback above:\n\n"
            f"TASK: {task.description or task.goal}"
        )

        try:
            new_output = specialist_fn(retry_prompt)
        except Exception as exc:
            logger.error("Specialist retry failed for task %s: %s", task.id, exc)
            raise RuntimeError(f"Specialist retry failed: {exc}") from exc

        # Re-score
        result = self._engine.score(department, new_output, task.task_type)
        new_score = result.get("overall_score", 0.0)

        # ── Score regression detection ────────────────────────────────
        # If retry didn't improve, stop wasting LLM calls
        if new_score <= score:
            logger.warning(
                "Task %s: score regression (%.1f -> %.1f) at attempt %d — escalating",
                task.id, score, new_score, decision.attempt,
            )
            task.retry_count = decision.attempt
            task.score = max(score, new_score)  # keep the better score
            self._repo.update(task)
            return (
                output if score >= new_score else new_output,
                max(score, new_score),
                RetryDecision(
                    should_retry=False,
                    reason=f"Score regression: {score:.1f} -> {new_score:.1f}, no improvement",
                    feedback="",
                    attempt=decision.attempt,
                    new_score=max(score, new_score),
                    final_decision="escalate",
                ),
            )

        # Update task
        task.retry_count = decision.attempt
        task.score = new_score
        self._repo.update(task)
        threshold = RubricRegistry().quality_threshold(department)
        self._repo.save_review_history(
            task_id=task.id,
            step_name=department,
            score=new_score,
            threshold=threshold,
            decision="PASS" if new_score >= threshold else "FAIL",
            feedback=decision.feedback,
            breakdown={},
            mode="retry_loop",
        )

        # Recurse with improved score
        return self.execute_retry(task, department, specialist_fn, new_output, new_score)

    def _build_feedback(
        self,
        department: str,
        output: str,
        score: float,
        attempt: int,
    ) -> str:
        """
        Build specific, actionable feedback from rubric criteria analysis.
        """
        rubric = RubricRegistry().get(department)
        result = self._engine.score(department, output, task_type="ad_hoc")
        breakdown = result.get("breakdown", {})
        criteria_scores = result.get("criteria_scores", {})

        weakest = sorted(
            [(k, v) for k, v in breakdown.items() if isinstance(v, (int, float))],
            key=lambda x: x[1],
        )

        feedback_parts = [
            f"[Attempt {attempt}/{MAX_RETRIES}] Current score: {score:.1f}/100",
            f"Threshold for acceptance: {rubric.quality_threshold:.1f}/100",
            "",
            "Focus improvements on these weak areas:",
        ]

        for criterion_name, criterion_score in weakest[:2]:  # top 2 weakest
            criterion_obj = next(
                (c for c in rubric.criteria if c.name == criterion_name), None
            )
            if criterion_obj:
                notes = (
                    criteria_scores.get(criterion_name, {})
                    .get("notes", "See rubric checklist")
                )
                feedback_parts.append(f"")
                feedback_parts.append(f"## {criterion_name} ({criterion_score:.0f}/100)")
                feedback_parts.append(f"Issue: {notes}")
                feedback_parts.append("Checklist items to verify:")
                for item in criterion_obj.checklist[:3]:  # top 3 checklist items
                    feedback_parts.append(f"  - {item}")

        feedback_parts.append("")
        feedback_parts.append("Rewrite the output addressing these issues specifically.")
        return "\n".join(feedback_parts)
