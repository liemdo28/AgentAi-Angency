from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import uuid4

from models import HandoffInstance, HandoffPolicy, HandoffState


class WorkflowEngine:
    def __init__(self, policies: tuple[HandoffPolicy, ...], handoffs: list[HandoffInstance] | None = None):
        self._policies = policies
        self._policy_map: dict[tuple[str, str], HandoffPolicy] = {
            (p.from_department, p.to_department): p for p in policies
        }
        self._handoffs: list[HandoffInstance] = handoffs or []

    def initiate_handoff(self, from_department: str, to_department: str, payload: dict[str, str]) -> HandoffInstance:
        policy = self._policy_map.get((from_department, to_department))
        if not policy:
            raise ValueError(f"Unknown handoff route: {from_department}->{to_department}")

        missing = [key for key in policy.required_inputs if key not in payload]
        if missing:
            raise ValueError(f"Missing required input(s): {', '.join(missing)}")

        now = datetime.now(timezone.utc)
        handoff = HandoffInstance(
            id=str(uuid4()),
            from_department=from_department,
            to_department=to_department,
            input_payload=payload,
            created_at=now,
            updated_at=now,
        )
        self._handoffs.append(handoff)
        return handoff

    def get_handoff(self, handoff_id: str) -> HandoffInstance:
        for handoff in self._handoffs:
            if handoff.id == handoff_id:
                return handoff
        raise KeyError(f"Handoff not found: {handoff_id}")

    def approve(self, handoff_id: str, notes: str = "") -> HandoffInstance:
        handoff = self.get_handoff(handoff_id)
        handoff.state = HandoffState.APPROVED
        handoff.notes = notes
        handoff.updated_at = datetime.now(timezone.utc)
        return handoff

    def block(self, handoff_id: str, notes: str = "") -> HandoffInstance:
        handoff = self.get_handoff(handoff_id)
        handoff.state = HandoffState.BLOCKED
        handoff.notes = notes
        handoff.updated_at = datetime.now(timezone.utc)
        return handoff

    def refresh_overdue(self) -> int:
        now = datetime.now(timezone.utc)
        changed = 0
        for handoff in self._handoffs:
            policy = self._policy_map[(handoff.from_department, handoff.to_department)]
            if handoff.is_overdue(policy.sla_hours, now=now):
                handoff.state = HandoffState.OVERDUE
                handoff.updated_at = now
                changed += 1
        return changed

    def list_handoffs(self) -> list[HandoffInstance]:
        return list(self._handoffs)

    def list_by_state(self, state: HandoffState) -> list[HandoffInstance]:
        return [h for h in self._handoffs if h.state == state]

    def status_dashboard(self) -> dict[str, int]:
        total = len(self._handoffs)
        return {
            "total": total,
            HandoffState.DRAFT.value: len(self.list_by_state(HandoffState.DRAFT)),
            HandoffState.APPROVED.value: len(self.list_by_state(HandoffState.APPROVED)),
            HandoffState.BLOCKED.value: len(self.list_by_state(HandoffState.BLOCKED)),
            HandoffState.OVERDUE.value: len(self.list_by_state(HandoffState.OVERDUE)),
        }

    def list_routes(self) -> list[dict[str, str | int]]:
        return [
            {
                "from_department": p.from_department,
                "to_department": p.to_department,
                "sla_hours": p.sla_hours,
                "approver_role": p.approver_role,
            }
            for p in self._policies
        ]

    def export_handoffs(self) -> list[dict]:
        exported = []
        for handoff in self._handoffs:
            data = asdict(handoff)
            data["state"] = handoff.state.value
            data["created_at"] = handoff.created_at.isoformat()
            data["updated_at"] = handoff.updated_at.isoformat()
            exported.append(data)
        return exported
