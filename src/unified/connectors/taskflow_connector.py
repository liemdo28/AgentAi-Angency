"""
TaskFlow Connector - dashboard.bakudanramen.com

Authentication: PHP session login with email/password.
Credentials are read from settings (env vars).
Session cookie is cached in memory and auto-refreshed on 401/403.

Endpoints:
- POST /index.php?route=login     → session login
- GET  /api/stats                → dashboard statistics
- GET  /api/tasks                → list tasks
- POST /api/tasks                → create task
- GET  /api/tasks/{id}           → task details
- PATCH /api/tasks/{id}          → update task
- GET  /api/users                → team members
- POST /api/internal/sync        → internal sync
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from src.unified.connectors.base import (
    BaseConnector,
    ConnectorAction,
    ConnectorResult,
    ConnectorStatus,
    HealthResult,
)
from src.unified.settings import get_settings, mask_secret

logger = logging.getLogger(__name__)


class TaskFlowConnector(BaseConnector):
    """Connector for TaskFlow dashboard (dashboard.bakudanramen.com)."""

    project_id = "dashboard-taskflow"
    project_name = "Dashboard TaskFlow"

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._base_url = settings.taskflow_base_url.rstrip("/")
        self._username = settings.taskflow_username
        self._password = settings.taskflow_password
        self._timeout = float(settings.taskflow_timeout)

        # In-memory session state
        self._client: Optional[httpx.AsyncClient] = None
        self._logged_in: bool = False
        self._login_error: Optional[str] = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def timeout(self) -> float:
        return self._timeout

    def is_configured(self) -> bool:
        """Check if credentials are set."""
        return bool(self._username and self._password)

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self) -> ConnectorResult:
        """
        Login to TaskFlow PHP backend.
        Stores session cookie for subsequent requests.
        """
        if not self.is_configured():
            return ConnectorResult(
                success=False,
                message="TaskFlow credentials not configured. Set TASKFLOW_USERNAME and TASKFLOW_PASSWORD in .env",
            )

        logger.info(
            "TaskFlow login attempt for user: %s",
            mask_secret(self._username, keep=3),
        )

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                follow_redirects=True,
                cookies=httpx.Cookies(),
            ) as client:
                # Try standard PHP login endpoint
                response = await client.post(
                    f"{self._base_url}/index.php?route=login",
                    data={
                        "email": self._username,
                        "password": self._password,
                    },
                    headers={"Accept": "application/json"},
                )

                # Check for redirect to dashboard (successful login)
                # or stay on login page (failed)
                if response.status_code == 200:
                    text = response.text.lower()
                    # PHP CodeIgniter-style: redirect usually goes to dashboard
                    if "login" in text and "error" not in text and "password" not in text[:500]:
                        # Check URL we ended up at
                        final_url = str(response.url)
                        if "dashboard" in final_url or "login" not in final_url:
                            self._logged_in = True
                            # Extract cookies from the client
                            self._client = client
                            logger.info("TaskFlow login successful")
                            return ConnectorResult(
                                success=True,
                                message="Login successful",
                            )
                    elif "login" in text:
                        self._logged_in = False
                        self._login_error = "Invalid email or password"
                        logger.warning("TaskFlow login failed: invalid credentials")
                        return ConnectorResult(
                            success=False,
                            message="Invalid email or password",
                            error="auth_failed",
                        )

                # Fallback: check if we got a session cookie
                session_cookies = [
                    c.name for c in client.cookies.jar
                    if "session" in c.name.lower() or "token" in c.name.lower()
                ]
                if session_cookies or response.status_code == 200:
                    self._logged_in = True
                    self._client = client
                    logger.info("TaskFlow login (cookie-based) successful")
                    return ConnectorResult(
                        success=True,
                        message="Login successful",
                    )

                return ConnectorResult(
                    success=False,
                    message=f"Login failed: HTTP {response.status_code}",
                    error="login_failed",
                )

        except httpx.TimeoutException:
            self._logged_in = False
            self._login_error = f"Login timeout after {self._timeout}s"
            logger.warning("TaskFlow login timeout")
            return ConnectorResult(
                success=False,
                message=self._login_error,
                error="timeout",
            )
        except Exception as e:
            self._logged_in = False
            self._login_error = str(e)
            logger.exception("TaskFlow login error")
            return ConnectorResult(
                success=False,
                message=f"Login error: {e}",
                error=type(e).__name__,
            )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get authenticated client, auto-login if needed."""
        if not self._logged_in or self._client is None:
            result = await self.login()
            if not result.success:
                raise RuntimeError(f"TaskFlow not authenticated: {result.message}")
        return self._client

    # ── Authenticated request ─────────────────────────────────────────────────

    async def _auth_request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> ConnectorResult:
        """
        Make an authenticated request.
        Auto re-logs in if session expired (401/403).
        """
        start = datetime.now(timezone.utc)

        try:
            client = await self._get_client()
        except RuntimeError as e:
            return ConnectorResult(
                success=False,
                message=str(e),
                error="not_authenticated",
                duration_ms=0,
            )

        url = f"{self._base_url}{path}"

        try:
            request_kwargs: dict[str, Any] = {
                "url": url,
                "timeout": self._timeout,
            }
            if params:
                request_kwargs["params"] = params

            if method == "GET":
                request_kwargs["headers"] = {"Accept": "application/json"}
            else:
                request_kwargs["json"] = payload
                request_kwargs["headers"] = {"Accept": "application/json"}

            response = await client.request(method, **request_kwargs)
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            # Handle session expiry
            if response.status_code in (401, 403):
                logger.info("TaskFlow session expired, re-logging in...")
                self._logged_in = False
                self._client = None

                login_result = await self.login()
                if not login_result.success:
                    return ConnectorResult(
                        success=False,
                        message=f"Session expired, re-login failed: {login_result.message}",
                        error="session_expired",
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                    )

                # Retry once with new session
                client = await self._get_client()
                request_kwargs["url"] = url
                response = await client.request(method, **request_kwargs)
                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            try:
                data = response.json()
            except Exception:
                data = {"raw": response.text[:200]}

            return ConnectorResult(
                success=response.is_success,
                message="Success" if response.is_success else f"HTTP {response.status_code}",
                data=data,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

        except httpx.TimeoutException:
            return ConnectorResult(
                success=False,
                message=f"Request timeout after {self._timeout}s",
                error="timeout",
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )
        except Exception as e:
            logger.exception("TaskFlow request failed")
            return ConnectorResult(
                success=False,
                message=str(e),
                error=type(e).__name__,
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

    # ── BaseConnector interface ───────────────────────────────────────────────

    async def check_health(self) -> HealthResult:
        """Check if TaskFlow is reachable and session is valid."""
        start = datetime.now(timezone.utc)

        if not self.is_configured():
            return HealthResult(
                status=ConnectorStatus.WARNING,
                latency_ms=0,
                message="TaskFlow credentials not configured in .env",
                details={"hint": "Set TASKFLOW_USERNAME and TASKFLOW_PASSWORD"},
            )

        # First check connectivity
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.get(f"{self._base_url}/api/stats", timeout=5.0)
                latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                if r.status_code in (401, 403):
                    # Try to login
                    login_result = await self.login()
                    if login_result.success:
                        return HealthResult(
                            status=ConnectorStatus.ONLINE,
                            latency_ms=latency_ms,
                            message="Connected and authenticated",
                        )
                    else:
                        return HealthResult(
                            status=ConnectorStatus.UNAUTHORIZED,
                            latency_ms=latency_ms,
                            message=f"Auth failed: {login_result.message}",
                        )

                if r.is_success:
                    return HealthResult(
                        status=ConnectorStatus.ONLINE,
                        latency_ms=latency_ms,
                        message="Connected",
                        details=r.json() if r.headers.get("content-type", "").startswith("application/json") else {},
                    )

                return HealthResult(
                    status=ConnectorStatus.WARNING,
                    latency_ms=latency_ms,
                    message=f"HTTP {r.status_code}",
                )

        except httpx.TimeoutException:
            return HealthResult(
                status=ConnectorStatus.OFFLINE,
                latency_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                message=f"Timeout after {self._timeout}s",
            )
        except httpx.ConnectError:
            return HealthResult(
                status=ConnectorStatus.OFFLINE,
                latency_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                message=f"Cannot reach {self._base_url}",
            )
        except Exception as e:
            logger.exception("TaskFlow health check failed")
            return HealthResult(
                status=ConnectorStatus.WARNING,
                latency_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                message=str(e),
            )

    async def get_status(self) -> dict:
        """Get current status and metrics."""
        health = await self.check_health()
        status = {
            "project_id": self.project_id,
            "status": health.status.value,
            "configured": self.is_configured(),
            "authenticated": self._logged_in,
            "latency_ms": health.latency_ms,
            "last_check": health.last_check.isoformat(),
            "metrics": {},
        }

        if health.status == ConnectorStatus.ONLINE:
            result = await self.get_json("/api/stats")
            if result.success and result.data:
                data = result.data
                status["metrics"] = {
                    "total_tasks": data.get("total", 0),
                    "completed_today": data.get("completed_today", 0),
                    "overdue": data.get("overdue", 0),
                    "in_progress": data.get("in_progress", 0),
                    "team_members": data.get("users", 0),
                }

        return status

    async def get_available_actions(self) -> list[ConnectorAction]:
        """List available actions for TaskFlow."""
        actions = []

        if self.is_configured():
            actions.extend([
                ConnectorAction(
                    id="taskflow.health",
                    name="Health Check",
                    description="Verify TaskFlow connection and session",
                    category="general",
                ),
                ConnectorAction(
                    id="taskflow.fetch_stats",
                    name="Fetch Stats",
                    description="Get latest task statistics",
                    category="sync",
                ),
                ConnectorAction(
                    id="taskflow.list_tasks",
                    name="List Tasks",
                    description="Retrieve all tasks",
                    category="sync",
                ),
                ConnectorAction(
                    id="taskflow.sync_team",
                    name="Sync Team",
                    description="Refresh team member list",
                    category="sync",
                ),
                ConnectorAction(
                    id="taskflow.create_task",
                    name="Create Task",
                    description="Create a new task (requires title/description)",
                    category="general",
                    requires_confirmation=True,
                ),
            ])
        else:
            actions.append(
                ConnectorAction(
                    id="taskflow.setup",
                    name="Configure",
                    description="TaskFlow credentials not set — see .env",
                    category="general",
                )
            )

        return actions

    async def execute_action(
        self,
        action_id: str,
        payload: Optional[dict] = None,
        job_id: Optional[str] = None,
    ) -> ConnectorResult:
        del job_id  # part of interface signature; context tracked via job audit trail
        """Execute a TaskFlow action."""
        actions_map = {
            "taskflow.health": ("GET", "/api/stats"),
            "taskflow.fetch_stats": ("GET", "/api/stats"),
            "taskflow.list_tasks": ("GET", "/api/tasks"),
            "taskflow.sync_team": ("GET", "/api/users"),
            "taskflow.create_task": ("POST", "/api/tasks"),
        }

        if action_id not in actions_map:
            return ConnectorResult(success=False, message=f"Unknown action: {action_id}")

        if not self.is_configured():
            return ConnectorResult(
                success=False,
                message="TaskFlow not configured — set TASKFLOW_USERNAME and TASKFLOW_PASSWORD in .env",
                error="not_configured",
            )

        method, endpoint = actions_map[action_id]

        if method == "POST":
            return await self._auth_request(method, endpoint, payload=payload)
        else:
            return await self._auth_request(method, endpoint)

    async def get_metrics(self) -> dict:
        """Get TaskFlow metrics."""
        result = await self._auth_request("GET", "/api/stats")
        if result.success and result.data:
            return {
                "total_tasks": result.data.get("total", 0),
                "completed_today": result.data.get("completed_today", 0),
                "overdue": result.data.get("overdue", 0),
                "in_progress": result.data.get("in_progress", 0),
                "team_members": result.data.get("users", 0),
            }
        return {}
