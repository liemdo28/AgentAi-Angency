from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ai.models import Task, TaskStatus
from models import HandoffInstance, HandoffState


class JsonStore:
    def __init__(self, path: str = "agency_state.json", task_path: str = "agency_tasks.json"):
        self.path = Path(path)
        self.task_path = Path(task_path)

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

    def save_tasks(self, tasks: list[Task]) -> None:
        data = []
        for task in tasks:
            data.append(
                {
                    "id": task.id,
                    "goal": task.goal,
                    "kpi": task.kpi,
                    "deadline": task.deadline,
                    "department": task.department,
                    "context": task.context,
                    "status": task.status.value,
                    "score": task.score,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat(),
                }
            )
        self.task_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_tasks(self) -> list[Task]:
        if not self.task_path.exists():
            return []

        raw = json.loads(self.task_path.read_text(encoding="utf-8"))
        tasks: list[Task] = []
        for item in raw:
            tasks.append(
                Task(
                    id=item["id"],
                    goal=item["goal"],
                    kpi=item["kpi"],
                    deadline=item["deadline"],
                    department=item["department"],
                    context=item.get("context", {}),
                    status=TaskStatus(item["status"]),
                    score=float(item.get("score", 0.0)),
                    created_at=datetime.fromisoformat(item["created_at"]),
                    updated_at=datetime.fromisoformat(item["updated_at"]),
                )
            )
        return tasks
