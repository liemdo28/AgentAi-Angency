"""
CEO Decision Engine — decides what action to take for a given situation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.tasks.models import Task, TaskStatus
from src.db.repositories.task_repo import TaskRepository
from src.tasks.sla_tracker import SLAViolation, SLATracker

logger = logging.getLogger(__name__)

MIN_ACCEPTABLE_SCORE = 60.0
MAX_RETRIES = 3


@dataclass
class CEODecision:
    decision_type: str    # "retry" | "escalate" | "sla_extend" | "monitor" | "done"
    task_id: str
    reason: str
    recommended_action: str
    details: dict


class CEODecisionEngine:
    """Determines the right CEO action based on task state."""

    def __init__(self, task_repo: Optional[TaskRepository] = None) -> None:
        self._repo = task_repo or TaskRepository()

    def monitor_decisions(
        self,
        active_tasks: list[Task],
        sla_violations: list[SLAViolation],
        health_scores: dict[str, float],
    ) -> list[CEODecision]:
        """Generate a list of decisions for the monitoring loop."""
        decisions = []

        # SLA violations → intervene
        for v in sla_violations:
            decisions.append(CEODecision(
                decision_type="sla_breach",
                task_id=v.task_id,
                reason=f"SLA breached by {v.overdue_hours:.1f}h",
                recommended_action=v.recommended_action,
                details={"violation_type": v.violation_type, "overdue_hours": v.overdue_hours},
            ))

        # Low health campaigns
        for campaign_id, score in health_scores.items():
            if score < 70:
                decisions.append(CEODecision(
                    decision_type="campaign_health_warning",
                    task_id=campaign_id,
                    reason=f"Campaign health score {score:.0f}/100 is below 70",
                    recommended_action="review_and_optimise",
                    details={"health_score": score},
                ))

        return decisions

    def decide_next(self, task: Task) -> CEODecision:
        """Decide what to do with a single task."""
        score = task.score
        threshold = 98.0  # could come from task
        retries = task.retry_count
        status = task.status.value if hasattr(task.status, "value") else task.status

        if status in ("passed", "done"):
            return CEODecision(
                decision_type="done",
                task_id=task.id,
                reason="Task already completed",
                recommended_action="none",
                details={},
            )

        if score >= threshold:
            return CEODecision(
                decision_type="accept",
                task_id=task.id,
                reason=f"Score {score:.0f} >= threshold {threshold}",
                recommended_action="accept_and_advance",
                details={"score": score, "threshold": threshold},
            )

        if score < MIN_ACCEPTABLE_SCORE:
            return CEODecision(
                decision_type="escalate",
                task_id=task.id,
                reason=f"Score {score:.0f} below minimum {MIN_ACCEPTABLE_SCORE}",
                recommended_action="escalate_to_human",
                details={"score": score, "min_score": MIN_ACCEPTABLE_SCORE},
            )

        if retries >= MAX_RETRIES:
            return CEODecision(
                decision_type="escalate",
                task_id=task.id,
                reason=f"Max retries ({MAX_RETRIES}) exhausted",
                recommended_action="escalate_to_human",
                details={"retries": retries, "max_retries": MAX_RETRIES},
            )

        return CEODecision(
            decision_type="retry",
            task_id=task.id,
            reason=f"Score {score:.0f} < {threshold}, retries {retries}/{MAX_RETRIES}",
            recommended_action="retry_with_feedback",
            details={"score": score, "retries": retries},
        )

    def intervene(
        self,
        violation: SLAViolation,
        sla_tracker: SLATracker,
    ) -> CEODecision:
        """Handle an SLA violation."""
        action = violation.recommended_action

        if action == "extend_sla":
            sla_tracker.extend_sla(violation.task_id, hours=24)
            self._repo.add_audit_log(
                actor="ceo",
                action_type="sla_extended",
                entity_type="task",
                entity_id=violation.task_id,
                details={"overdue_hours": violation.overdue_hours, "hours_added": 24},
            )
            return CEODecision(
                decision_type="sla_extended",
                task_id=violation.task_id,
                reason=f"SLA extended by 24h (was {violation.overdue_hours:.1f}h overdue)",
                recommended_action="continue_execution",
                details={"violation": violation.__dict__},
            )

        # escalate or reassign
        task = self._repo.get(violation.task_id)
        if task:
            task.escalation_count += 1
            task.health_flags = [*task.health_flags, f"sla_breach:{violation.overdue_hours:.0f}h"]
            self._repo.update(task)
            self._repo.add_audit_log(
                actor="ceo",
                action_type="escalated",
                entity_type="task",
                entity_id=violation.task_id,
                details={"reason": f"SLA breach {violation.overdue_hours:.1f}h", "action": action},
            )

        return CEODecision(
            decision_type="escalate",
            task_id=violation.task_id,
            reason=f"SLA breach {violation.overdue_hours:.1f}h — {action}",
            recommended_action=action,
            details={"violation": violation.__dict__},
        )
