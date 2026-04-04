"""
Base Connector - Abstract interface for all project connectors.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class ConnectorStatus(str, Enum):
    ONLINE = "online"
    WARNING = "warning"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


@dataclass
class ConnectorAction:
    """Represents an action that can be executed on a project."""
    id: str
    name: str
    description: str
    requires_confirmation: bool = False
    category: str = "general"  # general, sync, deploy, data
    http_method: str = "POST"
    endpoint: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class ConnectorResult:
    """Result from a connector operation."""
    success: bool
    message: str
    data: Any = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    duration_ms: float = 0.0


@dataclass
class HealthResult:
    """Health check result from a connector."""
    status: ConnectorStatus
    latency_ms: float = 0.0
    message: str = ""
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict = field(default_factory=dict)


class BaseConnector(ABC):
    """
    Abstract base class for all project connectors.

    Each connector must implement:
    - check_health(): Check if the project is reachable
    - get_status(): Get current status with metrics
    - get_available_actions(): List available actions for this project
    - execute_action(action_id): Execute a specific action
    - get_metrics(): Get project-specific metrics
    """

    # Override in subclass
    project_id: str = ""
    project_name: str = ""
    base_url: str = ""
    timeout: float = 10.0

    # Default headers (can be overridden with auth token)
    _default_headers: dict = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None

    @property
    def headers(self) -> dict:
        """Build request headers with auth token."""
        h = self._default_headers.copy()
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def set_token(self, token: str) -> None:
        """Set Bearer token for authentication."""
        self._token = token

    async def _request(
        self,
        method: str,
        endpoint: str,
        payload: Optional[dict] = None,
        params: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> ConnectorResult:
        """Make HTTP request with timing."""
        url = f"{self.base_url}{endpoint}" if endpoint else self.base_url
        timeout = timeout or self.timeout
        start = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                request_kwargs = {
                    "url": url,
                    "headers": self.headers,
                }
                if params:
                    request_kwargs["params"] = params
                if payload:
                    request_kwargs["json"] = payload

                response = await client.request(method, **request_kwargs)
                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                try:
                    data = response.json()
                except Exception:
                    data = {"raw": response.text}

                # Handle common status codes
                if response.status_code == 401:
                    return ConnectorResult(
                        success=False,
                        message="Unauthorized - check API token",
                        error="401 Unauthorized",
                        status_code=401,
                        duration_ms=duration_ms,
                    )
                elif response.status_code == 403:
                    return ConnectorResult(
                        success=False,
                        message="Forbidden - insufficient permissions",
                        error="403 Forbidden",
                        status_code=403,
                        duration_ms=duration_ms,
                    )

                return ConnectorResult(
                    success=response.is_success,
                    message="Success" if response.is_success else f"HTTP {response.status_code}",
                    data=data,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )

        except httpx.TimeoutException:
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return ConnectorResult(
                success=False,
                message=f"Request timeout after {timeout}s",
                error="timeout",
                duration_ms=duration_ms,
            )
        except httpx.ConnectError:
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return ConnectorResult(
                success=False,
                message=f"Cannot connect to {self.base_url}",
                error="connection_error",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.exception(f"Connector request failed: {e}")
            return ConnectorResult(
                success=False,
                message=str(e),
                error=type(e).__name__,
                duration_ms=duration_ms,
            )

    # ---- Abstract methods ----

    @abstractmethod
    async def check_health(self) -> HealthResult:
        """Check if the project is reachable and healthy."""
        raise NotImplementedError

    @abstractmethod
    async def get_status(self) -> dict:
        """Get current status with metrics."""
        raise NotImplementedError

    @abstractmethod
    async def get_available_actions(self) -> list[ConnectorAction]:
        """List all available actions for this project."""
        raise NotImplementedError

    @abstractmethod
    async def execute_action(
        self,
        action_id: str,
        payload: Optional[dict] = None,
        job_id: Optional[str] = None,
    ) -> ConnectorResult:
        """Execute a specific action on the project."""
        raise NotImplementedError

    async def get_metrics(self) -> dict:
        """Get project-specific metrics. Override in subclass."""
        return {}

    # ---- Utility methods ----

    async def get_json(self, endpoint: str, params: Optional[dict] = None) -> ConnectorResult:
        """GET request."""
        return await self._request("GET", endpoint, params=params)

    async def post_json(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
    ) -> ConnectorResult:
        """POST request."""
        return await self._request("POST", endpoint, payload=payload)

    async def patch_json(
        self,
        endpoint: str,
        payload: Optional[dict] = None,
    ) -> ConnectorResult:
        """PATCH request."""
        return await self._request("PATCH", endpoint, payload=payload)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} project={self.project_id} url={self.base_url}>"
