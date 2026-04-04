"""
Connectors - API adapters for each child project.

Each connector handles:
- Authentication (API tokens, session cookies)
- API calls to the target project
- Data normalization
- Error handling

Connectors are registered in CONNECTOR_REGISTRY.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.unified.connectors.base import BaseConnector

from src.unified.connectors.taskflow_connector import TaskFlowConnector
from src.unified.connectors.review_connector import ReviewConnector
from src.unified.connectors.integration_connector import IntegrationConnector
from src.unified.connectors.agency_connector import AgencyConnector
from src.unified.connectors.marketing_connector import MarketingConnector

# Registry - maps project_id to connector instance
# Note: Growth Dashboard actions are handled by MarketingConnector (marketing.* namespace)
CONNECTOR_REGISTRY: dict[str, BaseConnector] = {
    "agentai-agency": AgencyConnector(),
    "dashboard-taskflow": TaskFlowConnector(),
    "review-management": ReviewConnector(),
    "integration-full": IntegrationConnector(),
    "marketing": MarketingConnector(),
}


def get_connector(project_id: str) -> BaseConnector | None:
    """Get connector for a project."""
    return CONNECTOR_REGISTRY.get(project_id)


def list_connectors() -> list[str]:
    """List all registered project IDs."""
    return list(CONNECTOR_REGISTRY.keys())


__all__ = [
    "BaseConnector",
    "AgencyConnector",
    "TaskFlowConnector",
    "ReviewConnector",
    "IntegrationConnector",
    "MarketingConnector",
    "CONNECTOR_REGISTRY",
    "get_connector",
    "list_connectors",
]
