"""
Job Queue & Audit Log System for Unified API.

Manages all async actions across projects:
- Job lifecycle (pending, running, success, failed, retrying, cancelled)
- Audit logs for every action
- File tracking for uploads
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Path to database
DB_PATH = Path(__file__).parent.parent.parent / "data" / "unified.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# ============================================
# Enums
# ============================================

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class JobPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class AuditLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================
# Pydantic Models (for API responses)
# ============================================

class JobCreateRequest(BaseModel):
    project_id: str
    action_id: str
    payload: Optional[dict] = None
    priority: int = JobPriority.NORMAL
    requested_by: str = "system"
    description: Optional[str] = None


class JobResponse(BaseModel):
    id: str
    project_id: str
    action_id: str
    status: str
    priority: int
    payload: dict
    result: Optional[dict]
    error_message: Optional[str]
    requested_by: str
    requested_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    duration_ms: Optional[float]
    retry_count: int
    logs: list[dict]


class AuditLogEntry(BaseModel):
    id: str
    job_id: Optional[str]
    level: str
    message: str
    context: dict
    created_at: str


# ============================================
# Dataclasses
# ============================================

@dataclass
class Job:
    id: str
    project_id: str
    action_id: str
    status: JobStatus = JobStatus.PENDING
    priority: int = JobPriority.NORMAL
    payload: dict = field(default_factory=dict)
    result: Optional[dict] = None
    error_message: Optional[str] = None
    requested_by: str = "system"
    requested_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "status": self.status.value,
            "priority": self.priority,
            "requested_at": self.requested_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
        }


@dataclass
class AuditLog:
    id: str
    job_id: Optional[str]
    level: AuditLevel
    message: str
    context: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "level": self.level.value,
            "message": self.message,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
        }


# ============================================
# Database Manager
# ============================================

class JobDB:
    """SQLite-based job queue and audit log storage."""

    _instance: Optional["JobDB"] = None

    def __init__(self):
        self._db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._ensure_tables()

    @classmethod
    def get_instance(cls) -> "JobDB":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _ensure_tables(self) -> None:
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                priority INTEGER NOT NULL DEFAULT 1,
                payload TEXT NOT NULL DEFAULT '{}',
                result TEXT,
                error_message TEXT,
                requested_by TEXT NOT NULL DEFAULT 'system',
                requested_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                duration_ms REAL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                next_retry_at TEXT
            );

            CREATE TABLE IF NOT EXISTS job_logs (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                job_id TEXT,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                mime_type TEXT,
                size INTEGER,
                uploaded_by TEXT,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_requested_at ON jobs(requested_at);
            CREATE INDEX IF NOT EXISTS idx_job_logs_job ON job_logs(job_id);
            CREATE INDEX IF NOT EXISTS idx_job_logs_level ON job_logs(level);
        """)
        self._db.commit()

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            project_id=row["project_id"],
            action_id=row["action_id"],
            status=JobStatus(row["status"]),
            priority=row["priority"],
            payload=json.loads(row["payload"]),
            result=json.loads(row["result"]) if row["result"] else None,
            error_message=row["error_message"],
            requested_by=row["requested_by"],
            requested_at=datetime.fromisoformat(row["requested_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            duration_ms=row["duration_ms"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            next_retry_at=datetime.fromisoformat(row["next_retry_at"]) if row["next_retry_at"] else None,
        )

    def create_job(self, job: Job) -> Job:
        d = job.to_dict()
        self._db.execute(
            """INSERT INTO jobs
               (id, project_id, action_id, status, priority, payload, result, error_message,
                requested_by, requested_at, started_at, finished_at, duration_ms,
                retry_count, max_retries, next_retry_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (d["id"], d["project_id"], d["action_id"], d["status"], d["priority"],
             json.dumps(d["payload"]), None, None, d["requested_by"], d["requested_at"],
             d["started_at"], d["finished_at"], d["duration_ms"], d["retry_count"],
             job.max_retries, d["next_retry_at"])
        )
        self._db.commit()
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        row = self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(
        self,
        project_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY priority DESC, requested_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._db.execute(query, params).fetchall()
        return [self._row_to_job(r) for r in rows]

    def update_job(self, job: Job) -> Job:
        d = job.to_dict()
        self._db.execute(
            """UPDATE jobs SET
               status=?, payload=?, result=?, error_message=?,
               started_at=?, finished_at=?, duration_ms=?,
               retry_count=?, next_retry_at=?
               WHERE id=?""",
            (d["status"], json.dumps(d["payload"]),
             json.dumps(d["result"]) if d["result"] else None,
             d["error_message"], d["started_at"], d["finished_at"],
             d["duration_ms"], d["retry_count"], d["next_retry_at"],
             d["id"])
        )
        self._db.commit()
        return job

    def count_jobs(self, status: Optional[JobStatus] = None) -> dict[str, int]:
        if status:
            row = self._db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = ?", (status.value,)
            ).fetchone()
            return {status.value: row[0] if row else 0}
        rows = self._db.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["count"] for r in rows}

    def add_log(self, log: AuditLog) -> None:
        d = log.to_dict()
        self._db.execute(
            """INSERT INTO job_logs (id, job_id, level, message, context, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (d["id"], d["job_id"], d["level"], d["message"], json.dumps(d["context"]), d["created_at"])
        )
        self._db.commit()

    def get_job_logs(self, job_id: str) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM job_logs WHERE job_id = ? ORDER BY created_at ASC",
            (job_id,)
        ).fetchall()
        return [
            {
                "id": r["id"],
                "level": r["level"],
                "message": r["message"],
                "context": json.loads(r["context"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def list_logs(
        self,
        level: Optional[AuditLevel] = None,
        job_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        query = "SELECT * FROM job_logs WHERE 1=1"
        params: list = []
        if job_id:
            query += " AND job_id = ?"
            params.append(job_id)
        if level:
            query += " AND level = ?"
            params.append(level.value)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._db.execute(query, params).fetchall()
        return [
            {
                "id": r["id"],
                "job_id": r["job_id"],
                "level": r["level"],
                "message": r["message"],
                "context": json.loads(r["context"]),
                "created_at": r["created_at"],
            }
            for r in rows
        ]


# ============================================
# Job Runner (async worker)
# ============================================

async def _run_connector(
    connector: Any,
    action_id: str,
    payload: dict,
    job_id: str,
    timeout_seconds: float,
):
    """Wrap connector.execute_action with a timeout, returning a ConnectorResult on timeout."""
    try:
        return await asyncio.wait_for(
            connector.execute_action(
                action_id=action_id,
                payload=payload,
                job_id=job_id,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        from src.unified.connectors.base import ConnectorResult
        return ConnectorResult(
            success=False,
            message=f"Connector timed out after {timeout_seconds}s",
            error="timeout",
            duration_ms=timeout_seconds * 1000,
        )


def _handle_job_error(
    job: Job,
    job_id: str,
    db: "JobDB",
    error_msg: str,
    error_type: str,
) -> None:
    """Centralized error + retry/fail logic."""
    from src.unified.settings import get_settings
    settings = get_settings()

    if job.status == JobStatus.CANCELLED:
        return

    if job.retry_count < job.max_retries:
        job.status = JobStatus.RETRYING
        job.retry_count += 1
        backoff = settings.job_backoff_seconds * job.retry_count
        job.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
        job.error_message = error_msg
        db.add_log(AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            level=AuditLevel.WARNING,
            message=f"Job failed, retrying ({job.retry_count}/{job.max_retries}) in {backoff}s",
            context={
                "error": error_msg,
                "error_type": error_type,
                "retry_at": job.next_retry_at.isoformat(),
                "backoff_seconds": backoff,
            },
        ))
        logger.info(
            "Job %s scheduled for retry %d/%d at %s",
            job_id, job.retry_count, job.max_retries, job.next_retry_at,
        )
    else:
        job.status = JobStatus.FAILED
        job.error_message = error_msg
        db.add_log(AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            level=AuditLevel.ERROR,
            message=f"Job failed permanently after {job.retry_count} retries: {error_msg}",
            context={
                "error": error_msg,
                "error_type": error_type,
                "total_retries": job.retry_count,
            },
        ))
        logger.error("Job %s FAILED permanently after %d retries", job_id, job.retry_count)


class JobRunner:
    """
    Async job runner that processes jobs from the queue.
    Uses the connector system to execute actions.
    """

    def __init__(self):
        self._running_jobs: dict[str, Job] = {}

    def generate_id(self) -> str:
        return f"job_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"

    def create(
        self,
        project_id: str,
        action_id: str,
        payload: Optional[dict] = None,
        priority: int = JobPriority.NORMAL,
        requested_by: str = "system",
        description: Optional[str] = None,
    ) -> tuple[Job, AuditLog]:
        """Create a new job and return it with the initial log entry."""
        job_id = self.generate_id()
        job = Job(
            id=job_id,
            project_id=project_id,
            action_id=action_id,
            priority=priority,
            payload=payload or {},
            requested_by=requested_by,
        )
        db = JobDB.get_instance()
        db.create_job(job)
        log = AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            level=AuditLevel.INFO,
            message=f"Job created: {action_id} on {project_id}",
            context={
                "project_id": project_id,
                "action_id": action_id,
                "payload": payload or {},
                "requested_by": requested_by,
            },
        )
        db.add_log(log)
        logger.info("Job created: %s (%s/%s)", job_id, project_id, action_id)
        return job, log

    async def run(self, job_id: str) -> Job:
        """
        Execute a job using the appropriate connector.
        Hardened with: full audit trail, connector-level timeout,
        structured error logging with traceback, retry with backoff.
        """
        from src.unified.settings import get_settings
        settings = get_settings()
        db = JobDB.get_instance()
        job = db.get_job(job_id)

        if not job:
            logger.error("Job not found: %s", job_id)
            raise ValueError(f"Job not found: {job_id}")

        if job.status not in (JobStatus.PENDING, JobStatus.RETRYING):
            logger.warning("Job %s is not runnable (status: %s)", job_id, job.status)
            return job

        # Mark running
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        db.update_job(job)

        db.add_log(AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            level=AuditLevel.INFO,
            message=f"[{job.project_id}] {job.action_id} started",
            context={
                "started_at": job.started_at.isoformat(),
                "payload_keys": list((job.payload or {}).keys()),
            },
        ))
        logger.info("Job %s started: %s/%s", job_id, job.project_id, job.action_id)

        timeout = (
            settings.integration_timeout
            if job.project_id == "integration-full"
            else settings.job_default_timeout
        )

        try:
            from src.unified.connectors import get_connector
            connector = get_connector(job.project_id)

            if not connector:
                raise RuntimeError(f"No connector registered for project: {job.project_id}")

            result = await _run_connector(
                connector,
                job.action_id,
                job.payload,
                job_id,
                float(timeout),
            )

            duration_ms = result.duration_ms or 0

            if result.success:
                job.status = JobStatus.SUCCESS
                job.result = {
                    "success": True,
                    "message": result.message,
                    "data": result.data,
                    "status_code": result.status_code,
                    "duration_ms": duration_ms,
                }
                logger.info("Job %s succeeded (%.1fms): %s", job_id, duration_ms, result.message)
                db.add_log(AuditLog(
                    id=f"log_{uuid.uuid4().hex[:8]}",
                    job_id=job_id,
                    level=AuditLevel.INFO,
                    message=f"Job succeeded: {result.message}",
                    context={
                        "duration_ms": duration_ms,
                        "data_keys": list((result.data or {}).keys()),
                    },
                ))
            else:
                raise RuntimeError(
                    result.message
                    or f"Connector returned failure (HTTP {result.status_code})"
                )

        except asyncio.TimeoutError:
            _handle_job_error(job, job_id, db, f"Job timed out after {timeout}s", "timeout")
        except asyncio.CancelledError:
            _handle_job_error(job, job_id, db, "Job was cancelled", "cancelled")
        except Exception as e:
            tb = traceback.format_exc()
            error_msg = str(e)
            logger.warning("Job %s failed: %s\n%s", job_id, error_msg, tb)
            _handle_job_error(job, job_id, db, error_msg, type(e).__name__)

        finally:
            job.finished_at = datetime.now(timezone.utc)
            if job.started_at:
                job.duration_ms = (job.finished_at - job.started_at).total_seconds() * 1000
            db.update_job(job)

        return job

    def get(self, job_id: str) -> Optional[Job]:
        return JobDB.get_instance().get_job(job_id)

    def list_jobs(
        self,
        project_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Job]:
        return JobDB.get_instance().list_jobs(project_id, status, limit, offset)

    def cancel(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if not job:
            return None
        if job.status in (JobStatus.PENDING, JobStatus.RETRYING):
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(timezone.utc)
            JobDB.get_instance().update_job(job)
            JobDB.get_instance().add_log(AuditLog(
                id=f"log_{uuid.uuid4().hex[:8]}",
                job_id=job_id,
                level=AuditLevel.INFO,
                message="Job cancelled by user",
                context={},
            ))
        return job

    def get_logs(self, job_id: str) -> list[dict]:
        return JobDB.get_instance().get_job_logs(job_id)

    def add_log(
        self,
        job_id: Optional[str],
        level: AuditLevel,
        message: str,
        context: Optional[dict] = None,
    ) -> AuditLog:
        log = AuditLog(
            id=f"log_{uuid.uuid4().hex[:8]}",
            job_id=job_id,
            level=level,
            message=message,
            context=context or {},
        )
        JobDB.get_instance().add_log(log)
        return log
