from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    id: str
    goal: str
    kpi: str
    deadline: str
    department: str
    context: dict[str, str] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    score: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AgentResult:
    department: str
    output: dict[str, str]
    score: float
    feedback: str
