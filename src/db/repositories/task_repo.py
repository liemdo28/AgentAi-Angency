"""Task repository — SQLite CRUD for tasks."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.db.connection import get_db, rows_to_dicts
from src.tasks.models import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskRepository:
    """SQLite CRUD for the tasks table."""

    TABLE = "tasks"

    def create(self, task: Task) -> Task:
        """Insert a new task into the database."""
        db = get_db()
        data = task.to_db_dict()

        # Build INSERT with only non-None columns
        cols = [k for k, v in data.items() if v is not None]
        placeholders = ", ".join(f":{c}" for c in cols)
        col_names = ", ".join(cols)

        db.execute(
            f"INSERT INTO {self.TABLE} ({col_names}) VALUES ({placeholders})",
            data,
        )
        db.commit()
        logger.info("TaskRepository: created task %s", task.id)
        return task

    def get(self, task_id: str) -> Optional[Task]:
        """Fetch a single task by ID."""
        db = get_db()
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (task_id,)
        ).fetchall()
        if not rows:
            return None
        return Task.from_db_row(dict(rows[0]))

    def update(self, task: Task) -> Task:
        """Update an existing task."""
        db = get_db()
        data = task.to_db_dict()
        data = {k: v for k, v in data.items() if v is not None}
        setters = ", ".join(f"{k} = :{k}" for k in data)
        db.execute(
            f"UPDATE {self.TABLE} SET {setters} WHERE id = :id",
            data,
        )
        db.commit()
        logger.info("TaskRepository: updated task %s", task.id)
        return task

    def delete(self, task_id: str) -> bool:
        """Delete a task. Returns True if deleted."""
        db = get_db()
        cursor = db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (task_id,))
        db.commit()
        return cursor.rowcount > 0

    def list_active(self) -> list[Task]:
        """Return all non-terminal tasks."""
        db = get_db()
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE status NOT IN "
            f"('passed','done','failed','cancelled') ORDER BY created_at DESC"
        ).fetchall()
        return [Task.from_db_row(dict(r)) for r in rows]

    def list_by_campaign(self, campaign_id: str) -> list[Task]:
        db = get_db()
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE campaign_id = ? ORDER BY step_index",
            (campaign_id,),
        ).fetchall()
        return [Task.from_db_row(dict(r)) for r in rows]

    def list_by_status(self, status: str) -> list[Task]:
        db = get_db()
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE status = ? ORDER BY created_at",
            (status,),
        ).fetchall()
        return [Task.from_db_row(dict(r)) for r in rows]

    def get_overdue(self) -> list[Task]:
        """Tasks whose SLA deadline has passed and are not done."""
        db = get_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} "
            f"WHERE sla_deadline IS NOT NULL "
            f"AND sla_deadline < ? "
            f"AND status NOT IN ('passed','done','failed','cancelled')",
            (now,),
        ).fetchall()
        return [Task.from_db_row(dict(r)) for r in rows]

    def upsert(self, task: Task) -> Task:
        """Insert or replace."""
        db = get_db()
        data = task.to_db_dict()
        cols = [k for k in data]
        placeholders = ", ".join(f":{c}" for c in cols)
        col_names = ", ".join(cols)
        db.execute(
            f"INSERT OR REPLACE INTO {self.TABLE} ({col_names}) VALUES ({placeholders})",
            data,
        )
        db.commit()
        return task

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Quick status update."""
        db = get_db()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        updates = {"status": status.value}
        if status == TaskStatus.IN_PROGRESS:
            updates["started_at"] = now
        elif status in (TaskStatus.PASSED, TaskStatus.DONE):
            updates["completed_at"] = now
        setters = ", ".join(f"{k} = :{k}" for k in updates)
        db.execute(
            f"UPDATE {self.TABLE} SET {setters} WHERE id = :id",
            {"id": task_id, **updates},
        )
        db.commit()

    def save_review_history(
        self,
        task_id: str,
        step_name: str,
        score: float,
        threshold: float,
        decision: str,
        feedback: str,
        breakdown: dict[str, float],
        mode: str = "llm",
        model_version: str = "",
    ) -> None:
        """Append a review record to the review_history table."""
        import uuid
        db = get_db()
        db.execute(
            """INSERT INTO review_history
               (id, task_id, step_name, score, threshold, decision, feedback, breakdown_json, mode, model_version)
               VALUES (:id, :task_id, :step_name, :score, :threshold, :decision,
                       :feedback, :breakdown_json, :mode, :model_version)""",
            {
                "id": str(uuid.uuid4()),
                "task_id": task_id,
                "step_name": step_name,
                "score": score,
                "threshold": threshold,
                "decision": decision,
                "feedback": feedback,
                "breakdown_json": json.dumps(breakdown),
                "mode": mode,
                "model_version": model_version,
            },
        )
        db.commit()

    def add_audit_log(
        self,
        actor: str,
        action_type: str,
        entity_type: str = "",
        entity_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append an audit log entry."""
        import uuid
        db = get_db()
        db.execute(
            """INSERT INTO audit_log
               (id, actor, action_type, entity_type, entity_id, details_json)
               VALUES (:id, :actor, :action_type, :entity_type, :entity_id, :details)""",
            {
                "id": str(uuid.uuid4()),
                "actor": actor,
                "action_type": action_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "details": json.dumps(details or {}),
            },
        )
        db.commit()

    def get_stats(self) -> dict[str, Any]:
        """Return dashboard metrics: counts by status, avg score, pass rate."""
        db = get_db()

        def count_where(where: str) -> int:
            row = db.execute(f"SELECT COUNT(*) as n FROM {self.TABLE} WHERE {where}").fetchone()
            return dict(row)["n"]

        total = count_where("1=1")

        def avg_score_where(where: str) -> float:
            row = db.execute(
                f"SELECT AVG(score) as avg FROM {self.TABLE} WHERE score IS NOT NULL AND {where}"
            ).fetchone()
            return round(dict(row)["avg"] or 0.0, 1)

        passed = count_where("status IN ('passed','done')")
        failed = count_where("status IN ('failed','cancelled')")
        escalated = count_where("status = 'escalated'")
        active = count_where("status NOT IN ('passed','done','failed','cancelled')")
        review = count_where("status = 'review'")

        avg_score = avg_score_where("status IN ('passed','done')")
        pass_rate = round(passed / total * 100, 1) if total > 0 else 0.0

        return {
            "total": total,
            "active": active,
            "passed": passed,
            "failed": failed,
            "escalated": escalated,
            "review": review,
            "avg_score": avg_score,
            "pass_rate": pass_rate,
        }

    def list_all(self, status: str | None = None, department: str | None = None,
                 search: str | None = None, limit: int = 200) -> list[Task]:
        """List tasks with optional filters."""
        db = get_db()
        conditions = []
        params: list = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if department:
            conditions.append("current_department = ?")
            params.append(department)
        if search:
            conditions.append("(goal LIKE ? OR description LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])
        where = " AND ".join(conditions) if conditions else "1=1"
        rows = db.execute(
            f"SELECT * FROM {self.TABLE} WHERE {where} ORDER BY created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [Task.from_db_row(dict(r)) for r in rows]

    def get_pending_escalations(self) -> list[dict[str, Any]]:
        """Return all audit log entries for escalation actions with 'pending' status."""
        db = get_db()
        rows = db.execute(
            """SELECT * FROM audit_log
               WHERE action_type LIKE 'escalation_%'
               AND details_json LIKE '%pending%'
               ORDER BY timestamp DESC
               LIMIT 100"""
        ).fetchall()
        return [dict(r) for r in rows]
