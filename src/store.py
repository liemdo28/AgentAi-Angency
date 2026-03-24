from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from models import HandoffInstance, HandoffState


class JsonStore:
    def __init__(self, path: str = "agency_state.json"):
        self.path = Path(path)

    def save(self, handoffs: list[HandoffInstance]) -> None:
        data = []
        for handoff in handoffs:
            data.append(
                {
                    "id": handoff.id,
                    "from_department": handoff.from_department,
                    "to_department": handoff.to_department,
                    "input_payload": handoff.input_payload,
                    "state": handoff.state.value,
                    "notes": handoff.notes,
                    "created_at": handoff.created_at.isoformat(),
                    "updated_at": handoff.updated_at.isoformat(),
                }
            )
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load(self) -> list[HandoffInstance]:
        if not self.path.exists():
            return []

        raw = json.loads(self.path.read_text(encoding="utf-8"))
        handoffs: list[HandoffInstance] = []
        for item in raw:
            handoffs.append(
                HandoffInstance(
                    id=item["id"],
                    from_department=item["from_department"],
                    to_department=item["to_department"],
                    input_payload=item["input_payload"],
                    state=HandoffState(item["state"]),
                    notes=item.get("notes", ""),
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                )
            )
        return handoffs
