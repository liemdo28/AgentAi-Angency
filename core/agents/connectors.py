"""
Connector agents — wrap the existing unified connectors
(marketing, review, taskflow, integration) as orchestrator-compatible agents.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from core.agents.base import BaseAgent

logger = logging.getLogger("agents.connectors")


class _ConnectorAgent(BaseAgent):
    """Base for connector-wrapping agents."""

    connector_module: str = ""
    connector_class: str = ""

    def _get_connector(self):
        import importlib
        mod = importlib.import_module(f"src.unified.connectors.{self.connector_module}")
        cls = getattr(mod, self.connector_class)
        return cls()

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        try:
            connector = self._get_connector()
            payload = task.get("context_json", {})
            action = payload.get("action", "health_check")

            if action == "health_check":
                result = connector.health_check()
            else:
                result = connector.execute(payload)

            return {"status": "done", "connector": self.connector_module, "output": result}
        except Exception as exc:
            logger.exception("Connector %s error: %s", self.connector_module, exc)
            return {"status": "error", "error": str(exc)}


class MarketingAgent(_ConnectorAgent):
    description = "Marketing site connector agent"
    connector_module = "marketing_connector"
    connector_class = "MarketingConnector"


class ReviewAgent(_ConnectorAgent):
    description = "Review management connector agent"
    connector_module = "review_connector"
    connector_class = "ReviewConnector"


class TaskFlowAgent(_ConnectorAgent):
    description = "TaskFlow dashboard connector agent"
    connector_module = "taskflow_connector"
    connector_class = "TaskFlowConnector"
