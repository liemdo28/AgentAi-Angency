"""
SLA Tracker — monitors SLA deadlines and returns breach notifications.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.tasks.models import Task
from src.db.repositories.task_repo import TaskRepository

logger = logging.getLogger(__name__)


@dataclass
class SLAViolation:
    task_id: str
    deadline: str
    overdue_hours: float
    violation_type: str       # "sla_breach" | "hard_deadline"
    department: str
    recommended_action: str    # "extend_sla" | "escalate" | "reassign"


class SLATracker:
    """Check SLA deadlines and detect violations."""

    def __init__(self, task_repo: Optional[TaskRepository] = None) -> None:
        self._repo = task_repo or TaskRepository()

    def check_all_sla(self) -> list[SLAViolation]:
        """Scan all active tasks and return any SLA violations."""
        overdue_tasks = self._repo.get_overdue()
        violations = []
        for task in overdue_tasks:
            violation = self._check_task_sla(task)
            if violation:
                violations.append(violation)
        if violations:
            logger.warning("SLATracker: %d violations found", len(violations))
        return violations

    def check_task(self, task_id: str) -> Optional[SLAViolation]:
        """Check SLA for a single task."""
        task = self._repo.get(task_id)
        if not task:
            return None
        return self._check_task_sla(task)

    def _check_task_sla(self, task: Task) -> Optional[SLAViolation]:
        if not task.sla_deadline:
            return None

        deadline = task.sla_deadline
        # Parse ISO format
        try:
            if deadline.endswith("Z"):
                deadline = deadline[:-1] + "+00:00"
            deadline_dt = datetime.fromisoformat(deadline)
        except ValueError:
            logger.warning("SLATracker: invalid deadline format '%s' for task %s", deadline, task.id)
            return None

        now = datetime.now(timezone.utc)
        if deadline_dt.tzinfo is None:
            deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
        if now <= deadline_dt:
            return None

        overdue_hours = (now - deadline_dt).total_seconds() / 3600

        action = "escalate"
        if overdue_hours < 2:
            action = "extend_sla"
        elif overdue_hours < 8:
            action = "reassign"

        return SLAViolation(
            task_id=task.id,
            deadline=task.sla_deadline,
            overdue_hours=round(overdue_hours, 1),
            violation_type="sla_breach",
            department=task.current_department,
            recommended_action=action,
        )

    def extend_sla(self, task_id: str, hours: int = 24) -> None:
        """Extend a task's SLA deadline by the given hours."""
        task = self._repo.get(task_id)
        if not task or not task.sla_deadline:
            return
        from datetime import timedelta
        current = task.sla_deadline
        try:
            if current.endswith("Z"):
                current = current[:-1] + "+00:00"
            dt = datetime.fromisoformat(current)
        except ValueError:
            dt = datetime.now(timezone.utc)
        new_deadline = (dt + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        task.sla_deadline = new_deadline
        self._repo.update(task)
        self._repo.add_audit_log(
            actor="system",
            action_type="sla_extended",
            entity_type="task",
            entity_id=task_id,
            details={"hours": hours, "new_deadline": new_deadline},
        )
        logger.info("SLATracker: extended SLA for task %s by %d hours", task_id, hours)
