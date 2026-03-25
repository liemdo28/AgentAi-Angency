from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ai.department_agents import build_agents
from ai.models import AgentResult, Task, TaskStatus


class AutonomousAgency:
    """Autonomous execution layer: all departments represented by AI agents."""

    def __init__(self, score_threshold: float = 98.0, existing_tasks: list[Task] | None = None):
        self._agents = build_agents()
        self._tasks: dict[str, Task] = {task.id: task for task in (existing_tasks or [])}
        self._history: dict[str, list[AgentResult]] = {task.id: [] for task in (existing_tasks or [])}
        self.score_threshold = score_threshold

    def create_task(self, goal: str, kpi: str, deadline: str, department: str, context: dict[str, str] | None = None) -> Task:
        if department not in self._agents:
            raise ValueError(f"Unknown department: {department}")

        now = datetime.now(timezone.utc)
        task = Task(
            id=str(uuid4()),
            goal=goal,
            kpi=kpi,
            deadline=deadline,
            department=department,
            context=context or {},
            created_at=now,
            updated_at=now,
        )
        self._tasks[task.id] = task
        self._history[task.id] = []
        return task

    def get_task(self, task_id: str) -> Task:
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")
        return self._tasks[task_id]

    def run_task(self, task_id: str, max_iterations: int = 3) -> Task:
        task = self.get_task(task_id)
        task.status = TaskStatus.IN_PROGRESS

        for _ in range(max_iterations):
            result = self._agents[task.department].run(task)
            self._history[task.id].append(result)
            task.score = result.score
            task.updated_at = datetime.now(timezone.utc)
            task.context.update(result.output)

            if result.score >= self.score_threshold:
                task.status = TaskStatus.COMPLETED
                return task

            task.status = TaskStatus.REVIEW

        task.status = TaskStatus.FAILED
        return task

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def task_history(self, task_id: str) -> list[AgentResult]:
        self.get_task(task_id)
        return list(self._history.get(task_id, []))

    def status_dashboard(self) -> dict[str, int]:
        tasks = self.list_tasks()
        return {
            "total": len(tasks),
            TaskStatus.PENDING.value: len([t for t in tasks if t.status == TaskStatus.PENDING]),
            TaskStatus.IN_PROGRESS.value: len([t for t in tasks if t.status == TaskStatus.IN_PROGRESS]),
            TaskStatus.REVIEW.value: len([t for t in tasks if t.status == TaskStatus.REVIEW]),
            TaskStatus.COMPLETED.value: len([t for t in tasks if t.status == TaskStatus.COMPLETED]),
            TaskStatus.FAILED.value: len([t for t in tasks if t.status == TaskStatus.FAILED]),
        }
