"""
Unified Dashboard API - Central data hub for all projects.

This API aggregates data from all projects and provides
a single endpoint for the Agency Dashboard.

Run:
    PYTHONPATH=.:src uvicorn src.unified.api:app --reload --port 8001
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import asyncio
import logging
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.unified.models import (
    ALL_PROJECTS,
    ALL_STORES,
    Alert,
    DashboardOverview,
    Project,
    ProjectHealth,
    ProjectStatus,
    Store,
)

logger = logging.getLogger(__name__)

# ============================================
# App Setup
# ============================================

app = FastAPI(
    title="Agency Unified Dashboard API",
    description="Central data hub for all agency projects and stores",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# External API Configurations
# ============================================

EXTERNAL_APIS = {
    "agency": {
        "base_url": "http://localhost:8000",
        "endpoints": {
            "status": "/status",
            "tasks": "/tasks",
            "handoffs": "/handoffs",
        },
        "timeout": 5.0,
    },
    "taskflow": {
        "base_url": "https://dashboard.bakudanramen.com",
        "endpoint": "/api/stats",
        "timeout": 10.0,
    },
}

# ============================================
# Data Cache (in-memory, refreshes on request)
# ============================================

_cache: dict[str, Any] = {
    "last_refresh": None,
    "projects": {},
    "stores": {},
    "overview": None,
}


# ============================================
# Pydantic Response Models
# ============================================


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    projects_checked: int
    stores_checked: int
    errors: list[str]


class ProjectStatusResponse(BaseModel):
    id: str
    name: str
    status: str
    last_check: Optional[str]
    metrics: dict


class StoreStatusResponse(BaseModel):
    id: str
    name: str
    status: str
    store_type: str
    metrics: dict


class RefreshResponse(BaseModel):
    ok: bool
    refreshed_at: str
    projects_updated: int
    stores_updated: int


# ============================================
# Helper Functions
# ============================================


async def fetch_with_timeout(url: str, timeout: float = 5.0) -> Optional[dict]:
    """Fetch JSON from URL with timeout."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
    return None


async def check_agency_status() -> dict:
    """Check status of the Agency API."""
    base_url = EXTERNAL_APIS["agency"]["base_url"]
    result = {
        "status": ProjectStatus.OFFLINE,
        "metrics": {},
    }

    try:
        data = await fetch_with_timeout(f"{base_url}/status", timeout=3.0)
        if data:
            result["status"] = ProjectStatus.ONLINE
            result["metrics"] = {
                "total_tasks": data.get("total", 0),
                "active_tasks": data.get("active", 0),
                "passed_tasks": data.get("passed", 0),
                "pending_handoffs": data.get("pending", 0),
                "avg_score": data.get("avg_score", 0),
                "pass_rate": data.get("pass_rate", 0),
            }
    except Exception as e:
        result["error"] = str(e)

    return result


async def check_taskflow() -> dict:
    """Check status of TaskFlow dashboard."""
    base_url = EXTERNAL_APIS["taskflow"]["base_url"]
    endpoint = EXTERNAL_APIS["taskflow"]["endpoint"]
    result = {
        "status": ProjectStatus.UNKNOWN,
        "metrics": {},
    }

    try:
        data = await fetch_with_timeout(f"{base_url}{endpoint}", timeout=5.0)
        if data:
            result["status"] = ProjectStatus.ONLINE
            result["metrics"] = data
    except Exception:
        # Site might be up but API might not respond
        result["status"] = ProjectStatus.WARNING

    return result


async def check_integration() -> dict:
    """Check status of Toast-QB integration."""
    result = {
        "status": ProjectStatus.UNKNOWN,
        "metrics": {},
    }

    # This would typically check QB logs or API
    # For now, return needs verification
    result["metrics"] = {
        "last_sync": None,
        "orders_synced": 0,
        "errors": 0,
        "status": "needs_verification",
    }

    return result


async def check_review_mcp() -> dict:
    """Check status of Review MCP."""
    result = {
        "status": ProjectStatus.UNKNOWN,
        "metrics": {},
    }

    result["metrics"] = {
        "google_reviews": 0,
        "yelp_reviews": 0,
        "responses_sent": 0,
        "last_checked": None,
    }

    return result


