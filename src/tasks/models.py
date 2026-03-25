"""
Task models — Task dataclass, TaskStatus, Priority, and related enums.
Replaces the implicit task state in the LangGraph with a proper domain model.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    DONE = "done"


class Priority(int, Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


def new_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def default_deadline(hours: int = 24) -> str:
    return (datetime.utcnow() + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Task:
    """Core task model for the agency AI system."""

    id: str = field(default_factory=new_id)
    campaign_id: str = ""
    account_id: str = ""
    goal: str = ""
    description: str = ""
    task_type: str = ""
    status: TaskStatus = TaskStatus.DRAFT
    priority: Priority = Priority.NORMAL

    # KPI tracking
    kpis: dict[str, float] = field(default_factory=dict)
    kpi_results: dict[str, float] = field(default_factory=dict)
    score: float = 0.0

    # Timing
    created_at: str = field(default_factory=now_iso)
    deadline: Optional[str] = None
    sla_deadline: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Ownership
    current_department: str = ""
    assigned_employees: list[str] = field(default_factory=list)

    # DAG
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    step_index: int = 0

    # Meta
    planning_mode: str = "template"
    health_flags: list[str] = field(default_factory=list)
    retry_count: int = 0
    escalation_count: int = 0
    final_output_text: str = ""
    final_output_json: dict[str, Any] = field(default_factory=dict)
    specialist_outputs_json: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    # ── Convenience ────────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self.status in (
            TaskStatus.DRAFT,
            TaskStatus.PENDING,
            TaskStatus.IN_PROGRESS,
            TaskStatus.REVIEW,
        )

    @property
    def is_done(self) -> bool:
        return self.status in (
            TaskStatus.PASSED,
            TaskStatus.DONE,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )

    @property
    def is_sla_breached(self) -> bool:
        if not self.sla_deadline:
            return False
        return datetime.utcnow() > datetime.fromisoformat(self.sla_deadline.replace("Z", "+00:00"))

    def kpi_score(self) -> float:
        if not self.kpis:
            return 100.0
        rates = []
        for name, target in self.kpis.items():
            actual = self.kpi_results.get(name, 0.0)
            if target != 0:
                rates.append(min(actual / target, 1.5))
        if not rates:
            return 100.0
        return round(sum(rates) / len(rates) * 100, 2)

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_db_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "campaign_id": self.campaign_id or None,
            "account_id": self.account_id or None,
            "goal": self.goal,
            "description": self.description,
            "task_type": self.task_type,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "priority": int(self.priority) if isinstance(self.priority, Enum) else self.priority,
            "score": self.score,
            "kpis_json": json.dumps(self.kpis),
            "kpi_results_json": json.dumps(self.kpi_results),
            "deadline": self.deadline,
            "sla_deadline": self.sla_deadline,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "current_department": self.current_department,
            "planning_mode": self.planning_mode,
            "health_flags_json": json.dumps(self.health_flags),
            "retry_count": self.retry_count,
            "escalation_count": self.escalation_count,
            "final_output_text": self.final_output_text,
            "final_output_json": json.dumps(self.final_output_json),
            "specialist_outputs_json": json.dumps(self.specialist_outputs_json),
            "notes": self.notes,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "Task":
        def _parse_json(val: Any, default: Any = None) -> Any:
            if val is None:
                return default
            if isinstance(val, (dict, list)):
                return val
            try:
                return json.loads(val) if isinstance(val, str) else default
            except (json.JSONDecodeError, TypeError):
                return default

        return cls(
            id=str(row.get("id", "")),
            campaign_id=str(row.get("campaign_id") or ""),
            account_id=str(row.get("account_id") or ""),
            goal=str(row.get("goal", "")),
            description=str(row.get("description") or ""),
            task_type=str(row.get("task_type") or ""),
            status=TaskStatus(row.get("status", "draft")),
            priority=Priority(int(row.get("priority", 2))),
            score=float(row.get("score", 0.0)),
            kpis=_parse_json(row.get("kpis_json"), {}),
            kpi_results=_parse_json(row.get("kpi_results_json"), {}),
            deadline=str(row.get("deadline") or ""),
            sla_deadline=str(row.get("sla_deadline") or ""),
            started_at=str(row.get("started_at") or ""),
            completed_at=str(row.get("completed_at") or ""),
            current_department=str(row.get("current_department") or ""),
            planning_mode=str(row.get("planning_mode", "template")),
            health_flags=_parse_json(row.get("health_flags_json"), []),
            retry_count=int(row.get("retry_count", 0)),
            escalation_count=int(row.get("escalation_count", 0)),
            final_output_text=str(row.get("final_output_text") or ""),
            final_output_json=_parse_json(row.get("final_output_json"), {}),
            specialist_outputs_json=_parse_json(row.get("specialist_outputs_json"), {}),
            notes=str(row.get("notes") or ""),
        )
