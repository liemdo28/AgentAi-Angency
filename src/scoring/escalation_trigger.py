"""
Escalation Trigger — decides when to notify a human and creates escalation records.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.tasks.models import Task, TaskStatus
from src.db.repositories.task_repo import TaskRepository

logger = logging.getLogger(__name__)


@dataclass
class EscalationRecord:
    task_id: str
    reason: str
    score: float
    retry_count: int
    escalation_type: str  # "low_quality" | "max_retries" | "sla_breach" | "kpi_miss" | "client_request"
    assigned_to: Optional[str]  # human email/owner
    status: str  # "pending" | "acknowledged" | "resolved"
    created_at: str
    notes: str = ""


class EscalationTrigger:
    """
    Detect conditions that require human intervention and create escalation records.

    Triggers:
    - Score < 60 after any retry (quality too low for AI)
    - Max retries (3) exhausted
    - SLA breach > 48h overdue
    - KPI miss > 20% below target
    - Client escalation flag (email keyword match)
    """

    ESCALATION_SCORE_THRESHOLD = 60.0
    ESCALATION_SLA_HOURS = 48.0
    ESCALATION_KPI_MISS_PCT = 0.20

    def __init__(self, task_repo: Optional[TaskRepository] = None) -> None:
        self._repo = task_repo or TaskRepository()

    def check_task(self, task: Task) -> Optional[EscalationRecord]:
        """
        Evaluate a task and return an EscalationRecord if escalation is warranted.
        Returns None if no escalation needed.
        """
        # Already escalated
        if task.status == TaskStatus.ESCALATED:
            return None

        # Check score threshold
        if 0 < task.score < self.ESCALATION_SCORE_THRESHOLD:
            return self._create_record(
                task=task,
                reason=f"Score {task.score:.1f} below threshold {self.ESCALATION_SCORE_THRESHOLD}",
                escalation_type="low_quality",
            )

        # Check max retries
        if task.retry_count >= 3:
            return self._create_record(
                task=task,
                reason=f"Max retries exhausted (retry_count={task.retry_count})",
                escalation_type="max_retries",
            )

        # Check SLA breach
        if task.is_sla_breached:
            hours_over = self._estimate_overdue_hours(task)
            if hours_over >= self.ESCALATION_SLA_HOURS:
                return self._create_record(
                    task=task,
                    reason=f"SLA breached by {hours_over:.1f}h (threshold: {self.ESCALATION_SLA_HOURS}h)",
                    escalation_type="sla_breach",
                )

        # Check KPI miss
        if task.kpi_results:
            for metric, actual in task.kpi_results.items():
                target = task.kpis.get(metric, 0)
                if target > 0:
                    miss_pct = (target - actual) / target
                    if miss_pct > self.ESCALATION_KPI_MISS_PCT:
                        return self._create_record(
                            task=task,
                            reason=(
                                f"KPI miss: {metric}={actual} vs target={target} "
                                f"({miss_pct:.0%} below target)"
                            ),
                            escalation_type="kpi_miss",
                        )

        return None

    def check_batch(self, tasks: list[Task]) -> list[EscalationRecord]:
        """Check multiple tasks and return all escalation records."""
        records = []
        for task in tasks:
            record = self.check_task(task)
            if record:
                records.append(record)
                self._persist(record)
        return records

    def trigger(
        self,
        task: Task,
        reason: str,
        escalation_type: str = "client_request",
        assigned_to: Optional[str] = None,
        notes: str = "",
    ) -> EscalationRecord:
        """
        Manually trigger an escalation for a task (e.g., from client email keyword match).
        """
        record = self._create_record(
            task=task,
            reason=reason,
            escalation_type=escalation_type,
            assigned_to=assigned_to,
            notes=notes,
        )
        self._persist(record)
        return record

    # ── Internal ────────────────────────────────────────────────────────

    def _create_record(
        self,
        task: Task,
        reason: str,
        escalation_type: str,
        assigned_to: Optional[str] = None,
        notes: str = "",
    ) -> EscalationRecord:
        return EscalationRecord(
            task_id=task.id,
            reason=reason,
            score=task.score,
            retry_count=task.retry_count,
            escalation_type=escalation_type,
            assigned_to=assigned_to or "",
            status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            notes=notes,
        )

    def _persist(self, record: EscalationRecord) -> None:
        """Write escalation record to audit log and update task status."""
        self._repo.add_audit_log(
            actor="system",
            action_type=f"escalation_{record.escalation_type}",
            entity_type="task",
            entity_id=record.task_id,
            details={
                "reason": record.reason,
                "score": record.score,
                "retry_count": record.retry_count,
                "escalation_type": record.escalation_type,
                "assigned_to": record.assigned_to,
                "status": record.status,
            },
        )
        # Mark task as escalated
        task = self._repo.get(record.task_id)
        if task:
            task.status = TaskStatus.ESCALATED
            task.escalation_count += 1
            task.health_flags = [*task.health_flags, f"escalation:{record.escalation_type}"]
            self._repo.update(task)

        logger.warning(
            "ESCALATION: task=%s type=%s reason=%s",
            record.task_id,
            record.escalation_type,
            record.reason,
        )

    def _estimate_overdue_hours(self, task: Task) -> float:
        """Estimate how many hours overdue a task is."""
        if not task.sla_deadline:
            return 0.0
        try:
            from datetime import datetime as dt
            deadline = dt.fromisoformat(task.sla_deadline)
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = now - deadline
            return delta.total_seconds() / 3600
        except Exception:
            return 0.0

    # ── Escalation Queue ───────────────────────────────────────────────

    def get_pending_escalations(self) -> list[EscalationRecord]:
        """Get all pending escalation records from the audit log."""
        import json

        rows = self._repo.get_pending_escalations()
        records: list[EscalationRecord] = []
        for r in rows:
            details_raw = r.get("details_json", "{}")
            try:
                details = json.loads(details_raw) if isinstance(details_raw, str) else (details_raw or {})
            except Exception:
                details = {}

            records.append(
                EscalationRecord(
                    task_id=r.get("entity_id", ""),
                    reason=details.get("reason", ""),
                    score=float(details.get("score", 0.0) or 0.0),
                    retry_count=int(details.get("retry_count", 0) or 0),
                    escalation_type=r.get("action_type", "").replace("escalation_", ""),
                    assigned_to=details.get("assigned_to", ""),
                    status=details.get("status", "pending"),
                    created_at=r.get("timestamp", ""),
                )
            )
        return records

    def acknowledge(self, task_id: str) -> None:
        """Mark an escalation as acknowledged by human."""
        self._repo.add_audit_log(
            actor="human",
            action_type="escalation_acknowledged",
            entity_type="task",
            entity_id=task_id,
            details={"status": "acknowledged"},
        )
        logger.info("Escalation acknowledged for task %s", task_id)

    def resolve(self, task_id: str, notes: str = "") -> None:
        """Mark an escalation as resolved."""
        self._repo.add_audit_log(
            actor="human",
            action_type="escalation_resolved",
            entity_type="task",
            entity_id=task_id,
            details={"status": "resolved", "resolution_notes": notes},
        )
        task = self._repo.get(task_id)
        if task:
            task.status = TaskStatus.DONE
            self._repo.update(task)
        logger.info("Escalation resolved for task %s", task_id)
