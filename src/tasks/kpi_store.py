"""
KPI Store — records KPI metrics and computes KPI achievement scores.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from src.db.connection import get_db
from src.tasks.models import Task
from src.db.repositories.task_repo import TaskRepository

logger = logging.getLogger(__name__)


class KPIStore:
    """Track KPI targets vs actuals, compute achievement scores."""

    def __init__(self, task_repo: Optional[TaskRepository] = None) -> None:
        self._repo = task_repo or TaskRepository()

    def record(
        self,
        task_id: str,
        kpi_name: str,
        actual: float,
        target: float,
        unit: str = "%",
    ) -> None:
        """Record a KPI metric for a task."""
        db = get_db()
        db.execute(
            """INSERT INTO kpi_metrics
               (id, task_id, kpi_name, target, actual, unit, recorded_at)
               VALUES (:id, :tid, :name, :target, :actual, :unit, :at)""",
            {
                "id": str(uuid.uuid4()),
                "tid": task_id,
                "name": kpi_name,
                "target": target,
                "actual": actual,
                "unit": unit,
                "at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        db.commit()
        logger.info("KPIStore: recorded %s=%.2f (target=%.2f) for task %s", kpi_name, actual, target, task_id)

    def get_task_kpis(self, task_id: str) -> list[dict]:
        """Fetch all KPI metrics for a task."""
        db = get_db()
        rows = db.execute(
            "SELECT * FROM kpi_metrics WHERE task_id = ? ORDER BY recorded_at",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def compute_kpi_score(self, task_id: str) -> float:
        """
        Compute a 0-100 KPI achievement score for a task.
        Each KPI contributes equally; capped at 150% achievement.
        """
        metrics = self.get_task_kpis(task_id)
        if not metrics:
            return 100.0

        rates = []
        for m in metrics:
            target = float(m["target"])
            actual = float(m["actual"])
            if target != 0:
                rates.append(min(actual / target, 1.5))  # cap at 150%
        if not rates:
            return 100.0
        return round(sum(rates) / len(rates) * 100, 2)

    def kpi_score_from_task(self, task: Task) -> float:
        """Compute KPI score using the task's own kpis/kpi_results dicts."""
        if not task.kpis:
            return 100.0
        rates = []
        for name, target in task.kpis.items():
            actual = task.kpi_results.get(name, 0.0)
            if target != 0:
                rates.append(min(actual / target, 1.5))
        if not rates:
            return 100.0
        return round(sum(rates) / len(rates) * 100, 2)
