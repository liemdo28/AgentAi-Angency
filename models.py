from __future__ import annotations

from dataclasses import dataclass, field


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
