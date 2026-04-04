"""
BaseAgent — abstract contract every agent must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseAgent(ABC):
    """Minimal agent interface for the orchestrator."""

    description: str = ""
    budget_limit: float = 50.0  # default USD
    _total_cost: float = 0.0

    @abstractmethod
    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute *task* and return a result dict.

        Must be synchronous (the orchestrator calls this in a loop).
        """

    @property
    def cost(self) -> float:
        return self._total_cost

    def add_cost(self, amount: float) -> None:
        self._total_cost += amount
