from __future__ import annotations

from datetime import datetime

from models import HandoffInstance, HandoffPolicy, HandoffState
from policies import POLICIES


class WorkflowEngine:
    def __init__(self, policies: tuple[HandoffPolicy, ...] = POLICIES) -> None:
        self._policies: dict[tuple[str, str], HandoffPolicy] = {
            (p.from_department, p.to_department): p for p in policies
        }
        self._handoffs: dict[str, HandoffInstance] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def initiate(
        self,
        from_department: str,
        to_department: str,
        provided_inputs: tuple[str, ...],
    ) -> HandoffInstance:
        """Create a new DRAFT handoff if the route and inputs are valid."""
        policy = self._get_policy(from_department, to_department)
        missing = set(policy.required_inputs) - set(provided_inputs)
        if missing:
            raise ValueError(
                f"Missing required inputs for {from_department}->{to_department}: "
                f"{sorted(missing)}"
            )
        instance = HandoffInstance(policy=policy, provided_inputs=provided_inputs)
        self._handoffs[instance.id] = instance
        return instance

    def approve(self, handoff_id: str) -> HandoffInstance:
        """Transition a DRAFT or OVERDUE handoff to APPROVED."""
        instance = self._get_handoff(handoff_id)
        if instance.state not in (HandoffState.DRAFT, HandoffState.OVERDUE):
            raise ValueError(f"Cannot approve handoff in state '{instance.state}'")
        instance.state = HandoffState.APPROVED
        instance.updated_at = datetime.utcnow()
        return instance

    def block(self, handoff_id: str, reason: str = "") -> HandoffInstance:
        """Transition a DRAFT or OVERDUE handoff to BLOCKED."""
        instance = self._get_handoff(handoff_id)
        if instance.state == HandoffState.APPROVED:
            raise ValueError("Cannot block an already approved handoff")
        instance.state = HandoffState.BLOCKED
        instance.notes = reason
        instance.updated_at = datetime.utcnow()
        return instance

    def refresh_overdue(self, now: datetime | None = None) -> list[HandoffInstance]:
        """Mark DRAFT handoffs past their SLA deadline as OVERDUE. Returns flagged list."""
        now = now or datetime.utcnow()
        flagged = []
        for instance in self._handoffs.values():
            if instance.state == HandoffState.DRAFT and instance.is_overdue(now):
                instance.state = HandoffState.OVERDUE
                instance.updated_at = now
                flagged.append(instance)
        return flagged

    def get_by_state(self, state: HandoffState) -> list[HandoffInstance]:
        """Return all handoffs in a given state."""
        return [h for h in self._handoffs.values() if h.state == state]

    def all_handoffs(self) -> list[HandoffInstance]:
        """Return all handoffs regardless of state."""
        return list(self._handoffs.values())

    def restore(self, handoffs: dict[str, HandoffInstance]) -> None:
        """Load persisted handoffs into the engine (replaces current state)."""
        self._handoffs = dict(handoffs)

    def status(self) -> dict[str, int]:
        """Return count of handoffs per state."""
        counts: dict[str, int] = {s.value: 0 for s in HandoffState}
        for instance in self._handoffs.values():
            counts[instance.state.value] += 1
        return counts

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _get_policy(self, from_dept: str, to_dept: str) -> HandoffPolicy:
        key = (from_dept, to_dept)
        if key not in self._policies:
            raise KeyError(f"No policy defined for route {from_dept}->{to_dept}")
        return self._policies[key]

    def _get_handoff(self, handoff_id: str) -> HandoffInstance:
        if handoff_id not in self._handoffs:
            raise KeyError(f"Handoff '{handoff_id}' not found")
        return self._handoffs[handoff_id]