def _scan_local_project(project_id: str) -> dict:
    """Check if a local project directory exists and has source files."""
    import subprocess as _sp
    # api.py → src/unified/ → src/ → agentai-agency/ → E:\Project\Master
    master_dir = Path(__file__).resolve().parent.parent.parent.parent
    # Map IDs to actual folder names
    folder_map = {
        "dashboard-taskflow": "dashboard.bakudanramen.com",
        "review-management": "review-management-mcp",
        "marketing": None,  # remote-only
    }
    folder = folder_map.get(project_id, project_id)
    if folder is None:
        return {"status": ProjectStatus.UNKNOWN, "metrics": {}}

    project_path = master_dir / folder
    if not project_path.exists():
        return {"status": ProjectStatus.OFFLINE, "metrics": {}}

    # Detect status by checking for key files
    markers = [
        "package.json", "requirements.txt", "composer.json", "index.html",
        "app.py", "main.py", "pyproject.toml", "README.md", "tsconfig.json",
        "index.php", "launch.bat", "src/main.py", "app/main.py",
    ]
    has_source = any((project_path / m).exists() for m in markers)

    # Get git info
    branch = None
    last_commit = None
    try:
        r = _sp.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                     cwd=str(project_path), capture_output=True, text=True, timeout=3)
        if r.returncode == 0:
            branch = r.stdout.strip()
        r2 = _sp.run(["git", "log", "-1", "--format=%s"],
                      cwd=str(project_path), capture_output=True, text=True, timeout=3)
        if r2.returncode == 0:
            last_commit = r2.stdout.strip()
    except Exception:
        pass

    return {
        "status": ProjectStatus.ONLINE if has_source else ProjectStatus.WARNING,
        "metrics": {
            "branch": branch,
            "last_commit": last_commit,
            "has_source": has_source,
        },
    }


async def refresh_all_data() -> dict:
    """Refresh all project and store data — combines HTTP checks + local scan."""
    global _cache

    now = datetime.now(timezone.utc)

    # 1) HTTP checks for remote services (in parallel)
    results = await asyncio.gather(
        check_agency_status(),
        check_taskflow(),
        check_integration(),
        check_review_mcp(),
        return_exceptions=True,
    )

    http_statuses = {
        "agentai-agency": results[0] if not isinstance(results[0], Exception) else {},
        "dashboard-taskflow": results[1] if not isinstance(results[1], Exception) else {},
        "integration-full": results[2] if not isinstance(results[2], Exception) else {},
        "review-management": results[3] if not isinstance(results[3], Exception) else {},
    }

    # 2) Local directory scan for ALL projects
    project_statuses = {}
    for project_id in ALL_PROJECTS:
        # Prefer HTTP check if available and online
        http_data = http_statuses.get(project_id, {})
        if http_data.get("status") == ProjectStatus.ONLINE:
            project_statuses[project_id] = http_data
        else:
            # Fall back to local scan
            local = _scan_local_project(project_id)
            # Merge HTTP metrics if any
            if http_data.get("metrics"):
                local.setdefault("metrics", {}).update(http_data["metrics"])
            project_statuses[project_id] = local

    # 3) Get pending task count from Control Plane DB (if available)
    try:
        from db.repository import ControlPlaneDB
        cp_db = ControlPlaneDB()
        cp_stats = cp_db.get_dashboard_stats()
        _cache["cp_stats"] = cp_stats
    except Exception:
        _cache["cp_stats"] = None

    # Update cache
    _cache["last_refresh"] = now
    _cache["projects"] = project_statuses

    return {
        "refreshed_at": now.isoformat(),
        "projects_updated": len(project_statuses),
    }


