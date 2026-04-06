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
    connector_module = "marketing_connector"
    connector_class = "MarketingConnector"

    from core.agents.roles import ROLE_DEFINITIONS
    _role = ROLE_DEFINITIONS.get("connector-marketing", {})
    description = _role.get("system_prompt", "Marketing site connector agent")
    title = _role.get("title", "Marketing Ops")
    responsibilities = _role.get("responsibilities", [])
    agent_tools = _role.get("tools", [])
    kpis = _role.get("kpis", [])
    model = _role.get("model", "")
    level = _role.get("level", "specialist")


class ReviewAgent(_ConnectorAgent):
    connector_module = "review_connector"
    connector_class = "ReviewConnector"

    from core.agents.roles import ROLE_DEFINITIONS
    _role = ROLE_DEFINITIONS.get("connector-review", {})
    description = _role.get("system_prompt", "Review management connector agent")
    title = _role.get("title", "Review Ops")
    responsibilities = _role.get("responsibilities", [])
    agent_tools = _role.get("tools", [])
    kpis = _role.get("kpis", [])
    model = _role.get("model", "")
    level = _role.get("level", "specialist")


class TaskFlowAgent(_ConnectorAgent):
    connector_module = "taskflow_connector"
    connector_class = "TaskFlowConnector"

    from core.agents.roles import ROLE_DEFINITIONS
    _role = ROLE_DEFINITIONS.get("connector-taskflow", {})
    description = _role.get("system_prompt", "TaskFlow dashboard connector agent")
    title = _role.get("title", "TaskFlow Ops")
    responsibilities = _role.get("responsibilities", [])
    agent_tools = _role.get("tools", [])
    kpis = _role.get("kpis", [])
    model = _role.get("model", "")
    level = _role.get("level", "specialist")
