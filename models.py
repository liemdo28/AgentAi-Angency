from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


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
    policy: HandoffPolicy
    provided_inputs: tuple[str, ...]
    state: HandoffState = HandoffState.DRAFT
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""

    def is_overdue(self, now: datetime | None = None) -> bool:
        from datetime import timedelta
        if self.state == HandoffState.APPROVED:
            return False
        deadline = self.created_at + timedelta(hours=self.policy.sla_hours)
        return (now or datetime.utcnow()) > deadline