def build_overview() -> DashboardOverview:
    """Build the complete dashboard overview from ALL projects."""
    global _cache

    now = datetime.now(timezone.utc)

    # Count statuses from cache
    projects_data = _cache.get("projects", {})
    active_projects = sum(
        1 for p in projects_data.values()
        if p.get("status") == ProjectStatus.ONLINE
    )

    # Stores — all are considered online (local businesses)
    online_stores = len(ALL_STORES)

    # Task counts from Control Plane DB
    cp_stats = _cache.get("cp_stats") or {}
    pending_tasks = cp_stats.get("tasks", {}).get("pending", 0)
    total_tasks = sum(cp_stats.get("tasks", {}).values()) if cp_stats.get("tasks") else 0

    # Build alerts
    alerts = []
    for project_id, data in projects_data.items():
        if data.get("status") == ProjectStatus.OFFLINE:
            alerts.append(Alert(
                id=f"alert-{project_id}-offline",
                severity="error",
                title=f"{project_id} is offline",
                description=f"Cannot connect to {project_id}. Check if the service is running.",
                project_id=project_id,
                timestamp=now,
            ))
        elif data.get("status") == ProjectStatus.WARNING:
            alerts.append(Alert(
                id=f"alert-{project_id}-warning",
                severity="warning",
                title=f"{project_id} has warnings",
                description=f"Some metrics may be outdated or unavailable.",
                project_id=project_id,
                timestamp=now,
            ))

    # Build project list from ALL_PROJECTS, enriched with live status
    project_list = []
    for pid, proj in ALL_PROJECTS.items():
        live = projects_data.get(pid, {})
        project_list.append(Project(
            id=pid,
            name=proj.name,
            description=proj.description,
            status=live.get("status", ProjectStatus.UNKNOWN),
            metrics=live.get("metrics", {}),
            store_ids=proj.store_ids,
        ))

    return DashboardOverview(
        timestamp=now,
        total_projects=len(ALL_PROJECTS),
        active_projects=active_projects,
        total_stores=len(ALL_STORES),
        online_stores=online_stores,
        total_revenue_7d=0.0,
        total_tasks=total_tasks,
        pending_tasks=pending_tasks,
        projects=project_list,
        stores=list(ALL_STORES.values()),
        alerts=alerts,
    )


# ============================================
# API Endpoints
# ============================================


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "name": "Agency Unified Dashboard API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Health check endpoint."""
    global _cache

    errors = []
    projects_checked = 0

    for project_id, data in _cache.get("projects", {}).items():
        projects_checked += 1
        if data.get("status") == ProjectStatus.OFFLINE:
            errors.append(f"{project_id} is offline")

    return HealthResponse(
        status="healthy" if not errors else "degraded",
        timestamp=datetime.now(timezone.utc).isoformat(),
        projects_checked=projects_checked,
        stores_checked=len(ALL_STORES),
        errors=errors,
    )


@app.post("/refresh", response_model=RefreshResponse, tags=["Data"])
async def refresh():
    """Force refresh all data from external sources."""
    result = await refresh_all_data()
    return RefreshResponse(
        ok=True,
        refreshed_at=result["refreshed_at"],
        projects_updated=result["projects_updated"],
        stores_updated=len(ALL_STORES),
    )


@app.get("/overview", response_model=DashboardOverview, tags=["Dashboard"])
async def overview():
    """
    Get complete dashboard overview.

    This endpoint returns:
    - All projects with their current status and metrics
    - All stores with their current status and metrics
    - Summary statistics
    - Active alerts
    """
    global _cache

    # Auto-refresh if cache is old (> 30 seconds)
    last_refresh = _cache.get("last_refresh")
    if not last_refresh:
        await refresh_all_data()
    else:
        age = (datetime.now(timezone.utc) - last_refresh).total_seconds()
        if age > 30:
            asyncio.create_task(refresh_all_data())

    return build_overview()


@app.get("/projects", tags=["Projects"])
async def list_projects():
    """List all projects with their status."""
    global _cache

    projects_data = _cache.get("projects", {})

    # Always return ALL_PROJECTS, enrich with live status from cache
    result = []
    for project_id, project in ALL_PROJECTS.items():
        live = projects_data.get(project_id, {})
        result.append({
            "id": project_id,
            "name": project.name,
            "description": project.description,
            "status": live.get("status", "unknown"),
            "metrics": live.get("metrics", {}),
            "store_ids": project.store_ids,
        })

    return result


