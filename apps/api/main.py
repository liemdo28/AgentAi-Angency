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

import importlib
import json
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from db.repository import ControlPlaneDB
from apps.api.project_ops import build_project_ops_profile
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

# Auto-register all runtime agents in DB so FK constraints work
for _agent_info in registry.list_agents():
    db.register_agent(
        agent_id=_agent_info["id"],
        role=_agent_info.get("title", _agent_info["id"]),
        agent_type=_agent_info["type"],
        model=_agent_info.get("model", ""),
        budget_limit=50.0,
    )


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


class EdgeProjectSnapshotUpsert(BaseModel):
    machine_id: str
    machine_name: str
    source_type: str = "integration-full"
    app_version: str = ""
    snapshot: dict


class ProjectCommandCreate(BaseModel):
    machine_id: str
    machine_name: str
    command_type: str
    title: str = ""
    created_by: str = "agentai-ui"
    source_suggestion_id: str = ""
    payload: dict | None = None
    max_attempts: int = 3


class EdgeCommandResolve(BaseModel):
    status: str
    result: dict | None = None
    error_message: str = ""


class EdgeCommandLeaseUpdate(BaseModel):
    heartbeat_seconds: int = 120


class EdgeMachineControlUpdate(BaseModel):
    paused: bool | None = None
    draining: bool | None = None
    pause_reason: str | None = None
    cancel_pending: bool = False


class DepartmentUpsert(BaseModel):
    code: str
    name: str
    description: str = ""
    category: str = "general"
    status: str = "active"
    allow_store_assignment: bool = True
    allow_ai_agent_execution: bool = True
    allow_human_assignment: bool = True
    requires_ceo_visibility_only: bool = False
    execution_mode: str = "suggest_only"
    parent_department_id: str | None = None


class DepartmentPermissionItem(BaseModel):
    key: str
    allowed: bool


class DepartmentPermissionUpdate(BaseModel):
    permissions: list[DepartmentPermissionItem]


class StoreDepartmentAssignmentItem(BaseModel):
    department_id: str
    enabled: bool = True
    locked: bool = False
    hidden: bool = False
    deleted: bool = False
    custom_policy_enabled: bool = False
    execution_mode: str | None = None


class StoreDepartmentBulkUpdate(BaseModel):
    departments: list[StoreDepartmentAssignmentItem]


class StoreDepartmentPermissionUpdate(BaseModel):
    permissions: list[DepartmentPermissionItem]


class PolicyUpsert(BaseModel):
    policy_code: str
    policy_name: str
    scope_type: str
    target_type: str
    target_id: str
    condition_json: dict | None = None
    effect: str
    approval_chain_json: list[str] | None = None
    escalation_json: dict | None = None
    audit_required: bool = True
    priority: int = 100
    is_active: bool = True
    effective_from: str | None = None
    effective_to: str | None = None


class GovernanceEvaluateRequest(BaseModel):
    actor_type: str = "agent"
    actor_id: str = "agentai"
    actor_role: str = "ceo"
    store_id: str | None = None
    department_id: str
    action: str
    permission_key: str | None = None
    context: dict | None = None


class GovernanceActionRequest(GovernanceEvaluateRequest):
    task_id: str | None = None
    edge_command: dict | None = None


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


# ── Smart Issues (AI Workflow Planner) ─────────────────────────────────

class SmartIssueRequest(BaseModel):
    text: str  # natural language request
    auto_create: bool = False  # if True, auto-create all tasks


@app.post("/issues/plan")
def plan_smart_issue(body: SmartIssueRequest):
    """Analyze a natural language request and return a multi-department workflow plan."""
    from core.orchestrator.workflow_planner import plan_workflow
    plan = plan_workflow(body.text)
    return plan


