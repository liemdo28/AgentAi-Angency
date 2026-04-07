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
        "port": None,
        "tech": ["HTML", "CSS", "JavaScript"],
        "github": "liemdo28/bakudanwebsite_sub",
    },
    "BakudanWebsite_Sub2": {
        "name": "Bakudan Ramen Website v2",
        "type": "html",
        "category": "website",
        "description": "Secondary iteration of restaurant website",
        "port": None,
        "tech": ["HTML", "CSS", "JavaScript"],
        "github": "liemdo28/bakudanwebsite_sub2",
    },
    "RawWebsite": {
        "name": "Raw Sushi Bistro Website",
        "type": "html",
        "category": "website",
        "description": "Restaurant website — menu, blog, analytics",
        "port": None,
        "tech": ["HTML", "CSS", "JavaScript"],
        "github": "liemdo28/rawwebsite",
    },
    "dashboard.bakudanramen.com": {
        "name": "TaskFlow Dashboard",
        "type": "php",
        "category": "operations",
        "description": "Project management — tasks, calendar, notifications, PWA",
        "port": None,
        "tech": ["PHP", "MySQL", "PWA"],
        "github": "liemdo28/dashboard.bakudanramen.com",
    },
    "growth-dashboard": {
        "name": "Growth Dashboard",
        "type": "node",
        "category": "analytics",
        "description": "Growth analytics dashboard on Cloudflare Pages",
        "port": 8789,
        "tech": ["Node.js", "Wrangler", "Cloudflare Pages"],
        "github": "liemdo28/growth-dashboard",
    },
    "integration-full": {
        "name": "Toast POS Integration",
        "type": "python",
        "category": "operations",
        "description": "Desktop app — Toast POS to QuickBooks sync",
        "port": None,
        "tech": ["Python", "CustomTkinter", "Playwright"],
        "github": "liemdo28/intergration-full",
    },
    "review-dashboard": {
        "name": "ReviewOps Dashboard",
        "type": "node",
        "category": "reviews",
        "description": "Next.js frontend for review management system",
        "port": 3000,
        "tech": ["Next.js", "React", "Tailwind", "shadcn/ui"],
        "github": None,
    },
    "review-management-mcp": {
        "name": "Review MCP Server",
        "type": "node",
        "category": "reviews",
        "description": "MCP server for Yelp & Google review management",
        "port": None,
        "tech": ["TypeScript", "MCP SDK", "Electron"],
        "github": "liemdo28/review-management-mcp",
    },
    "review-system": {
        "name": "Review Automation System",
        "type": "python",
        "category": "reviews",
        "description": "Auto-fetch reviews, AI reply generation, auto-post",
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
    snapshots = db.list_project_snapshots(project_id)
    nodes = []
    for item in snapshots:
        nodes.append(
            {
                "machine_id": item.get("machine_id"),
                "machine_name": item.get("machine_name"),
                "source_type": item.get("source_type"),
                "app_version": item.get("app_version"),
                "received_at": item.get("received_at"),
                "summary": item.get("summary") or {},
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
    return local_snapshot


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


@app.get("/projects")
def list_projects():
    """List all projects from the Master directory with live git info."""
    projects = []
    for dir_name, meta in PROJECT_REGISTRY.items():
        project_path = MASTER_DIR / dir_name
        git = _git_info(project_path)
        status = _detect_status(project_path, meta.get("port"))
        integration_ops = _resolve_integration_snapshot(project_path) if dir_name == "integration-full" else None

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
        })
    return projects


@app.get("/projects/{project_id}")
def get_project(project_id: str):
    """Get detailed project info."""
    meta = PROJECT_REGISTRY.get(project_id)
    if not meta:
        raise HTTPException(404, "Project not found")

    project_path = MASTER_DIR / project_id
    git = _git_info(project_path)
    status = _detect_status(project_path, meta.get("port"))
    integration_ops = _resolve_integration_snapshot(project_path) if project_id == "integration-full" else None

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
