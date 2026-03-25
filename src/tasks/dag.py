"""
Task DAG — Directed Acyclic Graph for task dependencies.
Handles topological ordering and ready-task detection.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.tasks.models import Task, TaskStatus
from src.db.repositories.task_repo import TaskRepository

logger = logging.getLogger(__name__)


class TaskDAG:
    """
    Directed Acyclic Graph over tasks based on inter-department policy routes.

    Nodes = Tasks
    Edges  = from_department → to_department (a task "depends on" the previous step)
    """

    def __init__(self, task_repo: Optional[TaskRepository] = None) -> None:
        self._repo = task_repo or TaskRepository()

    def get_ready_tasks(self) -> list[Task]:
        """
        Tasks in DRAFT/PENDING whose dependencies are all PASSED or DONE.
        These are the tasks ready to be executed next.
        """
        all_tasks = self._repo.list_active()
        ready = []
        for task in all_tasks:
            if task.status not in (TaskStatus.DRAFT, TaskStatus.PENDING):
                continue
            deps_done = all(
                self._is_complete(dep_id) for dep_id in task.dependencies
            )
            if deps_done or not task.dependencies:
                ready.append(task)
        logger.info("TaskDAG: %d ready tasks", len(ready))
        return ready

    def get_blocked_tasks(self) -> list[tuple[Task, list[str]]]:
        """Tasks blocked by incomplete dependencies, with reasons."""
        all_tasks = self._repo.list_active()
        blocked = []
        for task in all_tasks:
            if task.status not in (TaskStatus.DRAFT, TaskStatus.PENDING):
                continue
            incomplete = [
                dep_id for dep_id in task.dependencies
                if not self._is_complete(dep_id)
            ]
            if incomplete:
                blocked.append((task, incomplete))
        return blocked

    def topological_sort(self, task_ids: list[str]) -> list[Task]:
        """
        Return tasks in dependency-respecting order (Kahn's algorithm).
        Raises ValueError if a cycle is detected.
        """
        tasks = {t.id: t for t in [self._repo.get(tid) for tid in task_ids] if t}
        if not tasks:
            return []

        in_degree = {tid: 0 for tid in tasks}
        for task in tasks.values():
            for dep in task.dependencies:
                if dep in in_degree:
                    in_degree[task.id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        order = []
        while queue:
            tid = queue.pop(0)
            order.append(tasks[tid])
            for other in tasks.values():
                if tid in other.dependencies and other.id in in_degree:
                    in_degree[other.id] -= 1
                    if in_degree[other.id] == 0:
                        queue.append(other.id)

        if len(order) != len(tasks):
            raise ValueError("Cycle detected in task DAG")
        return order

    def add_dependency(self, task_id: str, depends_on_task_id: str) -> None:
        """Add a dependency edge."""
        task = self._repo.get(task_id)
        if task and depends_on_task_id not in task.dependencies:
            task.dependencies = [*task.dependencies, depends_on_task_id]
            self._repo.update(task)

    def _is_complete(self, task_id: str) -> bool:
        task = self._repo.get(task_id)
        if not task:
            return False
        return task.status in (TaskStatus.PASSED, TaskStatus.DONE, TaskStatus.FAILED)
