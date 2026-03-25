"""
Base specialist — abstract agent that all 11 department specialists extend.
Handles: loading dept policy/leader, building prompts, calling LLM, parsing output.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from src.agency_registry import load_department_bundle
from src.llm import FallbackLLM, get_llm

logger = logging.getLogger(__name__)


class BaseSpecialist(ABC):
    """Abstract base for all department specialist agents."""

    department: str = ""

    def __init__(self, llm: Optional[FallbackLLM] = None) -> None:
        if not self.department:
            raise ValueError("Subclass must set department attribute")
        self._llm = llm
        self._bundle: dict[str, Any] = {}
        self._load_bundle()

    def _load_bundle(self) -> None:
        """Load department data from the registry."""
        try:
            self._bundle = load_department_bundle(self.department)
        except Exception as exc:
            logger.error("Failed to load bundle for %s: %s", self.department, exc)
            self._bundle = {}

    @abstractmethod
    def build_system_prompt(self) -> str:
        """Return the system prompt for this specialist."""

    def build_user_prompt(self, state: dict[str, Any]) -> str:
        """Build the user-facing prompt with task and artifact context."""
        task_desc = state.get("task_description", "")
        policy = state.get("policy", {})
        research = state.get("research_results", {})
        feedback = state.get("leader_feedback", "")
        current_step = state.get("current_step", {})
        artifacts = state.get("artifacts", {}) or state.get("required_inputs", {})

        required_inputs = ", ".join(policy.get("required_inputs", []))
        expected_outputs = ", ".join(policy.get("expected_outputs", []))
        sla = policy.get("sla_hours", "?")

        synthesis = research.get("search_synthesis", "(no research data)")
        search_results = research.get("search_results", [])
        search_refs = "\n".join(
            f"[{i + 1}] {result['title']} - {result['url']}"
            for i, result in enumerate(search_results[:5])
        )
        artifact_summary = "\n".join(
            f"- {key}: {str(value)[:250]}"
            for key, value in list(artifacts.items())[:8]
        ) or "- No structured artifacts yet."
        feedback_block = ""
        if feedback:
            feedback_block = (
                "## PREVIOUS FEEDBACK (from leader, must address):\n"
                f"{feedback}\n"
            )
        research_refs_block = f"## RESEARCH REFERENCES:\n{search_refs}\n" if search_refs else ""
        feedback_reminder = (
            "\nIMPORTANT: Address the following feedback from the leader reviewer:\n"
            f"{feedback}"
        ) if feedback else ""

        return f"""## TASK
{task_desc}

## BUSINESS STEP
- Step: {current_step.get('name', 'Single-step execution')}
- Objective: {current_step.get('objective', task_desc)}
- Quality threshold: {state.get('quality_threshold', 98.0)}

## POLICY CONTEXT
- From: {policy.get('from_department', '?')} -> To: {policy.get('to_department', '?')}
- Required inputs: {required_inputs}
- Expected outputs: {expected_outputs}
- SLA: {sla}h

## RESEARCH DATA
{synthesis}

## AVAILABLE ARTIFACTS
{artifact_summary}

{feedback_block}
{research_refs_block}

## YOUR TASK
As the {self.department.replace('_', ' ').title()} Specialist, produce the expected outputs.
Follow the output format specified in your system prompt.
Be specific, actionable, and aligned with the research data above.
{feedback_reminder}
"""

    def parse_output(self, raw_text: str, state: dict[str, Any]) -> dict[str, Any]:
        """Parse LLM raw output into a structured dict keyed by expected outputs."""
        policy = state.get("policy", {})
        expected_outputs = policy.get("expected_outputs", [])
        return {
            output_key: self._extract_section(raw_text, output_key)
            for output_key in expected_outputs
        }

    def _extract_section(self, text: str, section_name: str) -> str:
        """Try to extract a named section from LLM output."""
        import re
        patterns = [
            rf"(?i)^##\s*{re.escape(section_name)}[\s:\-]+(.+?)(?=\n##|\Z)",
            rf"(?i)^##\s*{re.escape(section_name.replace('_', ' '))}[\s:\-]+(.+?)(?=\n##|\Z)",
            rf"(?i)^{re.escape(section_name)}[\s:\-]+(.+?)(?=\n[A-Z]|\Z)",
            rf"(?i)^{re.escape(section_name.replace('_', ' '))}[\s:\-]+(.+?)(?=\n[A-Z]|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return text.strip()

    def build_fallback_output(self, state: dict[str, Any]) -> str:
        """Create a deterministic draft when no LLM provider is available."""
        task_desc = state.get("task_description", "")
        current_step = state.get("current_step", {})
        research = state.get("research_results", {})
        policy = state.get("policy", {})
        expected_outputs = policy.get("expected_outputs", []) or ["deliverable"]
        research_summary = research.get("search_synthesis", "No external research available.")
        artifact_keys = ", ".join((state.get("artifacts") or state.get("required_inputs") or {}).keys()) or "task description only"
        sections: list[str] = []

        for output_key in expected_outputs:
            sections.append(
                f"## {output_key}\n"
                f"- Department owner: {self.department}\n"
                f"- Step objective: {current_step.get('objective', task_desc)}\n"
                f"- Primary recommendation: Create a deliverable for '{output_key}' that directly supports '{task_desc}'.\n"
                f"- Inputs used: {artifact_keys}\n"
                f"- Research context: {str(research_summary)[:500]}\n"
                f"- Next action: Review with the {policy.get('approver_role', 'department lead')} and refine if needed."
            )

        return "\n\n".join(sections)

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        """Main entry point — calls the LLM and returns structured outputs."""
        system = self.build_system_prompt()
        user = self.build_user_prompt(state)

        try:
            llm = self._llm or get_llm()
            if llm.primary_provider is None:
                raise RuntimeError("No configured LLM provider for specialist generation")

            raw = llm.complete(
                prompt=user,
                system=system,
                temperature=0.7,
                max_tokens=4096,
            )
            structured = self.parse_output(raw, state)
            logger.info(
                "[%s] Specialist generated outputs: %s",
                self.department,
                list(structured.keys()),
            )
            return {
                "specialist_output": raw,
                "generated_outputs": structured,
            }
        except Exception as exc:
            logger.warning("[%s] Specialist LLM failed, using fallback draft: %s", self.department, exc)
            raw = self.build_fallback_output(state)
            structured = self.parse_output(raw, state)
            return {
                "specialist_output": raw,
                "generated_outputs": structured,
                "errors": [*state.get("errors", []), f"[{self.department}] Specialist fallback: {exc}"],
            }

    @property
    def leader(self) -> Any:
        return self._bundle.get("leader")

    @property
    def employees(self) -> list[Any]:
        return self._bundle.get("employees", [])

    @property
    def policy(self) -> dict[str, Any]:
        return self._bundle.get("policy", {})
