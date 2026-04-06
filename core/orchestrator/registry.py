"""
Agent Registry — maps agent IDs to runnable agent instances.

Supports dynamic registration so new agents (or department adapters)
can be plugged in at runtime.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from core.agents.base import BaseAgent

logger = logging.getLogger("orchestrator.registry")


class AgentRegistry:
    """Thread-safe agent lookup by ID."""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register(self, agent_id: str, agent: BaseAgent) -> None:
        logger.info("Registered agent: %s (%s)", agent_id, type(agent).__name__)
        self._agents[agent_id] = agent

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        return [
            {
                "id": aid,
                "type": type(a).__name__,
                "description": getattr(a, "description", ""),
                "title": getattr(a, "title", ""),
                "responsibilities": getattr(a, "responsibilities", []),
                "tools": getattr(a, "agent_tools", []),
                "kpis": getattr(a, "kpis", []),
                "model": getattr(a, "model", ""),
                "level": getattr(a, "level", ""),
            }
            for aid, a in self._agents.items()
        ]

    def __len__(self) -> int:
        return len(self._agents)
