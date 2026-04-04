"""
ControlPlaneDB — repository for the orchestrator's own tables.

Uses the same SQLite WAL database as the existing agency, but operates
on the cp_* tables (and goals / cp_approvals).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from db.schema_control_plane import CONTROL_PLANE_SCHEMA

logger = logging.getLogger("db.control_plane")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "agency.db"


class ControlPlaneDB:
    """Thin repository over the control-plane tables."""

    def __init__(self, db_path: str | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._ensure_schema()

    # ── connection helpers ────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _ensure_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = self._conn()
        try:
            conn.executescript(CONTROL_PLANE_SCHEMA)
            conn.commit()
            logger.info("Control plane schema ready (%s)", self.db_path)
        finally:
            conn.close()

    # ── goals ─────────────────────────────────────────────────────────

    def create_goal(self, title: str, description: str = "", owner: str = "") -> dict:
        gid = str(uuid4())
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO goals (id, title, description, owner) VALUES (?, ?, ?, ?)",
                (gid, title, description, owner),
            )
            conn.commit()
            return {"id": gid, "title": title}
        finally:
            conn.close()

    def list_goals(self) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM goals ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── agents ────────────────────────────────────────────────────────

    def register_agent(self, agent_id: str, role: str, agent_type: str,
                       model: str = "", budget_limit: float = 50.0) -> dict:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO cp_agents
                   (id, role, agent_type, model, budget_limit)
                   VALUES (?, ?, ?, ?, ?)""",
                (agent_id, role, agent_type, model, budget_limit),
            )
            conn.commit()
            return {"id": agent_id, "role": role}
        finally:
            conn.close()

    def list_agents(self) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM cp_agents ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_agent(self, agent_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cp_agents WHERE id = ?", (agent_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    # ── tasks ─────────────────────────────────────────────────────────

    def create_task(self, title: str, assigned_agent_id: str,
                    goal_id: str = "", description: str = "",
                    task_type: str = "default", priority: int = 2,
                    context_json: dict | None = None) -> dict:
        tid = str(uuid4())
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO cp_tasks
                   (id, goal_id, assigned_agent_id, title, description,
                    task_type, priority, context_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (tid, goal_id, assigned_agent_id, title, description,
                 task_type, priority, json.dumps(context_json or {})),
            )
            conn.commit()
            return {"id": tid, "title": title, "status": "pending"}
        finally:
            conn.close()

    def get_pending_tasks(self) -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM cp_tasks WHERE status = 'pending' ORDER BY priority DESC, created_at ASC"
            ).fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["context_json"] = json.loads(d.get("context_json") or "{}")
                results.append(d)
            return results
        finally:
            conn.close()

    def list_tasks(self, status: str | None = None, limit: int = 100) -> List[dict]:
        conn = self._conn()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM cp_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_tasks ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_task(self, task_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM cp_tasks WHERE id = ?", (task_id,)).fetchone()
            if row:
                d = dict(row)
                d["context_json"] = json.loads(d.get("context_json") or "{}")
                return d
            return None
        finally:
            conn.close()

    def update_task_status(self, task_id: str, status: str) -> None:
        conn = self._conn()
        try:
            now = datetime.now(timezone.utc).isoformat()
            extras = ""
            if status == "running":
                extras = ", started_at = ?"
            elif status in ("success", "failed", "cancelled"):
                extras = ", completed_at = ?"

            if extras:
                conn.execute(
                    f"UPDATE cp_tasks SET status = ?, updated_at = ?{extras} WHERE id = ?",
                    (status, now, now, task_id) if extras else (status, now, task_id),
                )
            else:
                conn.execute(
                    "UPDATE cp_tasks SET status = ? WHERE id = ?",
                    (status, task_id),
                )
            conn.commit()
        finally:
            conn.close()

    def retry_task(self, task_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "UPDATE cp_tasks SET status = 'pending', retry_count = retry_count + 1 WHERE id = ?",
                (task_id,),
            )
            conn.commit()
        finally:
            conn.close()

    # ── jobs ──────────────────────────────────────────────────────────

    def save_job(self, task_id: str, agent_id: str,
                 input_data: dict, output_data: dict,
                 started_at: str = "", cost: float = 0.0) -> dict:
        jid = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO cp_jobs
                   (id, task_id, agent_id, input_json, output_json,
                    cost, status, started_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'success', ?, ?)""",
                (jid, task_id, agent_id,
                 json.dumps(input_data), json.dumps(output_data),
                 cost, started_at or now, now),
            )
            conn.commit()
            return {"id": jid, "task_id": task_id}
        finally:
            conn.close()

    def list_jobs(self, task_id: str | None = None, limit: int = 50) -> List[dict]:
        conn = self._conn()
        try:
            if task_id:
                rows = conn.execute(
                    "SELECT * FROM cp_jobs WHERE task_id = ? ORDER BY started_at DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM cp_jobs ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── approvals ─────────────────────────────────────────────────────

    def request_approval(self, task_id: str, requested_by: str = "system") -> dict:
        aid = str(uuid4())
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO cp_approvals (id, task_id, requested_by) VALUES (?, ?, ?)",
                (aid, task_id, requested_by),
            )
            conn.commit()
            return {"id": aid, "task_id": task_id, "status": "pending"}
        finally:
            conn.close()

    def resolve_approval(self, approval_id: str, status: str,
                         approved_by: str = "", reason: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._conn()
        try:
            conn.execute(
                """UPDATE cp_approvals
                   SET status = ?, approved_by = ?, reason = ?, resolved_at = ?
                   WHERE id = ?""",
                (status, approved_by, reason, now, approval_id),
            )
            # Also update the task's approval_status
            row = conn.execute(
                "SELECT task_id FROM cp_approvals WHERE id = ?", (approval_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE cp_tasks SET approval_status = ? WHERE id = ?",
                    (status, row["task_id"]),
                )
            conn.commit()
        finally:
            conn.close()

    def list_approvals(self, status: str = "pending") -> List[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM cp_approvals WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── metrics / stats ───────────────────────────────────────────────

    def get_dashboard_stats(self) -> dict:
        conn = self._conn()
        try:
            task_counts = {}
            for status in ("pending", "running", "success", "failed"):
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM cp_tasks WHERE status = ?", (status,)
                ).fetchone()
                task_counts[status] = row["c"] if row else 0

            agent_count = conn.execute("SELECT COUNT(*) as c FROM cp_agents").fetchone()
            job_count = conn.execute("SELECT COUNT(*) as c FROM cp_jobs").fetchone()
            goal_count = conn.execute("SELECT COUNT(*) as c FROM goals").fetchone()

            total_cost = conn.execute(
                "SELECT COALESCE(SUM(cost), 0) as total FROM cp_jobs"
            ).fetchone()

            return {
                "tasks": task_counts,
                "agents": agent_count["c"] if agent_count else 0,
                "jobs": job_count["c"] if job_count else 0,
                "goals": goal_count["c"] if goal_count else 0,
                "total_cost_usd": round(total_cost["total"], 2) if total_cost else 0,
            }
        finally:
            conn.close()
