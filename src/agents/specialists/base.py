"""
Base specialist — abstract agent that all 11 department specialists extend.
Handles: loading dept policy/leader, building prompts, calling LLM, parsing output.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from src.agency_registry import load_department_bundle
from src.llm import get_llm, FallbackLLM

logger = logging.getLogger(__name__)


class BaseSpecialist(ABC):
    """
    Abstract base for all department specialist agents.

    Each subclass must:
    1. Set `self.department` to its department key
    2. Implement `build_prompt()` to return the specialist's system prompt
    3. Optionally override `parse_output()` for custom parsing
    """

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
            logger.error(f"Failed to load bundle for {self.department}: {exc}")
            self._bundle = {}

    # ── Prompt building ────────────────────────────────────────────────

    @abstractmethod
    def build_system_prompt(self) -> str:
        """
        Return the system prompt that defines this specialist's role,
        responsibilities, and output format.
        """
        ...

    def build_user_prompt(
        self,
        state: dict[str, Any],
    ) -> str:
        """
        Build the user-facing prompt with task context.
        Override in subclass for custom formatting.
        """
        task_desc = state.get("task_description", "")
        policy = state.get("policy", {})
        research = state.get("research_results", {})
        feedback = state.get("leader_feedback", "")

        required_inputs = ", ".join(policy.get("required_inputs", []))
        expected_outputs = ", ".join(policy.get("expected_outputs", []))
        sla = policy.get("sla_hours", "?")

        synthesis = research.get("search_synthesis", "(no research data)")
        search_results = research.get("search_results", [])
        search_refs = "\n".join(f"[{i+1}] {r['title']} — {r['url']}" for i, r in enumerate(search_results[:5]))

        prompt = f"""## TASK
{task_desc}

## POLICY CONTEXT
- From: {policy.get('from_department', '?')} → To: {policy.get('to_department', '?')}
- Required inputs: {required_inputs}
- Expected outputs: {expected_outputs}
- SLA: {sla}h

## RESEARCH DATA
{synthesis}

{f"## PREVIOUS FEEDBACK (from leader, must address):\n{feedback}\n" if feedback else ""}
{f"## RESEARCH REFERENCES:\n{search_refs}\n" if search_refs else ""}

## YOUR TASK
As the {self.department.replace('_', ' ').title()} Specialist, produce the expected outputs.
Follow the output format specified in your system prompt.
Be specific, actionable, and aligned with the research data above.
{f"\nIMPORTANT: Address the following feedback from the leader reviewer:\n{feedback}" if feedback else ""}
"""
        return prompt

    # ── Output parsing ─────────────────────────────────────────────────

    def parse_output(self, raw_text: str, state: dict[str, Any]) -> dict[str, Any]:
        """
        Parse LLM raw output into a structured dict keyed by expected_outputs.
        Default implementation returns a simple dict.
        Override in subclass for custom parsing.
        """
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
            rf"(?i)^{section_name}[\s:\-]+(.+?)(?=\n[A-Z]|\Z)",  # SECTION_NAME: content
            rf"(?i)^\*\**{section_name}\*\*\*[\s:\-]*(.+?)(?=\n\*\*\*|\Z)",  # ***Section***
            rf"(?i)^{section_name.replace('_', ' ')}[\s:\-]+(.+?)(?=\n[A-Z]|\Z)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return text.strip()  # fallback: return whole text

    # ── Generation ─────────────────────────────────────────────────────

    def generate(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Main entry point — calls LLM and returns structured outputs.
        """
        system = self.build_system_prompt()
        user = self.build_user_prompt(state)

        try:
            llm = self._llm or get_llm()
            raw = llm.complete(
                prompt=user,
                system=system,
                temperature=0.7,
                max_tokens=4096,
            )
            structured = self.parse_output(raw, state)
            logger.info(
                f"[{self.department}] Specialist generated outputs: "
                f"{list(structured.keys())}"
            )
            return {
                "specialist_output": raw,
                "generated_outputs": structured,
            }
        except Exception as exc:
            logger.exception(f"[{self.department}] Specialist failed: {exc}")
            return {
                "specialist_output": "",
                "generated_outputs": {},
                "errors": [f"[{self.department}] Specialist error: {exc}"],
            }

    # ── Registry access helpers ────────────────────────────────────────

    @property
    def leader(self) -> Any:
        return self._bundle.get("leader")

    @property
    def employees(self) -> list[Any]:
        return self._bundle.get("employees", [])

    @property
    def policy(self) -> dict[str, Any]:
        return self._bundle.get("policy", {})
