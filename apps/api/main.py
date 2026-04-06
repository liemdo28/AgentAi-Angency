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

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
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


# ══════════════════════════════════════════════════════════════════════
# Projects — scans E:\Project\Master\ for real project data
# ══════════════════════════════════════════════════════════════════════

MASTER_DIR = Path(os.environ.get(
    "MASTER_PROJECT_DIR",
    Path(__file__).resolve().parent.parent.parent.parent / "Master"
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


@app.get("/projects")
def list_projects():
    """List all projects from the Master directory with live git info."""
    projects = []
    for dir_name, meta in PROJECT_REGISTRY.items():
        project_path = MASTER_DIR / dir_name
        git = _git_info(project_path)
        status = _detect_status(project_path, meta.get("port"))

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
