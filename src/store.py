"""Simple JSON file store for persisting HandoffInstance state across CLI/API calls."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from models import HandoffInstance, HandoffPolicy, HandoffState

STATE_FILE = Path("agency_state.json")


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def load() -> dict[str, HandoffInstance]:
    if not STATE_FILE.exists():
        return {}
    raw = json.loads(STATE_FILE.read_text())
    return {id_: _deserialize(d) for id_, d in raw.items()}


def save(handoffs: dict[str, HandoffInstance]) -> None:
    data = {id_: _serialize(h) for id_, h in handoffs.items()}
    STATE_FILE.write_text(json.dumps(data, indent=2, default=str))


# ------------------------------------------------------------------ #
# Serialization helpers                                                #
# ------------------------------------------------------------------ #

def _serialize(h: HandoffInstance) -> dict:
    return {
        "id": h.id,
        "state": h.state.value,
        "created_at": h.created_at.isoformat(),
        "updated_at": h.updated_at.isoformat(),
        "notes": h.notes,
        "provided_inputs": list(h.provided_inputs),
        "policy": {
            "from_department": h.policy.from_department,
            "to_department": h.policy.to_department,
            "required_inputs": list(h.policy.required_inputs),
            "expected_outputs": list(h.policy.expected_outputs),
            "sla_hours": h.policy.sla_hours,
            "approver_role": h.policy.approver_role,
        },
    }


def _deserialize(d: dict) -> HandoffInstance:
    policy = HandoffPolicy(
        from_department=d["policy"]["from_department"],
        to_department=d["policy"]["to_department"],
        required_inputs=tuple(d["policy"]["required_inputs"]),
        expected_outputs=tuple(d["policy"]["expected_outputs"]),
        sla_hours=d["policy"]["sla_hours"],
        approver_role=d["policy"]["approver_role"],
    )
    return HandoffInstance(
        policy=policy,
        provided_inputs=tuple(d["provided_inputs"]),
        state=HandoffState(d["state"]),
        id=d["id"],
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
        notes=d["notes"],
    )


def handoff_to_dict(h: HandoffInstance) -> dict:
    """Public helper used by CLI and API to render a handoff."""
    return _serialize(h)
