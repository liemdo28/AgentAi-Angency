from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from models import Client, HandoffInstance, HandoffState, Project


class JsonStore:
    def __init__(self, path: str = "agency_state.json"):
        self.path = Path(path)

    def save_all(
        self,
        handoffs: list[HandoffInstance],
        clients: list[Client],
        projects: list[Project],
    ) -> None:
        handoff_data = []
        for handoff in handoffs:
            handoff_data.append(
                {
                    "id": handoff.id,
                    "from_department": handoff.from_department,
                    "to_department": handoff.to_department,
                    "input_payload": handoff.input_payload,
                    "state": handoff.state.value,
                    "notes": handoff.notes,
                    "client_id": handoff.client_id,
                    "project_id": handoff.project_id,
                    "created_at": handoff.created_at.isoformat(),
                    "updated_at": handoff.updated_at.isoformat(),
                }
            )

        client_data = [
            {
                "id": c.id,
                "name": c.name,
                "industry": c.industry,
                "created_at": c.created_at.isoformat(),
            }
            for c in clients
        ]

        project_data = [
            {
                "id": p.id,
                "client_id": p.client_id,
                "name": p.name,
                "objective": p.objective,
                "owner": p.owner,
                "created_at": p.created_at.isoformat(),
            }
            for p in projects
        ]

        payload = {"handoffs": handoff_data, "clients": client_data, "projects": project_data}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_all(self) -> tuple[list[HandoffInstance], list[Client], list[Project]]:
        if not self.path.exists():
            return [], [], []

        raw = json.loads(self.path.read_text(encoding="utf-8"))

        handoffs: list[HandoffInstance] = []
        for item in raw.get("handoffs", []):
            handoffs.append(
                HandoffInstance(
                    id=item["id"],
                    from_department=item["from_department"],
                    to_department=item["to_department"],
                    input_payload=item["input_payload"],
                    state=HandoffState(item["state"]),
                    notes=item.get("notes", ""),
                    client_id=item.get("client_id"),
                    project_id=item.get("project_id"),
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                )
            )

        clients = [
            Client(
                id=item["id"],
                name=item["name"],
                industry=item["industry"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in raw.get("clients", [])
        ]

        projects = [
            Project(
                id=item["id"],
                client_id=item["client_id"],
                name=item["name"],
                objective=item["objective"],
                owner=item["owner"],
                created_at=datetime.fromisoformat(item["created_at"]),
            )
            for item in raw.get("projects", [])
        ]

        return handoffs, clients, projects
