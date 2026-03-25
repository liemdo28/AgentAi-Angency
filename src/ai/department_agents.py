from __future__ import annotations

from dataclasses import dataclass

from agency_registry import load_all_departments
from ai.models import AgentResult, Task


@dataclass
class DepartmentAgent:
    department: str
    role: str
    expected_outputs: tuple[str, ...]

    def run(self, task: Task) -> AgentResult:
        # Simulate autonomous output generation per department.
        generated = {key: f"{self.department}:{task.goal}:{key}" for key in self.expected_outputs}

        # Score heuristic: output coverage + context quality.
        coverage = 100.0 if self.expected_outputs else 70.0
        context_bonus = min(5.0, float(len(task.context)))
        score = min(100.0, coverage - 2.0 + context_bonus)
        feedback = "meets_threshold" if score >= 98.0 else "needs_iteration"
        return AgentResult(department=self.department, output=generated, score=score, feedback=feedback)


def build_agents() -> dict[str, DepartmentAgent]:
    bundles = load_all_departments()
    agents: dict[str, DepartmentAgent] = {}
    for dept, bundle in bundles.items():
        outputs = tuple(bundle["policy"].get("core_outputs", []))
        agents[dept] = DepartmentAgent(
            department=dept,
            role=bundle["leader"].role,
            expected_outputs=outputs,
        )
    return agents
