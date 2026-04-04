"""
Agency Connector - AgentAI Agency (self)
Connects to the local FastAPI on port 8000.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.unified.connectors.base import (
    BaseConnector,
    ConnectorAction,
    ConnectorResult,
    ConnectorStatus,
    HealthResult,
)

logger = logging.getLogger(__name__)


class AgencyConnector(BaseConnector):
    """Connector for the Agency API itself."""

    project_id = "agentai-agency"
    project_name = "AgentAI Agency"
    base_url = "http://localhost:8000"
    timeout = 10.0

    async def check_health(self) -> HealthResult:
        """Check if Agency API is running."""
        start = datetime.now(timezone.utc)
        result = await self.get_json("/status")
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        if not result.success:
            if result.error == "connection_error":
                return HealthResult(
                    status=ConnectorStatus.OFFLINE,
                    latency_ms=latency_ms,
                    message="Agency API not running on port 8000",
                )
            elif result.error == "timeout":
                return HealthResult(
                    status=ConnectorStatus.WARNING,
                    latency_ms=latency_ms,
                    message="Agency API slow to respond",
                )
            return HealthResult(
                status=ConnectorStatus.WARNING,
                latency_ms=latency_ms,
                message=f"Error: {result.message}",
            )

        return HealthResult(
            status=ConnectorStatus.ONLINE,
            latency_ms=latency_ms,
            message="Agency API is healthy",
            details=result.data or {},
        )

    async def get_status(self) -> dict:
        """Get Agency status."""
        health = await self.check_health()
        status = {
            "project_id": self.project_id,
            "status": health.status.value,
            "latency_ms": health.latency_ms,
            "last_check": health.last_check.isoformat(),
            "metrics": {},
        }

        if health.status == ConnectorStatus.ONLINE and health.details:
            d = health.details
            status["metrics"] = {
                "total_tasks": d.get("total", 0),
                "active_tasks": d.get("active", 0),
                "pending_handoffs": d.get("pending", 0),
                "passed_tasks": d.get("passed", 0),
                "avg_score": d.get("avg_score", 0),
                "pass_rate": d.get("pass_rate", 0),
            }

        return status

    async def get_available_actions(self) -> list[ConnectorAction]:
        """List available actions."""
        return [
            ConnectorAction(
                id="agency.refresh",
                name="Refresh Status",
                description="Re-fetch agency status",
                category="sync",
                http_method="GET",
                endpoint="/status",
            ),
            ConnectorAction(
                id="agency.tasks",
                name="List Tasks",
                description="Get all tasks from AI pipeline",
                category="sync",
                http_method="GET",
                endpoint="/tasks",
            ),
            ConnectorAction(
                id="agency.handoffs",
                name="Review Handoffs",
                description="List pending handoffs for approval",
                category="general",
                http_method="GET",
                endpoint="/handoffs",
            ),
        ]

    async def execute_action(
        self,
        action_id: str,
        payload: Optional[dict] = None,
        job_id: Optional[str] = None,
    ) -> ConnectorResult:
        """Execute an Agency action."""
        actions_map = {
            "agency.refresh": ("GET", "/status"),
            "agency.tasks": ("GET", "/tasks"),
            "agency.handoffs": ("GET", "/handoffs"),
        }

        if action_id not in actions_map:
            return ConnectorResult(success=False, message=f"Unknown action: {action_id}")

        method, endpoint = actions_map[action_id]
        return await self._request(method, endpoint)

    async def get_metrics(self) -> dict:
        """Get agency metrics."""
        result = await self.get_json("/status")
        if result.success and result.data:
            return {
                "total_tasks": result.data.get("total", 0),
                "active_tasks": result.data.get("active", 0),
                "pending_handoffs": result.data.get("pending", 0),
                "avg_score": result.data.get("avg_score", 0),
                "pass_rate": result.data.get("pass_rate", 0),
            }
        return {}