@app.post("/issues/execute")
def execute_smart_issue(body: SmartIssueRequest):
    """Plan AND create all tasks + goal from a natural language request."""
    from core.orchestrator.workflow_planner import plan_workflow
    plan = plan_workflow(body.text)

    # 1. Create a goal for this workflow
    goal = db.create_goal(
        title=plan["template_name"] + ": " + body.text[:80],
        description=plan["summary"],
        owner="workflow",
    )

    # 2. Create sub-tasks for each phase
    created_tasks = []
    for phase in plan["phases"]:
        for task_spec in phase["tasks"]:
            t = db.create_task(
                title=task_spec["title"],
                assigned_agent_id=task_spec["agent_id"],
                goal_id=goal["id"],
                description=task_spec["description"],
                task_type="smart_workflow",
                priority=task_spec["priority"],
                context_json={
                    "phase": phase["phase"],
                    "phase_name": phase["name"],
                    "original_request": body.text,
                    "tools": task_spec.get("tools", []),
                },
            )
            created_tasks.append(t)

    return {
        "goal": goal,
        "plan": plan,
        "created_tasks": created_tasks,
        "total_created": len(created_tasks),
    }


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
def list_approvals(status: str = "pending", resource_type: str | None = None):
    return db.list_approvals(status=status, resource_type=resource_type)


@app.post("/approvals/{task_id}/request")
def request_approval(task_id: str):
    return db.request_approval(task_id)


@app.post("/approvals/{approval_id}/resolve")
def resolve_approval(approval_id: str, body: ApprovalResolve):
    approval = db.resolve_approval(
        approval_id=approval_id,
        status=body.status,
        approved_by=body.approved_by,
        reason=body.reason,
    )
    return {"status": body.status, "approval": approval}


# ── Activity Feed ─────────────────────────────────────────────────────

@app.get("/activity")
def get_activity(limit: int = 50):
    """Combined feed of recent tasks + jobs + approvals for the activity page."""
    tasks = db.list_tasks(limit=limit)
    jobs = db.list_jobs(limit=limit)
    approvals = db.list_approvals(status="all")[:limit]
    return {"tasks": tasks, "jobs": jobs, "approvals": approvals}


# ── Department Governance ────────────────────────────────────────────

@app.get("/permissions")
def list_permissions(module: str | None = None):
    return db.list_permissions(module=module)


@app.get("/departments")
def list_departments(
    status: str | None = None,
    visibility: str | None = None,
    search: str | None = None,
    category: str | None = None,
    x_actor_role: str | None = Header(default=None),
):
    _, actor_role = _actor_defaults(None, x_actor_role)
    return db.list_departments(
        status=status,
        visibility=visibility,
        search=search,
        category=category,
        actor_role=actor_role,
    )


