from __future__ import annotations

import threading
from datetime import datetime, timezone, timezone

from models import (
    HandoffInstance,
    HandoffNotFoundError,
    HandoffPolicy,
    HandoffState,
    InvalidStateTransitionError,
    MissingInputsError,
    RouteNotFoundError,
)
from policies import POLICIES


class WorkflowEngine:
    """Thread-safe runtime engine for inter-department handoff workflows."""

    def __init__(self, policies: tuple[HandoffPolicy, ...] = POLICIES) -> None:
        self._policies: dict[tuple[str, str], HandoffPolicy] = {
            (p.from_department, p.to_department): p for p in policies
        }
        self._handoffs: dict[str, HandoffInstance] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def initiate(
        self,
        from_department: str,
        to_department: str,
        provided_inputs: tuple[str, ...],
    ) -> HandoffInstance:
        """Create a new DRAFT handoff if the route and inputs are valid.

        Raises:
            RouteNotFoundError: Route does not exist in policy registry.
            MissingInputsError: One or more required inputs are absent.
        """
        with self._lock:
            policy = self._get_policy(from_department, to_department)
            missing = set(policy.required_inputs) - set(provided_inputs)
            if missing:
                raise MissingInputsError(
                    f"Missing required inputs for {from_department}->{to_department}: "
                    f"{sorted(missing)}"
                )
            instance = HandoffInstance(policy=policy, provided_inputs=provided_inputs)
            self._handoffs[instance.id] = instance
            return instance

    def approve(self, handoff_id: str) -> HandoffInstance:
        """Transition a DRAFT or OVERDUE handoff to APPROVED.

        Raises:
            HandoffNotFoundError: No handoff with this ID.
            InvalidStateTransitionError: Handoff is not in an approvable state.
        """
        with self._lock:
            instance = self._get_handoff(handoff_id)
            if instance.state not in (HandoffState.DRAFT, HandoffState.OVERDUE):
                raise InvalidStateTransitionError(
                    f"Cannot approve handoff in state '{instance.state.value}'. "
                    f"Only DRAFT and OVERDUE handoffs can be approved."
                )
            instance.state = HandoffState.APPROVED
            instance.updated_at = datetime.now(timezone.utc)
            return instance

    def block(self, handoff_id: str, reason: str = "") -> HandoffInstance:
        """Transition a DRAFT or OVERDUE handoff to BLOCKED.

        Raises:
            HandoffNotFoundError: No handoff with this ID.
            InvalidStateTransitionError: Handoff is APPROVED and cannot be blocked.
        """
        with self._lock:
            instance = self._get_handoff(handoff_id)
            if instance.state == HandoffState.APPROVED:
                raise InvalidStateTransitionError(
                    "Cannot block an already approved handoff."
                )
            if instance.state == HandoffState.BLOCKED:
                raise InvalidStateTransitionError(
                    "Handoff is already blocked."
                )
            instance.state = HandoffState.BLOCKED
            instance.notes = reason
            instance.updated_at = datetime.now(timezone.utc)
            return instance

    def refresh_overdue(self, now: datetime | None = None) -> list[HandoffInstance]:
        """Mark DRAFT handoffs past their SLA deadline as OVERDUE.

        Returns the list of newly flagged handoffs.
        """
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        flagged: list[HandoffInstance] = []
        with self._lock:
            for instance in self._handoffs.values():
                if instance.state == HandoffState.DRAFT and instance.is_overdue(now):
                    instance.state = HandoffState.OVERDUE
                    instance.updated_at = now
                    flagged.append(instance)
        return flagged

    def get_by_state(self, state: HandoffState) -> list[HandoffInstance]:
        """Return all handoffs in a given state."""
        with self._lock:
            return [h for h in self._handoffs.values() if h.state == state]

    def all_handoffs(self) -> list[HandoffInstance]:
        """Return all handoffs regardless of state."""
        with self._lock:
            return list(self._handoffs.values())

    def restore(self, handoffs: dict[str, HandoffInstance]) -> None:
        """Replace the in-memory handoff store with the given mapping.

        Typically called at startup to reload persisted state.
        """
        with self._lock:
            self._handoffs = dict(handoffs)

    def status(self) -> dict[str, int]:
        """Return per-state counts of all handoffs."""
        counts: dict[str, int] = {s.value: 0 for s in HandoffState}
        with self._lock:
            for instance in self._handoffs.values():
                counts[instance.state.value] += 1
        return counts

    def get_handoff(self, handoff_id: str) -> HandoffInstance:
        """Return a single handoff by ID.

        Raises:
            HandoffNotFoundError: No handoff found with this ID.
        """
        with self._lock:
            return self._get_handoff(handoff_id)

    def list_routes(self) -> list[HandoffPolicy]:
        """Return all registered route policies."""
        return list(self._policies.values())

    def export_handoffs(self) -> dict[str, HandoffInstance]:
        """Return a snapshot of the internal handoffs dict for persistence."""
        with self._lock:
            return dict(self._handoffs)

    # ------------------------------------------------------------------ #
    # Private helpers (no locking — callers must hold self._lock)         #
    # ------------------------------------------------------------------ #

    def _get_policy(self, from_dept: str, to_dept: str) -> HandoffPolicy:
        key = (from_dept, to_dept)
        if key not in self._policies:
            raise RouteNotFoundError(
                f"No policy defined for route {from_dept}->{to_dept}"
            )
        return self._policies[key]

    def _get_handoff(self, handoff_id: str) -> HandoffInstance:
        if handoff_id not in self._handoffs:
            raise HandoffNotFoundError(
                f"Handoff '{handoff_id}' not found"
            )
        return self._handoffs[handoff_id]