@app.get("/projects/{project_id}", response_model=Project, tags=["Projects"])
async def get_project(project_id: str):
    """Get details for a specific project."""
    if project_id not in ALL_PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")

    project = ALL_PROJECTS[project_id]
    project_data = _cache.get("projects", {}).get(project_id, {})

    return Project(
        id=project.id,
        name=project.name if hasattr(project, 'name') else project_id,
        description=project.description if hasattr(project, 'description') else "",
        status=project_data.get("status", ProjectStatus.UNKNOWN),
        metrics=project_data.get("metrics", {}),
    )


@app.get("/stores", tags=["Stores"])
async def list_stores():
    """List all stores."""
    return {
        store_id: {
            "name": store.name,
            "store_type": store.store_type.value,
            "location": store.location.value,
            "city": store.city,
            "state": store.state,
            "status": store.status.value,
        }
        for store_id, store in ALL_STORES.items()
    }


@app.get("/stores/{store_id}", response_model=Store, tags=["Stores"])
async def get_store(store_id: str):
    """Get details for a specific store."""
    if store_id not in ALL_STORES:
        raise HTTPException(status_code=404, detail="Store not found")

    return ALL_STORES[store_id]


@app.get("/stores/{store_id}/metrics", tags=["Stores"])
async def get_store_metrics(store_id: str):
    """Get metrics for a specific store."""
    if store_id not in ALL_STORES:
        raise HTTPException(status_code=404, detail="Store not found")

    # In production, this would aggregate from multiple sources
    return {
        "store_id": store_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "revenue": 0,
            "orders": 0,
            "roas": 0,
            "reviews": 0,
        },
    }


@app.get("/alerts", tags=["Alerts"])
async def list_alerts(severity: Optional[str] = Query(None)):
    """List all active alerts."""
    overview = build_overview()

    alerts = overview.alerts
    if severity:
        alerts = [a for a in alerts if a.severity == severity]

    return {
        "count": len(alerts),
        "alerts": [a.model_dump() for a in alerts],
    }


# ============================================
# Job Queue Endpoints
# ============================================

from src.unified.jobs import JobRunner, JobStatus, JobCreateRequest
from src.unified.settings import get_settings
from fastapi import UploadFile, File, Form

# Global job runner instance
_job_runner: Optional[JobRunner] = None


def get_job_runner() -> JobRunner:
    global _job_runner
    if _job_runner is None:
        _job_runner = JobRunner()
    return _job_runner


@app.post("/jobs", tags=["Jobs"])
async def create_job(body: JobCreateRequest):
    """
    Create a new job and add it to the queue.
    The job will be executed asynchronously.
    """
    runner = get_job_runner()

    # Validate project has a connector
    from src.unified.connectors import get_connector
    connector = get_connector(body.project_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"No connector for project: {body.project_id}")

    job, log = runner.create(
        project_id=body.project_id,
        action_id=body.action_id,
        payload=body.payload,
        priority=body.priority,
        requested_by=body.requested_by,
        description=body.description,
    )

    # Trigger async execution
    asyncio.create_task(runner.run(job.id))

    return {
        "job": job.to_dict(),
        "log": log.to_dict(),
    }


# ── Action Registry ─────────────────────────────────────────────────────────────
# Defines which actions require a file upload.

ACTION_REGISTRY: dict[str, dict] = {
    "marketing": {
        "marketing.upload": {"requires_file": True},
        "marketing.sync_campaigns": {"requires_file": False},
        "marketing.health": {"requires_file": False},
        "marketing.campaign_stats": {"requires_file": False},
        "marketing.pull_report": {"requires_file": False},
        "marketing.list_assets": {"requires_file": False},
        "marketing.branch_state": {"requires_file": False},
        "marketing.analytics": {"requires_file": False},
    },
    "dashboard-taskflow": {
        "taskflow.create_task": {"requires_file": False},
        "taskflow.fetch_stats": {"requires_file": False},
        "taskflow.sync_team": {"requires_file": False},
    },
    "review-management": {
        "reviews.refresh": {"requires_file": False},
        "reviews.list_pending": {"requires_file": False},
        "reviews.responses": {"requires_file": False},
    },
    "integration-full": {
        "integration.sync": {"requires_file": False},
        "integration.verify": {"requires_file": False},
        "integration.export": {"requires_file": False},
        "integration.sync_store": {"requires_file": False},
        "integration.retry_errors": {"requires_file": False},
        # Toast Report Ingestion
        "integration.ingest_file": {"requires_file": True},
        "integration.ingest_folder": {"requires_file": False},
        "integration.gdrive_poll": {"requires_file": False},
        "integration.coverage": {"requires_file": False},
        "integration.upload_status": {"requires_file": False},
    },
    "agentai-agency": {
        "agency.refresh": {"requires_file": False},
        "agency.tasks": {"requires_file": False},
        "agency.handoffs": {"requires_file": False},
    },
}


