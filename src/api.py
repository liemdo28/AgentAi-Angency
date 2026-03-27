"""
AgentAI Agency — REST API

Run:
  uvicorn src.api:app --reload          (from project root)
  PYTHONPATH=.:src uvicorn api:app --reload --app-dir src

Handoff endpoints:
  POST   /handoffs                       Create a new handoff
  GET    /handoffs                       List handoffs (?state= ?limit= ?offset=)
  GET    /handoffs/{id}                  Get a single handoff
  PATCH  /handoffs/{id}/approve          Approve a handoff
  PATCH  /handoffs/{id}/block            Block a handoff
  POST   /handoffs/refresh-overdue       Mark overdue handoffs
  GET    /status                         Dashboard counts by state
  GET    /routes                         List all available routes

Task endpoints (AI pipeline):
  POST   /tasks                          Create a new task
  GET    /tasks                          List tasks (?status= ?account_id= ?campaign_id=)
  GET    /tasks/{id}                     Get a single task
  POST   /tasks/{id}/run                 Run task through LangGraph AI pipeline
  GET    /tasks/{id}/review-history      Audit trail for a task
  POST   /tasks/{id}/cancel              Cancel a task

Data collection endpoints:
  POST   /data-collection/request        Send data-request email to client
  POST   /data-collection/inbound        Webhook: process inbound email with attachments
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

import store
from engine import WorkflowEngine
from models import (
    HandoffNotFoundError,
    HandoffState,
    InvalidStateTransitionError,
    MissingInputsError,
    RouteNotFoundError,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# App lifecycle                                                        #
# ------------------------------------------------------------------ #

engine = WorkflowEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Init SQLite DB for task layer on startup
    try:
        from src.db.connection import init_db
        init_db()
    except Exception as exc:
        logger.warning("DB init failed (non-fatal): %s", exc)
    engine.restore(store.load())
    _recover_stuck_tasks()
    yield


app = FastAPI(
    title="AgentAI Agency",
    description="Full AI agency: handoff workflow engine + AI task pipeline + email data collection",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# Request / Response Pydantic schemas                                  #
# ------------------------------------------------------------------ #

class InitiateRequest(BaseModel):
    from_department: str
    to_department: str
    inputs: list[str]

    @field_validator("inputs")
    @classmethod
    def inputs_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("inputs must not be empty")
        return v

    @field_validator("from_department", "to_department")
    @classmethod
    def dept_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("department name must not be blank")
        return v


class BlockRequest(BaseModel):
    reason: str = ""


class PolicyOut(BaseModel):
    from_department: str
    to_department: str
    required_inputs: list[str]
    expected_outputs: list[str]
    sla_hours: int
    approver_role: str


class HandoffOut(BaseModel):
    id: str
    state: str
    created_at: str
    updated_at: str
    notes: str
    provided_inputs: list[str]
    policy: PolicyOut


class HandoffListOut(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[HandoffOut]


class StatusOut(BaseModel):
    draft: int
    approved: int
    blocked: int
    overdue: int


class RefreshOverdueOut(BaseModel):
    flagged_count: int
    ids: list[str]


def _to_handoff_out(h) -> HandoffOut:
    d = store.handoff_to_dict(h)
    return HandoffOut(
        id=d["id"],
        state=d["state"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        notes=d["notes"],
        provided_inputs=d["provided_inputs"],
        policy=PolicyOut(**d["policy"]),
    )


# ------------------------------------------------------------------ #
# Routes                                                               #
# ------------------------------------------------------------------ #

@app.post("/handoffs", status_code=201, response_model=HandoffOut,
          summary="Create a new handoff")
def initiate(req: InitiateRequest):
    try:
        h = engine.initiate(req.from_department, req.to_department, tuple(req.inputs))
        store.save(engine.export_handoffs())
        return _to_handoff_out(h)
    except RouteNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except MissingInputsError as e:
        raise HTTPException(400, detail=str(e))


@app.get("/handoffs", response_model=HandoffListOut,
         summary="List handoffs with optional state filter and pagination")
def list_handoffs(
    state: Optional[str] = Query(None, description="draft | approved | blocked | overdue"),
    limit: int = Query(50, ge=1, le=500, description="Max items to return"),
    offset: int = Query(0, ge=0, description="Items to skip"),
):
    if state:
        try:
            s = HandoffState(state)
        except ValueError:
            valid = [v.value for v in HandoffState]
            raise HTTPException(400, detail=f"Invalid state. Valid values: {valid}")
        items = engine.get_by_state(s)
    else:
        items = engine.all_handoffs()

    total = len(items)
    page = items[offset: offset + limit]
    return HandoffListOut(total=total, offset=offset, limit=limit,
                          items=[_to_handoff_out(h) for h in page])


@app.get("/handoffs/{handoff_id}", response_model=HandoffOut,
         summary="Get a single handoff by ID")
def get_handoff(handoff_id: str):
    try:
        h = engine.get_handoff(handoff_id)
        return _to_handoff_out(h)
    except HandoffNotFoundError as e:
        raise HTTPException(404, detail=str(e))


@app.patch("/handoffs/{handoff_id}/approve", response_model=HandoffOut,
           summary="Approve a handoff")
def approve(handoff_id: str):
    try:
        h = engine.approve(handoff_id)
        store.save(engine.export_handoffs())
        return _to_handoff_out(h)
    except HandoffNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(409, detail=str(e))


@app.patch("/handoffs/{handoff_id}/block", response_model=HandoffOut,
           summary="Block a handoff")
def block(handoff_id: str, req: BlockRequest = BlockRequest()):
    try:
        h = engine.block(handoff_id, req.reason)
        store.save(engine.export_handoffs())
        return _to_handoff_out(h)
    except HandoffNotFoundError as e:
        raise HTTPException(404, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(409, detail=str(e))


@app.post("/handoffs/refresh-overdue", response_model=RefreshOverdueOut,
          summary="Scan and mark all overdue handoffs")
def refresh_overdue():
    flagged = engine.refresh_overdue()
    store.save(engine.export_handoffs())
    return RefreshOverdueOut(flagged_count=len(flagged), ids=[h.id for h in flagged])


@app.get("/status", response_model=StatusOut,
         summary="Dashboard: handoff counts per state")
def status():
    return engine.status()


@app.get("/health", summary="System health check")
def health_check():
    """
    Returns system health status including DB, task queue, and configuration.
    Used for monitoring and deployment readiness checks.
    """
    import os
    health: dict[str, Any] = {
        "status": "ok",
        "checks": {},
    }

    # DB check
    try:
        from src.db.connection import get_db, init_db
        init_db()
        get_db().execute("SELECT 1").fetchone()
        health["checks"]["database"] = "ok"
    except Exception as exc:
        health["checks"]["database"] = f"error: {exc}"
        health["status"] = "degraded"

    # Task queue check (count pending/in-progress)
    try:
        from src.db.connection import get_db
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import TaskStatus
        repo = TaskRepository()
        pending = len(repo.list_by_status(TaskStatus.PENDING))
        in_progress = len(repo.list_by_status(TaskStatus.IN_PROGRESS))
        health["checks"]["task_queue"] = {
            "pending": pending,
            "in_progress": in_progress,
        }
    except Exception as exc:
        health["checks"]["task_queue"] = f"error: {exc}"

    # LLM config check
    try:
        from src.config.settings import SETTINGS
        llm_provider = SETTINGS.LLM_PROVIDER
        has_key = bool(
            os.getenv("ANTHROPIC_API_KEY") or
            os.getenv("OPENAI_API_KEY") or
            os.getenv("OLLAMA_BASE_URL")
        )
        health["checks"]["llm"] = {
            "provider": llm_provider,
            "api_key_configured": has_key,
        }
    except Exception as exc:
        health["checks"]["llm"] = f"error: {exc}"

    # Email config check
    try:
        from src.config.settings import SETTINGS
        health["checks"]["email"] = {
            "smtp_configured": bool(SETTINGS.SMTP_HOST),
            "sendgrid_configured": bool(os.getenv("SENDGRID_API_KEY")),
        }
    except Exception as exc:
        health["checks"]["email"] = f"error: {exc}"

    return health


@app.get("/routes", summary="List all available department routes")
def routes():
    return [
        {
            "from": p.from_department,
            "to": p.to_department,
            "sla_hours": p.sla_hours,
            "approver_role": p.approver_role,
            "required_inputs": list(p.required_inputs),
            "expected_outputs": list(p.expected_outputs),
        }
        for p in engine.list_routes()
    ]


# ================================================================== #
# Task endpoints — AI pipeline                                         #
# ================================================================== #

class CreateTaskRequest(BaseModel):
    goal: str
    description: str = ""
    task_type: str = ""
    account_id: str = ""
    campaign_id: str = ""
    current_department: str = ""
    priority: int = 2  # 1=LOW 2=NORMAL 3=HIGH 4=URGENT
    kpis: dict[str, float] = {}

    @field_validator("goal")
    @classmethod
    def goal_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("goal must not be blank")
        return v


class TaskOut(BaseModel):
    id: str
    goal: str
    description: str
    task_type: str
    status: str
    priority: int
    score: float
    account_id: str
    campaign_id: str
    current_department: str
    retry_count: int
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    final_output_text: str
    notes: str


class TaskListOut(BaseModel):
    total: int
    items: list[TaskOut]


class RunTaskResult(BaseModel):
    task_id: str
    status: str
    score: float
    final_output: str
    retry_count: int
    errors: list[str]


def _task_to_out(task) -> TaskOut:
    return TaskOut(
        id=task.id,
        goal=task.goal,
        description=task.description or "",
        task_type=task.task_type or "",
        status=task.status.value if hasattr(task.status, "value") else str(task.status),
        priority=int(task.priority),
        score=float(task.score),
        account_id=task.account_id or "",
        campaign_id=task.campaign_id or "",
        current_department=task.current_department or "",
        retry_count=task.retry_count,
        created_at=task.created_at or "",
        started_at=task.started_at or None,
        completed_at=task.completed_at or None,
        final_output_text=task.final_output_text or "",
        notes=task.notes or "",
    )


@app.post("/tasks", status_code=201, response_model=TaskOut,
          summary="Create a new AI task")
def create_task(req: CreateTaskRequest):
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import Priority, Task, TaskStatus

        init_db()
        repo = TaskRepository()
        task = Task(
            goal=req.goal,
            description=req.description,
            task_type=req.task_type,
            account_id=req.account_id,
            campaign_id=req.campaign_id,
            current_department=req.current_department,
            priority=Priority(req.priority),
            kpis=req.kpis,
            status=TaskStatus.DRAFT,
        )
        repo.create(task)
        return _task_to_out(task)
    except ValueError as exc:
        # Invalid enum value (bad priority) or model validation failure
        raise HTTPException(400, detail=f"Invalid task parameter: {exc}")
    except sqlite3.IntegrityError as exc:
        # Duplicate task ID
        raise HTTPException(409, detail=f"Task already exists: {exc}")
    except sqlite3.OperationalError as exc:
        # DB connection / table not found
        logger.error("Database operational error: %s", exc)
        raise HTTPException(503, detail="Database unavailable. Please retry shortly.")
    except Exception as exc:
        logger.exception("create_task failed: %s", exc)
        raise HTTPException(500, detail=f"Unexpected error creating task: {exc}")


@app.get("/tasks", response_model=TaskListOut,
         summary="List tasks with optional filters")
def list_tasks(
    status: Optional[str] = Query(None, description="Filter by TaskStatus value"),
    account_id: Optional[str] = Query(None),
    campaign_id: Optional[str] = Query(None),
):
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository

        init_db()
        repo = TaskRepository()
        if campaign_id:
            items = repo.list_by_campaign(campaign_id)
        elif status:
            items = repo.list_by_status(status)
        else:
            items = repo.list_active()

        if account_id:
            items = [t for t in items if t.account_id == account_id]

        return TaskListOut(total=len(items), items=[_task_to_out(t) for t in items])
    except ValueError as exc:
        raise HTTPException(400, detail=f"Invalid list filter: {exc}")
    except sqlite3.OperationalError as exc:
        logger.error("Database error in list_tasks: %s", exc)
        raise HTTPException(503, detail="Database unavailable.")
    except Exception as exc:
        logger.exception("list_tasks failed: %s", exc)
        raise HTTPException(500, detail="Unexpected error listing tasks.")


@app.get("/tasks/{task_id}", response_model=TaskOut,
         summary="Get a single task by ID")
def get_task(task_id: str):
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository

        init_db()
        repo = TaskRepository()
        task = repo.get(task_id)
        if not task:
            raise HTTPException(404, detail=f"Task not found: {task_id}")
        return _task_to_out(task)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, detail=f"Invalid task data: {exc}")
    except sqlite3.OperationalError as exc:
        logger.error("Database error in get_task: %s", exc)
        raise HTTPException(503, detail="Database unavailable.")
    except Exception as exc:
        logger.exception("get_task failed: %s", exc)
        raise HTTPException(500, detail="Unexpected error fetching task.")


def _run_task_background(task_id: str) -> None:
    """Execute run_task_sync in a background thread (RISK-008)."""
    import threading
    from src.db.connection import init_db
    from src.db.repositories.task_repo import TaskRepository
    from src.task_runner import run_task_sync

    def _worker():
        try:
            init_db()
            repo = TaskRepository()
            task = repo.get(task_id)
            if task:
                run_task_sync(task)
        except Exception as exc:
            logger.exception("Background task %s failed: %s", task_id, exc)

    thread = threading.Thread(target=_worker, daemon=True, name=f"task-{task_id}")
    thread.start()


def _recover_stuck_tasks() -> None:
    """
    On startup: re-enqueue any tasks left IN_PROGRESS from a previous crash.
    This prevents tasks from being permanently stuck after server restart (RISK-008 durability).
    """
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import TaskStatus

        init_db()
        repo = TaskRepository()
        stuck = repo.list_by_status(TaskStatus.IN_PROGRESS)
        if stuck:
            logger.warning(
                "Startup recovery: found %d stuck IN_PROGRESS tasks, re-enqueueing", len(stuck)
            )
            for task in stuck:
                _run_task_background(task.id)
    except Exception as exc:
        logger.warning("Startup task recovery failed (non-fatal): %s", exc)


@app.post("/tasks/{task_id}/run",
          summary="Enqueue task through the LangGraph AI pipeline (returns 202, poll GET /tasks/{id})",
          status_code=202)
def run_task(task_id: str, background_tasks: BackgroundTasks):
    """
    Enqueue a task for async execution (RISK-008: non-blocking API).

    Returns 202 Accepted immediately. Poll GET /tasks/{task_id} for status.
    Status transitions: PENDING → IN_PROGRESS → PASSED | FAILED | ESCALATED
    """
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import TaskStatus, now_iso

        init_db()
        repo = TaskRepository()
        task = repo.get(task_id)
        if not task:
            raise HTTPException(404, detail=f"Task not found: {task_id}")
        if task.status and task.status.value == "IN_PROGRESS":
            raise HTTPException(409, detail=f"Task {task_id} is already running.")

        # Mark as IN_PROGRESS immediately so caller knows it's queued
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = now_iso()
        repo.upsert(task)

        background_tasks.add_task(_run_task_background, task_id)

        return {
            "task_id": task_id,
            "status": "IN_PROGRESS",
            "message": "Task queued. Poll GET /tasks/{task_id} for results.",
        }
    except HTTPException:
        raise
    except sqlite3.OperationalError as exc:
        logger.error("Database error in run_task: %s", exc)
        raise HTTPException(503, detail="Database unavailable.")
    except Exception as exc:
        logger.exception("run_task enqueue failed: %s", exc)
        raise HTTPException(500, detail=f"Unexpected error enqueuing task: {exc}")


@app.get("/tasks/{task_id}/review-history",
         summary="Get the review/scoring audit trail for a task")
def get_review_history(task_id: str):
    try:
        from src.db.connection import get_db, init_db

        init_db()
        db = get_db()
        rows = db.execute(
            "SELECT * FROM review_history WHERE task_id = ? ORDER BY timestamp",
            (task_id,),
        ).fetchall()
        history = []
        for row in rows:
            r = dict(row)
            try:
                r["breakdown"] = json.loads(r.pop("breakdown_json", "{}") or "{}")
            except Exception:
                r["breakdown"] = {}
            history.append(r)
        return {"task_id": task_id, "history": history}
    except ValueError as exc:
        raise HTTPException(400, detail=f"Invalid filter: {exc}")
    except sqlite3.OperationalError as exc:
        logger.error("Database error in get_review_history: %s", exc)
        raise HTTPException(503, detail="Database unavailable.")
    except Exception as exc:
        logger.exception("get_review_history failed: %s", exc)
        raise HTTPException(500, detail="Unexpected error fetching review history.")


@app.post("/tasks/{task_id}/cancel",
          summary="Cancel a task")
def cancel_task(task_id: str):
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import TaskStatus

        init_db()
        repo = TaskRepository()
        task = repo.get(task_id)
        if not task:
            raise HTTPException(404, detail=f"Task not found: {task_id}")
        if task.status in (TaskStatus.PASSED, TaskStatus.DONE, TaskStatus.CANCELLED):
            raise HTTPException(409, detail=f"Cannot cancel task in state: {task.status.value}")
        repo.update_status(task_id, TaskStatus.CANCELLED)
        return {"task_id": task_id, "status": "cancelled"}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, detail=f"Invalid task state: {exc}")
    except sqlite3.OperationalError as exc:
        logger.error("Database error in cancel_task: %s", exc)
        raise HTTPException(503, detail="Database unavailable.")
    except Exception as exc:
        logger.exception("cancel_task failed: %s", exc)
        raise HTTPException(500, detail="Unexpected error cancelling task.")


@app.post("/tasks/{task_id}/approve-notification",
          summary="Release a held notification email for human-approved tasks")
def approve_notification(task_id: str):
    """
    Release an email notification that was held pending human approval (RISK-013).

    Sets metadata.human_approved=True and re-runs the notification node.
    The email body/subject are retrieved from the held notification stored in metadata.
    """
    try:
        from src.db.connection import init_db
        from src.db.repositories.task_repo import TaskRepository
        from src.tasks.models import TaskStatus

        init_db()
        repo = TaskRepository()
        task = repo.get(task_id)
        if not task:
            raise HTTPException(404, detail=f"Task not found: {task_id}")
        if task.status not in (TaskStatus.PASSED, TaskStatus.DONE):
            raise HTTPException(409, detail=f"Task must be PASSED/DONE to approve notification (current: {task.status.value if task.status else 'unknown'})")

        # Read held notification from final_output_json metadata
        held_meta = (task.final_output_json or {}).get("notification_held_meta", {})
        to_email = held_meta.get("notification_to", "")
        subject = held_meta.get("notification_subject", f"[Agency AI] Task {task_id} complete")
        body = held_meta.get("notification_body", task.final_output_text or "")

        if not to_email:
            raise HTTPException(422, detail="No held notification found for this task. Was require_approval=True when it ran?")

        # Send the held email
        from src.tools.email_client import EmailClient, EmailMessage
        client = EmailClient()
        receipt = client.send(EmailMessage(to=to_email, subject=subject, body=body))
        client.close()

        # Log to audit trail
        repo.add_audit_log(
            actor="human_approver",
            action_type="notification_approved",
            entity_type="task",
            entity_id=task_id,
            details={"sent_to": to_email, "status": receipt.status},
        )

        return {
            "task_id": task_id,
            "notification_sent": receipt.status == "sent",
            "sent_to": to_email,
            "status": receipt.status,
            "error": receipt.error,
        }
    except HTTPException:
        raise
    except sqlite3.OperationalError as exc:
        logger.error("Database error in approve_notification: %s", exc)
        raise HTTPException(503, detail="Database unavailable.")
    except Exception as exc:
        logger.exception("approve_notification failed: %s", exc)
        raise HTTPException(500, detail=f"Unexpected error: {exc}")


# ================================================================== #
# Data collection endpoints — email workflow                           #
# ================================================================== #

class DataRequestBody(BaseModel):
    account_id: str
    account_email: str
    report_date: str  # e.g. "2026-03"
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None

    @field_validator("account_email")
    @classmethod
    def email_has_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("account_email must be a valid email address")
        return v


class InboundEmailBody(BaseModel):
    raw_email_b64: str  # base64-encoded RFC-822 bytes
    account_mapping: dict[str, str]  # partial sender → account_id
    trigger_task: bool = True


@app.post("/data-collection/request",
          summary="Send a data-report request email to a client")
def data_collection_request(req: DataRequestBody):
    try:
        from src.ingestion.data_collection import send_data_request_email
        result = send_data_request_email(
            account_id=req.account_id,
            account_email=req.account_email,
            report_date=req.report_date,
            custom_subject=req.custom_subject,
            custom_body=req.custom_body,
        )
        if result["status"] == "failed":
            raise HTTPException(502, detail=result.get("error", "Email send failed"))
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, detail=f"Invalid email parameter: {exc}")
    except Exception as exc:
        logger.exception("data_collection_request failed: %s", exc)
        raise HTTPException(500, detail=f"Unexpected error sending data request: {exc}")


@app.post("/data-collection/inbound",
          summary="Webhook: process inbound client email with attachments")
def data_collection_inbound(req: InboundEmailBody):
    try:
        import base64
        from src.ingestion.data_collection import process_inbound_email

        try:
            raw_bytes = base64.b64decode(req.raw_email_b64)
        except Exception:
            raise HTTPException(400, detail="raw_email_b64 is not valid base64")

        result = process_inbound_email(
            raw_bytes=raw_bytes,
            account_mapping=req.account_mapping,
            trigger_task=req.trigger_task,
        )
        if result["status"] == "unmatched":
            raise HTTPException(
                422,
                detail="Sender does not match any known account. "
                       "Add the sender domain to account_mapping.",
            )
        return result
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(400, detail=f"Invalid inbound email parameter: {exc}")
    except Exception as exc:
        logger.exception("data_collection_inbound failed: %s", exc)
        raise HTTPException(500, detail=f"Unexpected error processing inbound email: {exc}")
