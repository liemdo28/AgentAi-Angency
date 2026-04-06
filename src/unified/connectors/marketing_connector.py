"""
Marketing Connector - marketing.bakudanramen.com

Authentication: Bearer token (backend-to-backend)
Token is read from settings (MARKETING_API_TOKEN env var).
All requests include the Bearer token in Authorization header.

Endpoints expected on Marketing backend:
- GET  /api/health              → health check
- POST /api/import/upload       → file upload + import
- GET  /api/campaigns/stats     → campaign statistics
- POST /api/campaign/sync        → sync campaign data
- GET  /api/reports             → pull reports
- GET  /api/assets              → list uploaded assets
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx

from src.unified.connectors.base import (
    BaseConnector,
    ConnectorAction,
    ConnectorResult,
    ConnectorStatus,
    HealthResult,
)
from src.unified.settings import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MarketingConnector(BaseConnector):
    """Connector for Marketing website (marketing.bakudanramen.com)."""

    project_id = "marketing"
    project_name = "Marketing Website"

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._base_url = settings.marketing_base_url.rstrip("/")
        self._token = settings.marketing_api_token
        self._timeout = settings.marketing_timeout
        self._growth_api_key = getattr(settings, "growth_api_key", "")
        self._growth_base_url = getattr(settings, "growth_base_url", "").rstrip("/") or "https://marketing.bakudanramen.com/api"

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def timeout(self) -> float:
        return float(self._timeout)

    @property
    def headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def is_configured(self) -> bool:
        """Check if connector has required credentials."""
        return bool(self._token)

    async def check_health(self) -> HealthResult:
        """
        Health check: GET /api/health
        Returns status, latency, and service info.
        """
        start = datetime.now(timezone.utc)
        url = f"{self._base_url}/api/health"

        try:
            async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
                response = await client.get(url, headers=self.headers)
                latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                if response.status_code == 401:
                    return HealthResult(
                        status=ConnectorStatus.UNAUTHORIZED,
                        latency_ms=latency_ms,
                        message="Invalid or missing MARKETING_API_TOKEN",
                        details={"hint": "Set MARKETING_API_TOKEN in .env"},
                    )
                elif response.status_code == 403:
                    return HealthResult(
                        status=ConnectorStatus.UNAUTHORIZED,
                        latency_ms=latency_ms,
                        message="Token lacks sufficient permissions",
                    )
                elif not response.is_success:
                    return HealthResult(
                        status=ConnectorStatus.WARNING,
                        latency_ms=latency_ms,
                        message=f"HTTP {response.status_code}",
                        details={"status_code": response.status_code},
                    )

                try:
                    data = response.json()
                except Exception:
                    data = {}

                return HealthResult(
                    status=ConnectorStatus.ONLINE,
                    latency_ms=latency_ms,
                    message=data.get("message", "Marketing API is healthy"),
                    details=data,
                )

        except httpx.TimeoutException:
            return HealthResult(
                status=ConnectorStatus.OFFLINE,
                latency_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                message=f"Connection timeout after {self._timeout}s",
            )
        except httpx.ConnectError:
            return HealthResult(
                status=ConnectorStatus.OFFLINE,
                latency_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                message=f"Cannot reach {self._base_url}",
            )
        except Exception as e:
            logger.exception("Marketing health check failed")
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
            "latency_ms": health.latency_ms,
            "last_check": health.last_check.isoformat(),
            "metrics": {},
        }

        if health.status == ConnectorStatus.ONLINE:
            stats_result = await self.get_json("/api/campaigns/stats")
            if stats_result.success and stats_result.data:
                data = stats_result.data
                status["metrics"] = {
                    "campaigns": data.get("total", 0),
                    "active": data.get("active", 0),
                    "impressions": data.get("impressions", 0),
                    "clicks": data.get("clicks", 0),
                    "spend": data.get("spend", 0),
                    "revenue": data.get("revenue", 0),
                }

        return status

    async def get_available_actions(self) -> list[ConnectorAction]:
        """List available actions for Marketing."""
        actions = [
            ConnectorAction(
                id="marketing.health",
                name="Health Check",
                description="Verify Marketing API token and connection",
                category="general",
                http_method="GET",
                endpoint="/api/health",
            ),
            ConnectorAction(
                id="marketing.campaign_stats",
                name="Campaign Stats",
                description="Get campaign performance statistics",
                category="sync",
                http_method="GET",
                endpoint="/api/campaigns/stats",
            ),
            ConnectorAction(
                id="marketing.sync_campaigns",
                name="Sync Campaigns",
                description="Sync campaign data from Marketing",
                category="sync",
                http_method="POST",
                endpoint="/api/campaign/sync",
            ),
            ConnectorAction(
                id="marketing.pull_report",
                name="Pull Report",
                description="Retrieve performance report",
                category="data",
                http_method="GET",
                endpoint="/api/reports",
            ),
            ConnectorAction(
                id="marketing.list_assets",
                name="List Assets",
                description="List uploaded images and assets",
                category="general",
                http_method="GET",
                endpoint="/api/assets",
            ),
            # Growth Dashboard actions (same host: bakudanramen.com)
            ConnectorAction(
                id="marketing.branch_state",
                name="Branch State",
                description="Fetch branch data with sales/marketing metrics",
                category="sync",
                http_method="GET",
                endpoint="/branch-state.php",
            ),
            ConnectorAction(
                id="marketing.analytics",
                name="Analytics",
                description="Retrieve analytics data from Growth Dashboard",
                category="sync",
                http_method="GET",
                endpoint="/analytics.php",
            ),
        ]

        # Only add upload action if token is configured
        if self.is_configured():
            actions.insert(
                1,
                ConnectorAction(
                    id="marketing.upload",
                    name="Upload File",
                    description="Upload CSV/Excel/data file to Marketing (multipart)",
                    category="data",
                    requires_confirmation=True,
                    http_method="POST",
                    endpoint="/api/import/upload",
                ),
            )

        return actions

    async def execute_action(
        self,
        action_id: str,
        payload: Optional[dict] = None,
        job_id: Optional[str] = None,
    ) -> ConnectorResult:
        """Execute a Marketing or Growth Dashboard action."""
        # Marketing actions (uses marketing.bakudanramen.com)
        marketing_map = {
            "marketing.health": ("GET", "/api/health"),
            "marketing.campaign_stats": ("GET", "/api/campaigns/stats"),
            "marketing.sync_campaigns": ("POST", "/api/campaign/sync"),
            "marketing.pull_report": ("GET", "/api/reports"),
            "marketing.list_assets": ("GET", "/api/assets"),
        }

        # Growth Dashboard actions (uses bakudanramen.com/growth-dashboard/api)
        growth_map = {
            "marketing.branch_state": ("GET", "/branch-state.php"),
            "marketing.analytics": ("GET", "/analytics.php"),
        }

        if action_id == "marketing.upload":
            return await self._upload_file(payload)

        if action_id in marketing_map:
            method, endpoint = marketing_map[action_id]
            result = await self._request(method, endpoint, payload=payload)
            logger.info(
                "Marketing action: %s %s → %s",
                method, endpoint,
                "success" if result.success else f"HTTP {result.status_code}",
            )
            return result

        if action_id in growth_map:
            method, endpoint = growth_map[action_id]
            url = f"{self._growth_base_url}{endpoint}"
            return await self._request_growth(method, url, params=payload)

        return ConnectorResult(success=False, message=f"Unknown action: {action_id}")

    async def _request_growth(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
    ) -> ConnectorResult:
        """Make a request to the Growth Dashboard (bakudanramen.com)."""
        start = datetime.now(timezone.utc)
        try:
            async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
                headers = {"Accept": "application/json"}
                if self._growth_api_key:
                    headers["Authorization"] = f"Bearer {self._growth_api_key}"
                response = await client.request(method, url, params=params, headers=headers)
                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                try:
                    data = response.json()
                except Exception:
                    data = {"raw": response.text[:500]}
                return ConnectorResult(
                    success=response.is_success,
                    message=f"HTTP {response.status_code}",
                    data=data,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
        except httpx.TimeoutException:
            return ConnectorResult(
                success=False,
                message=f"Growth Dashboard timeout after {self._timeout}s",
                error="timeout",
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )
        except Exception as e:
            logger.exception("Growth Dashboard request failed")
            return ConnectorResult(
                success=False,
                message=str(e),
                error=type(e).__name__,
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

    async def _upload_file(self, payload: Optional[dict] = None) -> ConnectorResult:
        """
        Upload a file via multipart/form-data to Marketing backend.

        Expected payload keys:
          - file_path: absolute path to local file
          - extra: optional dict of additional form fields
        """
        payload = payload or {}
        file_path = payload.get("file_path")

        if not file_path:
            return ConnectorResult(success=False, message="file_path required in payload")

        f = Path(file_path)
        if not f.exists():
            return ConnectorResult(success=False, message=f"File not found: {file_path}")

        # Validate file
        settings = get_settings()
        ok, err_msg = settings.validate_upload(f.name, f.stat().st_size)
        if not ok:
            return ConnectorResult(success=False, message=err_msg)

        start = datetime.now(timezone.utc)
        url = f"{self._base_url}/api/import/upload"

        try:
            async with httpx.AsyncClient(timeout=float(self._timeout)) as client:
                with open(f, "rb") as fh:
                    extra_fields = payload.get("extra", {})
                    files: dict[str, Any] = {"file": (f.name, fh)}
                    data: dict[str, str] = {k: str(v) for k, v in extra_fields.items()}

                    # Don't set Content-Type for multipart — httpx sets it automatically
                    response = await client.post(
                        url,
                        files=files,
                        data=data,
                        headers={"Authorization": f"Bearer {self._token}"} if self._token else {},
                    )

                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                try:
                    response_data = response.json()
                except Exception:
                    response_data = {"raw": response.text[:500]}

                if response.status_code == 401:
                    return ConnectorResult(
                        success=False,
                        message="Unauthorized — check MARKETING_API_TOKEN",
                        error="401 Unauthorized",
                        status_code=401,
                        duration_ms=duration_ms,
                    )

                success = response.is_success and response_data.get("success", response.is_success)

                return ConnectorResult(
                    success=bool(success),
                    message=response_data.get("message", "Upload completed"),
                    data=response_data,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

        except httpx.TimeoutException:
            return ConnectorResult(
                success=False,
                message=f"Upload timed out after {self._timeout}s",
                error="timeout",
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )
        except Exception as e:
            logger.exception("Marketing upload failed")
            return ConnectorResult(
                success=False,
                message=str(e),
                error=type(e).__name__,
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

    async def get_metrics(self) -> dict:
        """Get marketing + growth dashboard metrics."""
        metrics = {}

        # Marketing metrics
        result = await self.get_json("/api/campaigns/stats")
        if result.success and result.data:
            data = result.data
            spend = data.get("spend", 0)
            revenue = data.get("revenue", 0)
            metrics["marketing"] = {
                "campaigns": data.get("total", 0),
                "active": data.get("active", 0),
                "impressions": data.get("impressions", 0),
                "clicks": data.get("clicks", 0),
                "spend": spend,
                "revenue": revenue,
                "roas": round(revenue / max(spend, 1), 2),
            }

        # Growth Dashboard metrics (branch-state)
        growth_result = await self.get_json_growth("/branch-state.php")
        if growth_result.success and growth_result.data:
            branches = growth_result.data.get("branches", [])
            total_revenue = sum(
                sum(float(r.get("revenue", 0) or 0)
                    for r in b.get("state", {}).get("salesRows", []))
                for b in branches
            )
            total_orders = sum(
                sum(int(r.get("orders", 0) or 0)
                    for r in b.get("state", {}).get("salesRows", []))
                for b in branches
            )
            total_spend = sum(float(b.get("state", {}).get("spend", 0) or 0) for b in branches)
            metrics["growth"] = {
                "branches": len(branches),
                "total_revenue": round(total_revenue, 2),
                "total_orders": total_orders,
                "marketing_spend": round(total_spend, 2),
                "roas": round(total_revenue / max(total_spend, 1), 2),
            }

        return metrics

    async def get_json_growth(self, endpoint: str) -> ConnectorResult:
        """GET JSON from Growth Dashboard."""
        url = f"{self._growth_base_url}{endpoint}"
        return await self._request_growth("GET", url)