def action_requires_file(project_id: str, action_id: str) -> bool:
    """Check if an action requires file upload."""
    project_actions = ACTION_REGISTRY.get(project_id, {})
    return project_actions.get(action_id, {}).get("requires_file", False)


# ── File Upload + Action Endpoint ──────────────────────────────────────────────

@app.post("/projects/{project_id}/actions/{action_id}", tags=["Projects"])
async def execute_project_action(
    project_id: str,
    action_id: str,
    file: UploadFile | None = File(default=None),
    meta: str | None = Form(default=None),
):
    """
    Execute an action on a project.
    Supports multipart file upload — the file is saved to data/uploads/
    and its path is included in the job payload.

    Use file=... to attach a file (csv, xlsx, json, etc.)
    Use meta=JSON string for additional action metadata.
    """
    from src.unified.connectors import get_connector
    import json as _json

    # Validate project
    connector = get_connector(project_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"No connector for project: {project_id}")

    # Validate action is registered
    if action_id not in ACTION_REGISTRY.get(project_id, {}):
        raise HTTPException(
            status_code=404,
            detail=f"Action '{action_id}' not found for project '{project_id}'",
        )
    if action_requires_file(project_id, action_id) and file is None:
        raise HTTPException(
            status_code=422,
            detail=f"Action '{action_id}' requires a file upload",
        )

    # Save uploaded file if present
    saved_path = None
    original_name = None

    if file:
        settings = get_settings()
        ok, err = settings.validate_upload(file.filename or "", 0)
        if not ok:
            raise HTTPException(status_code=400, detail=err)

        # Read content to check size
        content = await file.read()
        size = len(content)
        ok, err = settings.validate_upload(file.filename or "", size)
        if not ok:
            raise HTTPException(status_code=400, detail=err)

        original_name = file.filename
        ext = Path(original_name).suffix.lower()
        import uuid as _uuid
        stored_name = f"{_uuid.uuid4().hex}{ext}"
        saved_path = settings.upload_dir / stored_name

        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        saved_path.write_bytes(content)
        logger.info("File uploaded: %s → %s (%.1f KB)", original_name, saved_path, size / 1024)

    # Parse meta if provided
    meta_data = None
    if meta:
        try:
            meta_data = _json.loads(meta)
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid meta JSON: {meta}")

    # Build job payload
    payload: dict[str, Any] = {}
    if saved_path:
        payload["file_path"] = str(saved_path)
        payload["original_name"] = original_name
    if meta_data:
        payload["meta"] = meta_data

    # Create and trigger job
    runner = get_job_runner()
    job, _ = runner.create(
        project_id=project_id,
        action_id=action_id,
        payload=payload,
        requested_by="api",
    )

    asyncio.create_task(runner.run(job.id))

    return {
        "job_id": job.id,
        "status": job.status.value,
        "requires_file": action_requires_file(project_id, action_id),
        "file_uploaded": original_name,
        "message": f"Action '{action_id}' queued for project '{project_id}'",
    }


@app.get("/jobs", tags=["Jobs"])
async def list_jobs(
    project_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
):
    """List jobs with optional filters."""
    runner = get_job_runner()
    job_status = JobStatus(status) if status else None
    jobs = runner.list_jobs(project_id=project_id, status=job_status, limit=limit, offset=offset)

    return {
        "count": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
        "filters": {"project_id": project_id, "status": status},
        "pagination": {"limit": limit, "offset": offset},
    }