@app.post("/departments")
def create_department(
    body: DepartmentUpsert,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can create departments.")
    try:
        return db.create_department(body.model_dump(), actor_id=actor_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"Department create failed: {exc}") from exc


@app.get("/departments/{department_id}")
def get_department(department_id: str, x_actor_role: str | None = Header(default=None)):
    _, actor_role = _actor_defaults(None, x_actor_role)
    department = db.get_department(department_id, actor_role=actor_role)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.put("/departments/{department_id}")
def update_department(
    department_id: str,
    body: DepartmentUpsert,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can edit departments.")
    try:
        department = db.update_department(department_id, body.model_dump(), actor_id=actor_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"Department update failed: {exc}") from exc
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.post("/departments/{department_id}/lock")
def lock_department(
    department_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can lock departments.")
    department = db.set_department_status(department_id, "locked", actor_id=actor_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.post("/departments/{department_id}/unlock")
def unlock_department(
    department_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can unlock departments.")
    department = db.set_department_status(department_id, "active", actor_id=actor_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.post("/departments/{department_id}/hide")
def hide_department(
    department_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can hide departments.")
    department = db.set_department_status(department_id, "hidden", actor_id=actor_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.post("/departments/{department_id}/unhide")
def unhide_department(
    department_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can unhide departments.")
    department = db.set_department_status(department_id, "active", actor_id=actor_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.delete("/departments/{department_id}")
def delete_department(
    department_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role != "ceo":
        raise HTTPException(status_code=403, detail="Only CEO can delete departments.")
    if db.count_active_store_assignments(department_id) > 0:
        raise HTTPException(status_code=409, detail="Department has active store assignments. Migrate or disable them first.")
    department = db.set_department_status(department_id, "deleted", actor_id=actor_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.post("/departments/{department_id}/restore")
def restore_department(
    department_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can restore departments.")
    department = db.set_department_status(department_id, "active", actor_id=actor_id)
    if not department:
        raise HTTPException(status_code=404, detail="Department not found.")
    return department


@app.get("/departments/{department_id}/permissions")
def get_department_permissions(department_id: str):
    return db.list_department_permissions(department_id)


@app.put("/departments/{department_id}/permissions")
def update_department_permissions(
    department_id: str,
    body: DepartmentPermissionUpdate,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can manage permissions.")
    return db.set_department_permissions(
        department_id,
        [item.model_dump() for item in body.permissions],
        actor_id=actor_id,
    )


@app.get("/stores/{store_id}/departments")
def get_store_departments(store_id: str, x_actor_role: str | None = Header(default=None)):
    _, actor_role = _actor_defaults(None, x_actor_role)
    if store_id not in STORE_REGISTRY:
        raise HTTPException(status_code=404, detail="Store not found.")
    return db.list_store_departments(store_id, actor_role=actor_role)


@app.put("/stores/{store_id}/departments")
def update_store_departments(
    store_id: str,
    body: StoreDepartmentBulkUpdate,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can assign departments to stores.")
    if store_id not in STORE_REGISTRY:
        raise HTTPException(status_code=404, detail="Store not found.")
    return db.upsert_store_departments(
        store_id,
        [item.model_dump() for item in body.departments],
        actor_id=actor_id,
    )


@app.get("/stores/{store_id}/departments/{department_id}/permissions")
def get_store_department_permissions(store_id: str, department_id: str):
    try:
        return db.get_store_department_permissions(store_id, department_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/stores/{store_id}/departments/{department_id}/permissions")
def update_store_department_permissions(
    store_id: str,
    department_id: str,
    body: StoreDepartmentPermissionUpdate,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can override store permissions.")
    try:
        return db.set_store_department_permissions(
            store_id,
            department_id,
            [item.model_dump() for item in body.permissions],
            actor_id=actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/policies")
def list_policies(scope_type: str | None = None, target_type: str | None = None, is_active: bool | None = None):
    return db.list_policies(scope_type=scope_type, target_type=target_type, is_active=is_active)


@app.post("/policies")
def create_policy(
    body: PolicyUpsert,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can create policies.")
    try:
        return db.create_policy(body.model_dump(), actor_id=actor_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail=f"Policy create failed: {exc}") from exc


@app.put("/policies/{policy_id}")
def update_policy(
    policy_id: str,
    body: PolicyUpsert,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can edit policies.")
    policy = db.update_policy(policy_id, body.model_dump(), actor_id=actor_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return policy


@app.post("/policies/{policy_id}/activate")
def activate_policy(policy_id: str, x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None)):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can activate policies.")
    policy = db.set_policy_active(policy_id, True, actor_id=actor_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return policy


@app.post("/policies/{policy_id}/deactivate")
def deactivate_policy(policy_id: str, x_actor_id: str | None = Header(default=None), x_actor_role: str | None = Header(default=None)):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can deactivate policies.")
    policy = db.set_policy_active(policy_id, False, actor_id=actor_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found.")
    return policy


@app.post("/policies/evaluate")
def evaluate_policy(body: GovernanceEvaluateRequest):
    return db.evaluate_governance_action(body.model_dump())


@app.post("/governance/actions/request")
def request_governed_action(body: GovernanceActionRequest):
    return db.request_governed_action(body.model_dump())


@app.get("/policies/{policy_id}/versions")
def list_policy_versions(policy_id: str):
    return db.list_policy_versions(policy_id)


@app.post("/policies/{policy_id}/versions/{version_id}/rollback")
def rollback_policy_version(
    policy_id: str,
    version_id: str,
    x_actor_id: str | None = Header(default=None),
    x_actor_role: str | None = Header(default=None),
):
    actor_id, actor_role = _actor_defaults(x_actor_id, x_actor_role)
    if actor_role not in {"ceo", "super_admin"}:
        raise HTTPException(status_code=403, detail="Only CEO or Super Admin can rollback policies.")
    policy = db.rollback_policy_version(policy_id, version_id, actor_id=actor_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy version not found.")
    return policy


@app.get("/policies/simulations")
def list_policy_simulations(limit: int = 50, policy_id: str | None = None):
    return db.list_policy_simulations(limit=limit, policy_id=policy_id)


@app.get("/audit-logs")
def list_audit_logs(store_id: str | None = None, department_id: str | None = None, resource_type: str | None = None, limit: int = 100):
    return db.list_audit_logs(store_id=store_id, department_id=department_id, resource_type=resource_type, limit=limit)


# ══════════════════════════════════════════════════════════════════════
# Projects — scans E:\Project\Master\ for real project data
# ══════════════════════════════════════════════════════════════════════

MASTER_DIR = Path(os.environ.get(
    "MASTER_PROJECT_DIR",
    Path(__file__).resolve().parents[3]
))

# Registry of known projects with metadata
PROJECT_REGISTRY = {
    "agentai-agency": {
        "name": "AgentAI Agency",
        "type": "python",
        "category": "core",
        "description": "AI Company OS — orchestrator, agents, control plane",
        "port": 8000,
        "tech": ["Python", "FastAPI", "LangGraph", "SQLite"],
        "github": "liemdo28/AgentAi-Angency",
    },
    "BakudanWebsite_Sub": {
        "name": "Bakudan Ramen Website",
        "type": "html",
        "category": "website",
        "description": "Official restaurant website — menu, locations, ordering",
        "relative_path": "BakudanWebsite_Sub",
        "port": None,
        "tech": ["HTML", "CSS", "JavaScript"],
        "github": "liemdo28/bakudanwebsite_sub",
    },
    "BakudanWebsite_Sub2": {
        "name": "Bakudan Ramen Website v2",
        "type": "html",
        "category": "website",
        "description": "Secondary iteration of restaurant website",
        "relative_path": "BakudanWebsite_Sub2",
        "port": None,
        "tech": ["HTML", "CSS", "JavaScript"],
        "github": "liemdo28/bakudanwebsite_sub2",
    },
    "RawWebsite": {
        "name": "Raw Sushi Bistro Website",
        "type": "html",
        "category": "website",
        "description": "Restaurant website — menu, blog, analytics",
        "relative_path": "RawWebsite",
        "port": None,
        "tech": ["HTML", "CSS", "JavaScript"],
        "github": "liemdo28/rawwebsite",
    },
    "dashboard.bakudanramen.com": {
        "name": "TaskFlow Dashboard",
        "type": "php",
        "category": "operations",
        "description": "Project management — tasks, calendar, notifications, PWA",
        "relative_path": "dashboard.bakudanramen.com",
        "port": None,
        "tech": ["PHP", "MySQL", "PWA"],
        "github": "liemdo28/dashboard.bakudanramen.com",
    },
    "growth-dashboard": {
        "name": "Growth Dashboard",
        "type": "node",
        "category": "analytics",
        "description": "Growth analytics dashboard on Cloudflare Pages",
        "relative_path": "growth-dashboard",
        "port": 8789,
        "tech": ["Node.js", "Wrangler", "Cloudflare Pages"],
        "github": "liemdo28/growth-dashboard",
    },
    "integration-full": {
        "name": "Toast POS Integration",
        "type": "python",
        "category": "operations",
        "description": "Desktop app — Toast POS to QuickBooks sync",
        "relative_path": "integration-full",
        "port": None,
        "tech": ["Python", "CustomTkinter", "Playwright"],
        "github": "liemdo28/intergration-full",
    },
    "review-dashboard": {
        "name": "ReviewOps Dashboard",
        "type": "node",
        "category": "reviews",
        "description": "Next.js frontend for review management system",
        "relative_path": "review/review-dashboard",
        "port": 3000,
        "tech": ["Next.js", "React", "Tailwind", "shadcn/ui"],
        "github": None,
    },
    "review-management-mcp": {
        "name": "Review MCP Server",
        "type": "node",
        "category": "reviews",
        "description": "MCP server for Yelp & Google review management",
        "relative_path": "review/review-management-mcp",
        "port": None,
        "tech": ["TypeScript", "MCP SDK", "Electron"],
        "github": "liemdo28/review-management-mcp",
    },
    "review-system": {
        "name": "Review Automation System",
        "type": "python",
        "category": "reviews",
        "description": "Auto-fetch reviews, AI reply generation, auto-post",
        "relative_path": "review/review-system",
        "port": 8000,
        "tech": ["FastAPI", "PostgreSQL", "Redis", "OpenAI"],
        "github": "liemdo28/review-automation-system",
    },
}

# Store registry (Bakudan Ramen locations)
STORE_REGISTRY = {
    "B1": {"name": "Bakudan Ramen - Alamo Ranch", "address": "12602 W Interstate 10, San Antonio, TX 78249", "brand": "bakudan"},
    "B2": {"name": "Bakudan Ramen - La Cantera", "address": "15900 La Cantera Pkwy, San Antonio, TX 78256", "brand": "bakudan"},
    "B3": {"name": "Bakudan Ramen - Stone Oak", "address": "22211 IH 10 W, San Antonio, TX 78256", "brand": "bakudan"},
    "RAW": {"name": "Raw Sushi Bistro - Stockton", "address": "5756 Pacific Ave, Stockton, CA 95207", "brand": "raw"},
    "COPPER": {"name": "Copper Bowl", "address": "TBD", "brand": "copper"},
    "IFT": {"name": "International Food Truck", "address": "Mobile", "brand": "ift"},
}


def _actor_defaults(x_actor_id: str | None, x_actor_role: str | None) -> tuple[str, str]:
    return (x_actor_id or "ceo"), (x_actor_role or "ceo").lower()


def _git_info(project_path: Path) -> dict:
    """Extract git branch, last commit, and status from a project."""
    info = {"branch": None, "last_commit": None, "last_commit_date": None, "dirty": False}
    git_dir = project_path / ".git"
    if not git_dir.exists():
        return info
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5
        )
        if branch.returncode == 0:
            info["branch"] = branch.stdout.strip()

        log = subprocess.run(
            ["git", "log", "-1", "--format=%s|||%ai"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5
        )
        if log.returncode == 0 and "|||" in log.stdout:
            parts = log.stdout.strip().split("|||")
            info["last_commit"] = parts[0]
            info["last_commit_date"] = parts[1]

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5
        )
        if status.returncode == 0:
            info["dirty"] = len(status.stdout.strip()) > 0
    except Exception:
        pass
    return info


def _detect_status(project_path: Path, port: int | None = None) -> str:
    """Detect if a project is healthy based on existence of key files."""
    if not project_path.exists():
        return "offline"
    # Check if service is running on its port
    if port:
        try:
            import urllib.request
            urllib.request.urlopen(f"http://localhost:{port}", timeout=1.5)
            return "running"
        except Exception:
            pass
    # Check for source files
    marker_files = [
        "package.json", "requirements.txt", "composer.json",
        "index.html", "app.py", "main.py", "pyproject.toml",
        "README.md", ".gitignore", "Makefile", "tsconfig.json",
        "index.php", "launch.bat", "setup.py",
    ]
    sub_markers = ["src/main.py", "app/main.py", "desktop-app/app.py"]
    if any((project_path / f).exists() for f in marker_files + sub_markers):
        return "idle"
    return "warning"


def _load_integration_snapshot(project_path: Path) -> dict | None:
    desktop_app_path = project_path / "desktop-app"
    module_path = desktop_app_path / "integration_status.py"
    if not module_path.exists():
        return None

    try:
        desktop_app_str = str(desktop_app_path)
        if desktop_app_str not in sys.path:
            sys.path.insert(0, desktop_app_str)
        module = importlib.import_module("integration_status")
        module = importlib.reload(module)
        return module.build_integration_snapshot(base_dir=desktop_app_path, include_today_for_suggestions=False, max_items=6)
    except Exception as exc:
        return {
            "error": str(exc),
            "summary": {
                "stores_tracked": 0,
                "download_rows": 0,
                "qb_sync_rows": 0,
                "last_download_at": None,
                "last_qb_sync_at": None,
                "download_gap_count": 0,
                "qb_gap_count": 0,
                "failed_qb_count": 0,
            },
            "latest_downloads": [],
            "latest_qb_sync": [],
            "latest_qb_attempts": [],
            "ai_suggestions": [],
            "world_clocks": [],
        }


def _require_edge_token(x_agentai_token: str | None) -> None:
    expected = os.environ.get("AGENTAI_EDGE_TOKEN", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="AGENTAI_EDGE_TOKEN is not configured on AgentAI.",
        )
    if x_agentai_token != expected:
        raise HTTPException(status_code=401, detail="Invalid edge token.")


def _project_snapshot_nodes(project_id: str) -> list[dict]:
    machines = db.list_edge_machines(project_id)
    snapshots = {item.get("machine_id"): item for item in db.list_project_snapshots(project_id)}
    now = datetime.now(timezone.utc)
    nodes = []
    for machine in machines:
        snapshot = snapshots.get(machine.get("machine_id"), {})
        snapshot_payload = snapshot.get("snapshot") or {}
        last_seen_raw = machine.get("last_seen_at") or snapshot.get("received_at")
        last_seen_dt = None
        if last_seen_raw:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen_raw.replace("Z", "+00:00"))
            except ValueError:
                last_seen_dt = None
        is_online = bool(last_seen_dt and (now - last_seen_dt).total_seconds() <= 180)
        nodes.append(
            {
                "machine_id": machine.get("machine_id"),
                "machine_name": machine.get("machine_name"),
                "source_type": machine.get("source_type") or snapshot.get("source_type"),
                "app_version": machine.get("app_version") or snapshot.get("app_version"),
                "received_at": snapshot.get("received_at"),
                "last_seen_at": last_seen_raw,
                "online": is_online,
                "paused": bool(machine.get("paused")),
                "draining": bool(machine.get("draining")),
                "pause_reason": machine.get("pause_reason") or "",
                "last_snapshot_at": machine.get("last_snapshot_at"),
                "last_command_at": machine.get("last_command_at"),
                "generated_at": snapshot_payload.get("generated_at"),
                "runtime": snapshot_payload.get("runtime") or {},
                "summary": snapshot.get("summary") or {},
            }
        )
    return nodes


def _resolve_integration_snapshot(project_path: Path) -> dict | None:
    remote = db.get_latest_project_snapshot("integration-full")
    if remote:
        snapshot = deepcopy(remote.get("snapshot") or {})
        snapshot["source_mode"] = "remote"
        snapshot["source_project_id"] = "integration-full"
        snapshot["source_type"] = remote.get("source_type") or "integration-full"
        snapshot["source_machine_id"] = remote.get("machine_id")
        snapshot["source_machine_name"] = remote.get("machine_name")
        snapshot["source_app_version"] = remote.get("app_version") or ""
        snapshot["source_received_at"] = remote.get("received_at")
        snapshot["remote_nodes"] = _project_snapshot_nodes("integration-full")
        snapshot["recent_commands"] = db.list_edge_commands(project_id="integration-full", limit=8)
        return snapshot

    local_snapshot = _load_integration_snapshot(project_path)
    if local_snapshot is not None:
        local_snapshot = deepcopy(local_snapshot)
        local_snapshot["source_mode"] = "local"
        local_snapshot["source_project_id"] = "integration-full"
        local_snapshot["source_type"] = "integration-full"
        local_snapshot["source_machine_id"] = None
        local_snapshot["source_machine_name"] = "Local workspace"
        local_snapshot["source_app_version"] = ""
        local_snapshot["source_received_at"] = local_snapshot.get("generated_at")
        local_snapshot["remote_nodes"] = []
        local_snapshot["recent_commands"] = db.list_edge_commands(project_id="integration-full", limit=8)
    return local_snapshot


def _resolve_project_path(project_id: str, meta: dict) -> Path:
    return MASTER_DIR / Path(meta.get("relative_path") or project_id)


@app.post("/edge/projects/{project_id}/snapshot")
def upsert_edge_project_snapshot(
    project_id: str,
    body: EdgeProjectSnapshotUpsert,
    x_agentai_token: str | None = Header(default=None),
):
    _require_edge_token(x_agentai_token)
    snapshot = body.snapshot or {}
    if not isinstance(snapshot, dict) or not snapshot:
        raise HTTPException(status_code=400, detail="Snapshot payload must be a non-empty object.")
    result = db.upsert_project_snapshot(
        project_id=project_id,
        machine_id=body.machine_id,
        machine_name=body.machine_name,
        source_type=body.source_type,
        app_version=body.app_version,
        snapshot=snapshot,
    )
    return {"status": "ok", **result}


@app.get("/edge/projects/{project_id}/snapshots")
def list_edge_project_snapshots(
    project_id: str,
    x_agentai_token: str | None = Header(default=None),
):
    _require_edge_token(x_agentai_token)
    snapshots = db.list_project_snapshots(project_id)
    return [
        {
            "project_id": item.get("project_id"),
            "machine_id": item.get("machine_id"),
            "machine_name": item.get("machine_name"),
            "source_type": item.get("source_type"),
            "app_version": item.get("app_version"),
            "received_at": item.get("received_at"),
            "summary": item.get("summary") or {},
        }
        for item in snapshots
    ]


@app.get("/edge/projects/{project_id}/commands/{machine_id}")
def dispatch_edge_project_command(
    project_id: str,
    machine_id: str,
    x_agentai_token: str | None = Header(default=None),
):
    _require_edge_token(x_agentai_token)
    command = db.dispatch_next_edge_command(project_id=project_id, machine_id=machine_id)
    return {"command": command}


@app.post("/edge/commands/{command_id}/ack")
def acknowledge_edge_project_command(
    command_id: str,
    body: EdgeCommandLeaseUpdate,
    x_agentai_token: str | None = Header(default=None),
):
    _require_edge_token(x_agentai_token)
    command = db.acknowledge_edge_command(command_id=command_id, heartbeat_seconds=body.heartbeat_seconds)
    if not command:
        raise HTTPException(status_code=404, detail="Command not found.")
    return {"status": "ok", "command": command}


@app.post("/edge/commands/{command_id}/heartbeat")
def heartbeat_edge_project_command(
    command_id: str,
    body: EdgeCommandLeaseUpdate,
    x_agentai_token: str | None = Header(default=None),
):
    _require_edge_token(x_agentai_token)
    command = db.heartbeat_edge_command(command_id=command_id, heartbeat_seconds=body.heartbeat_seconds)
    if not command:
        raise HTTPException(status_code=404, detail="Command not found.")
    return {"status": "ok", "command": command}


@app.post("/edge/commands/{command_id}/result")
def resolve_edge_project_command(
    command_id: str,
    body: EdgeCommandResolve,
    x_agentai_token: str | None = Header(default=None),
):
    _require_edge_token(x_agentai_token)
    if body.status not in {"success", "failed", "cancelled"}:
        raise HTTPException(status_code=400, detail="Unsupported command status.")
    command = db.complete_edge_command(
        command_id=command_id,
        status=body.status,
        result=body.result,
        error_message=body.error_message,
    )
    if not command:
        raise HTTPException(status_code=404, detail="Command not found.")
    return {"status": "ok", "command": command}


@app.post("/projects/{project_id}/commands")
def create_project_command(project_id: str, body: ProjectCommandCreate):
    if project_id != "integration-full":
        raise HTTPException(status_code=400, detail="Project command queue is only enabled for integration-full right now.")
    command = db.create_edge_command(
        project_id=project_id,
        machine_id=body.machine_id,
        machine_name=body.machine_name,
        command_type=body.command_type,
        payload=body.payload,
        title=body.title,
        created_by=body.created_by,
        source_suggestion_id=body.source_suggestion_id,
        max_attempts=body.max_attempts,
    )
    return command


@app.get("/projects/{project_id}/commands")
def list_project_commands(project_id: str, machine_id: str | None = None, limit: int = 20):
    return db.list_edge_commands(project_id=project_id, machine_id=machine_id, limit=limit)


@app.get("/projects/{project_id}/machines")
def list_project_machines(project_id: str):
    return _project_snapshot_nodes(project_id)


@app.post("/projects/{project_id}/machines/{machine_id}/control")
def update_project_machine_control(project_id: str, machine_id: str, body: EdgeMachineControlUpdate):
    machine = db.set_edge_machine_control(
        project_id=project_id,
        machine_id=machine_id,
        paused=body.paused,
        draining=body.draining,
        pause_reason=body.pause_reason,
    )
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found.")
    cancelled = 0
    if body.cancel_pending:
        cancelled = db.cancel_pending_edge_commands(project_id=project_id, machine_id=machine_id)
    return {"machine": machine, "cancelled_pending": cancelled}


@app.get("/projects")
def list_projects():
    """List all projects from the Master directory with live git info."""
    projects = []
    for dir_name, meta in PROJECT_REGISTRY.items():
        project_path = _resolve_project_path(dir_name, meta)
        git = _git_info(project_path)
        status = _detect_status(project_path, meta.get("port"))
        integration_ops = _resolve_integration_snapshot(project_path) if dir_name == "integration-full" else None
        ops_profile = build_project_ops_profile(dir_name, project_path, meta, status)

        projects.append({
            "id": dir_name,
            "name": meta["name"],
            "type": meta["type"],
            "category": meta["category"],
            "description": meta["description"],
            "port": meta["port"],
            "tech": meta["tech"],
            "github": meta["github"],
            "status": status,
            "exists": project_path.exists(),
            "branch": git["branch"],
            "last_commit": git["last_commit"],
            "last_commit_date": git["last_commit_date"],
            "dirty": git["dirty"],
            "local_path": str(project_path),
            "integration_ops": integration_ops,
            "ops_profile": ops_profile,
        })
    return projects


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """Get detailed project info."""
    meta = PROJECT_REGISTRY.get(project_id)
    if not meta:
        raise HTTPException(404, "Project not found")

    project_path = _resolve_project_path(project_id, meta)
    git = _git_info(project_path)
    status = _detect_status(project_path, meta.get("port"))
    integration_ops = _resolve_integration_snapshot(project_path) if project_id == "integration-full" else None
    ops_profile = build_project_ops_profile(project_id, project_path, meta, status)

    # Count files
    file_count = 0
    if project_path.exists():
        for f in project_path.rglob("*"):
            if f.is_file() and ".git" not in f.parts and "node_modules" not in f.parts:
                file_count += 1

    return {
        "id": project_id,
        **meta,
        "status": status,
        "exists": project_path.exists(),
        "path": str(project_path),
        "file_count": file_count,
        "integration_ops": integration_ops,
        "ops_profile": ops_profile,
        **git,
    }


@app.get("/agents/roles")
def list_agent_roles():
    from core.agents.roles import ROLE_DEFINITIONS
    return ROLE_DEFINITIONS


@app.get("/stores")
def list_stores():
    """List all store locations."""
    return [{"id": sid, **sdata} for sid, sdata in STORE_REGISTRY.items()]


@app.get("/stores/{store_id}")
def get_store(store_id: str):
    """Get store details."""
    store = STORE_REGISTRY.get(store_id)
    if not store:
        raise HTTPException(404, "Store not found")
    return {"id": store_id, **store}
