"""
Control Plane API — FastAPI service for managing the orchestrator.

Provides endpoints for:
  - Goals (CRUD)
  - Tasks (create, list, cancel)
  - Agents (register, list, status)
  - Jobs (list, inspect)
  - Approvals (list, approve, reject)
  - Dashboard stats
  - Manual orchestrator cycle trigger

Run:
    uvicorn apps.api.main:app --host 0.0.0.0 --port 8002 --reload
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from db.repository import ControlPlaneDB
from core.orchestrator.registry import AgentRegistry
from core.policies.engine import PolicyEngine
from core.orchestrator.engine import Orchestrator
from apps.worker.heartbeat import build_registry

# ── App setup ─────────────────────────────────────────────────────────

app = FastAPI(
    title="AgentAI Control Plane",
    version="1.0.0",
    description="Orchestrator management API for the AI Agency",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared singletons ────────────────────────────────────────────────

db = ControlPlaneDB()
registry = build_registry()
policy_engine = PolicyEngine()
orchestrator = Orchestrator(db=db, agent_registry=registry, policy_engine=policy_engine)


# ── Request / Response models ─────────────────────────────────────────

class GoalCreate(BaseModel):
    title: str
    description: str = ""
    owner: str = ""


class TaskCreate(BaseModel):
    title: str
    assigned_agent_id: str
    goal_id: str = ""
    description: str = ""
    task_type: str = "default"
    priority: int = 2
    context_json: dict | None = None


class AgentRegister(BaseModel):
    id: str
    role: str
    agent_type: str
    model: str = ""
    budget_limit: float = 50.0


class ApprovalResolve(BaseModel):
    status: str  # "approved" or "rejected"
    approved_by: str = ""
    reason: str = ""


# ── Dashboard ─────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "AgentAI Control Plane", "version": "1.0.0"}


@app.get("/dashboard/stats")
def dashboard_stats():
    return db.get_dashboard_stats()


@app.post("/orchestrator/cycle")
def trigger_cycle():
    """Manually trigger one orchestrator cycle."""
    stats = orchestrator.run_cycle()
    return {"status": "ok", "cycle_stats": stats}


# ── Goals ─────────────────────────────────────────────────────────────

@app.post("/goals")
def create_goal(body: GoalCreate):
    return db.create_goal(title=body.title, description=body.description, owner=body.owner)


@app.get("/goals")
def list_goals():
    return db.list_goals()


# ── Tasks ─────────────────────────────────────────────────────────────

@app.post("/tasks")
def create_task(body: TaskCreate):
    return db.create_task(
        title=body.title,
        assigned_agent_id=body.assigned_agent_id,
        goal_id=body.goal_id,
        description=body.description,
        task_type=body.task_type,
        priority=body.priority,
        context_json=body.context_json,
    )


@app.get("/tasks")
def list_tasks(status: Optional[str] = None, limit: int = 100):
    return db.list_tasks(status=status, limit=limit)


@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: str):
    task = db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.update_task_status(task_id, "cancelled")
    return {"status": "cancelled"}


# ── Agents ────────────────────────────────────────────────────────────

@app.post("/agents")
def register_agent_db(body: AgentRegister):
    return db.register_agent(
        agent_id=body.id,
        role=body.role,
        agent_type=body.agent_type,
        model=body.model,
        budget_limit=body.budget_limit,
    )


@app.get("/agents")
def list_agents():
    return db.list_agents()


@app.get("/agents/runtime")
def list_runtime_agents():
    """List agents currently loaded in the orchestrator registry."""
    return registry.list_agents()


# ── Jobs ──────────────────────────────────────────────────────────────

@app.get("/jobs")
def list_jobs(task_id: Optional[str] = None, limit: int = 50):
    return db.list_jobs(task_id=task_id, limit=limit)


# ── Approvals ─────────────────────────────────────────────────────────

@app.get("/approvals")
def list_approvals(status: str = "pending"):
    return db.list_approvals(status=status)


@app.post("/approvals/{task_id}/request")
def request_approval(task_id: str):
    return db.request_approval(task_id)


@app.post("/approvals/{approval_id}/resolve")
def resolve_approval(approval_id: str, body: ApprovalResolve):
    db.resolve_approval(
        approval_id=approval_id,
        status=body.status,
        approved_by=body.approved_by,
        reason=body.reason,
    )
    return {"status": body.status}


# ── Activity Feed ─────────────────────────────────────────────────────

@app.get("/activity")
def get_activity(limit: int = 50):
    """Combined feed of recent tasks + jobs for the activity page."""
    tasks = db.list_tasks(limit=limit)
    jobs = db.list_jobs(limit=limit)
    return {"tasks": tasks, "jobs": jobs}