@app.get("/jobs/summary", tags=["Jobs"])
async def job_summary():
    """Get job statistics summary."""
    from src.unified.jobs import JobDB
    db = JobDB.get_instance()
    counts = db.count_jobs()

    # Get today's jobs
    today = datetime.now().strftime("%Y-%m-%d")
    runner = get_job_runner()
    today_jobs = [
        j for j in runner.list_jobs(limit=1000)
        if j.requested_at.strftime("%Y-%m-%d") == today
    ]

    return {
        "total": sum(counts.values()),
        "by_status": counts,
        "today": {
            "total": len(today_jobs),
            "success": len([j for j in today_jobs if j.status == JobStatus.SUCCESS]),
            "failed": len([j for j in today_jobs if j.status == JobStatus.FAILED]),
            "pending": len([j for j in today_jobs if j.status == JobStatus.PENDING]),
            "running": len([j for j in today_jobs if j.status == JobStatus.RUNNING]),
        },
    }


@app.get("/jobs/{job_id}", tags=["Jobs"])
async def get_job(job_id: str):
    """Get a specific job by ID."""
    runner = get_job_runner()
    job = runner.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    logs = runner.get_logs(job_id)
    return {
        "job": job.to_dict(),
        "logs": logs,
    }


@app.post("/jobs/{job_id}/run", tags=["Jobs"])
async def run_job(job_id: str):
    """Manually trigger a job to run."""
    runner = get_job_runner()
    job = runner.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status not in (JobStatus.PENDING, JobStatus.RETRYING):
        raise HTTPException(
            status_code=409,
            detail=f"Job cannot run (current status: {job.status.value})"
        )

    # Run async
    asyncio.create_task(runner.run(job_id))
    return {"message": "Job triggered", "job_id": job_id}


@app.post("/jobs/{job_id}/cancel", tags=["Jobs"])
async def cancel_job(job_id: str):
    """Cancel a pending/retrying job."""
    runner = get_job_runner()
    job = runner.cancel(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job cancelled", "job": job.to_dict()}


# ============================================
# Project Actions Endpoints
# ============================================

@app.get("/projects/{project_id}/actions", tags=["Projects"])
async def get_project_actions(project_id: str):
    """Get available actions for a project."""
    from src.unified.connectors import get_connector
    connector = get_connector(project_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"No connector for project: {project_id}")

    actions = await connector.get_available_actions()
    return {
        "project_id": project_id,
        "actions": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "category": a.category,
                "requires_confirmation": a.requires_confirmation,
            }
            for a in actions
        ],
    }



@app.get("/projects/{project_id}/health", response_model=ProjectHealth, tags=["Projects"])
async def get_project_health(project_id: str):
    """Get health status for a specific project."""
    if project_id not in ALL_PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")

    from src.unified.connectors import get_connector

    connector = get_connector(project_id)
    if not connector:
        raise HTTPException(status_code=404, detail=f"No connector for project: {project_id}")

    health = await connector.check_health()
    return ProjectHealth(
        project_id=project_id,
        timestamp=datetime.now(timezone.utc),
        is_healthy=health.status.value == "online",
        error_count=1 if health.status.value == "offline" else 0,
        warning_count=1 if health.status.value in ("warning", "unauthorized") else 0,
    )


# ============================================
# Audit Log Endpoints
# ============================================

@app.get("/logs", tags=["Audit"])
async def list_logs(
    level: Optional[str] = Query(None),
    job_id: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
):
    """List audit log entries."""
    from src.unified.jobs import JobDB, AuditLevel as AL
    db = JobDB.get_instance()
    log_level = AL(level) if level else None

    logs = db.list_logs(level=log_level, job_id=job_id, limit=limit, offset=offset)
    return {
        "count": len(logs),
        "logs": logs,
    }


@app.get("/logs/summary", tags=["Audit"])
async def log_summary():
    """Get recent log summary."""
    from src.unified.jobs import JobDB, AuditLevel as AL
    db = JobDB.get_instance()

    counts = {}
    for level in ["debug", "info", "warning", "error", "critical"]:
        rows = db.list_logs(level=AL(level), limit=1000)
        counts[level] = len(rows)

    recent = db.list_logs(limit=10)
    return {
        "by_level": counts,
        "recent": recent[:10],
    }


# ============================================
# Startup
# ============================================

@app.on_event("startup")
async def startup_event():
    """Initialize data on startup."""
    logger.info("Starting Unified Dashboard API...")
    await refresh_all_data()
    logger.info("Initial data refresh complete")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
