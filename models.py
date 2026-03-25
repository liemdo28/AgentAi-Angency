from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


@dataclass(frozen=True)
class Employee:
    id: str
    full_name: str
    role: str
    department: str
    responsibilities: tuple[str, ...]


@dataclass(frozen=True)
class Leader(Employee):
    approval_scope: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HandoffPolicy:
    from_department: str
    to_department: str
    required_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    sla_hours: int
    approver_role: str


class HandoffState(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    BLOCKED = "blocked"
    OVERDUE = "overdue"


@dataclass
class HandoffInstance:
    id: str
    from_department: str
    to_department: str
    input_payload: dict[str, str]
    state: HandoffState = HandoffState.DRAFT
    notes: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_overdue(self, sla_hours: int, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.state in {HandoffState.DRAFT, HandoffState.BLOCKED} and now > self.created_at + timedelta(hours=sla_hours)
