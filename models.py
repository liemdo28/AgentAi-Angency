from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4


# ------------------------------------------------------------------ #
# Domain Models                                                        #
# ------------------------------------------------------------------ #

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

    def __post_init__(self) -> None:
        if not self.from_department.strip():
            raise ValueError("from_department must not be empty")
        if not self.to_department.strip():
            raise ValueError("to_department must not be empty")
        if self.from_department == self.to_department:
            raise ValueError(
                f"from_department and to_department must differ: '{self.from_department}'"
            )
        if self.sla_hours <= 0:
            raise ValueError(f"sla_hours must be positive, got {self.sla_hours}")
        if not self.required_inputs:
            raise ValueError(
                f"required_inputs must not be empty for {self.from_department}->{self.to_department}"
            )
        if not self.expected_outputs:
            raise ValueError(
                f"expected_outputs must not be empty for {self.from_department}->{self.to_department}"
            )


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
        if self.state == HandoffState.APPROVED:
            return False
        deadline = self.created_at + timedelta(hours=self.policy.sla_hours)
        return (now or datetime.utcnow()) > deadline


# ------------------------------------------------------------------ #
# Client / Project (SaaS layer)                                        #
# ------------------------------------------------------------------ #

@dataclass
class Client:
    id: str
    name: str
    industry: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Project:
    id: str
    client_id: str
    name: str
    objective: str
    owner: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ------------------------------------------------------------------ #
# Custom Exceptions                                                    #
# ------------------------------------------------------------------ #

class HandoffError(Exception):
    """Base exception for all workflow errors."""


class RouteNotFoundError(HandoffError, KeyError):
    """No policy registered for the requested department route."""


class HandoffNotFoundError(HandoffError, KeyError):
    """No handoff found with the given ID."""


class InvalidStateTransitionError(HandoffError, ValueError):
    """The requested state transition is not allowed."""


class MissingInputsError(HandoffError, ValueError):
    """One or more required inputs are missing for this route."""
