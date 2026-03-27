"""
Score Engine — LLM-powered rubric scoring.
Evaluates specialist output against department rubric criteria and returns a 0-100 score.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.llm import get_llm
from src.scoring.rubric_registry import RubricRegistry, get_rubric

logger = logging.getLogger(__name__)

SCORE_PROMPT_TEMPLATE = """You are a quality reviewer scoring specialist output against a rubric.

Department: {department}
Task Type: {task_type}
Output Under Review:
---
{output}
---

Rubric Criteria:
{criteria_text}

Score each criterion honestly from 0-100 based on the checklist.
Return ONLY a JSON object (no markdown, no explanation outside the JSON):
{{
  "scores": {{
    "completeness": {{"score": 0-100, "notes": "brief justification"}},
    "accuracy": {{"score": 0-100, "notes": "brief justification"}},
    "actionability": {{"score": 0-100, "notes": "brief justification"}},
    "professional_quality": {{"score": 0-100, "notes": "brief justification"}}
  }},
  "overall_score": 0-100,
  "summary": "1-2 sentence overall assessment",
  "checklist_results": {{"item": true/false}}
}}
"""


class ScoreEngine:
    """
    Score specialist output using LLM + rubric.

    Falls back to heuristic scoring if LLM is unavailable.
    """

    def __init__(self, rubric_registry: Optional[RubricRegistry] = None) -> None:
        self._registry = rubric_registry or RubricRegistry()

    def score(
        self,
        department: str,
        output: str,
        task_type: str = "ad_hoc",
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Score output against department rubric.

        Returns dict:
            {
              "overall_score": float (0-100),
              "criteria_scores": dict,
              "breakdown": dict (per-criterion scores),
              "checklist_results": dict,
              "summary": str,
              "scoring_method": "llm" | "heuristic",
            }
        """
        rubric = self._registry.get(department)

        # Try LLM scoring
        try:
            result = self._llm_score(rubric, output, task_type)
            if result:
                return result
        except Exception as exc:
            logger.warning("LLM scoring failed, falling back to heuristic: %s", exc)

        # Fallback: heuristic scoring
        return self._heuristic_score(rubric, output)

    def _llm_score(
        self,
        rubric,
        output: str,
        task_type: str,
    ) -> Optional[dict[str, Any]]:
        """Use LLM to score against rubric."""
        llm = get_llm()
        if llm.primary_provider is None:
            return None

        # Build criteria text
        criteria_parts = []
        for c in rubric.criteria:
            items = "\n".join(f"  - {i}" for i in c.checklist)
            criteria_parts.append(
                f"[{c.name}] (weight={c.weight})\n  Checklist:\n{items}"
            )
        criteria_text = "\n\n".join(criteria_parts)

        prompt = SCORE_PROMPT_TEMPLATE.format(
            department=rubric.department,
            task_type=task_type,
            output=output[:8000],  # token safety
            criteria_text=criteria_text,
        )

        response = llm.complete(
            prompt=prompt,
            system="You are a rigorous quality reviewer. Score honestly. Return ONLY valid JSON.",
            temperature=0.0,  # deterministic scoring (RISK-009)
            max_tokens=2048,
        )

        from src.utils.json_utils import extract_first_json_object
        parsed = extract_first_json_object(response)
        if not parsed:
            return None

        # Validate structure
        scores = parsed.get("scores", {})
        breakdown = {k: v.get("score", 0) for k, v in scores.items()}
        overall = parsed.get("overall_score", self._weighted_score(rubric, breakdown))

        return {
            "overall_score": float(overall),
            "criteria_scores": scores,
            "breakdown": breakdown,
            "checklist_results": parsed.get("checklist_results", {}),
            "summary": parsed.get("summary", ""),
            "scoring_method": "llm",
        }

    def _weighted_score(self, rubric, breakdown: dict[str, float]) -> float:
        """Compute weighted average from criteria breakdown."""
        total = 0.0
        for c in rubric.criteria:
            total += breakdown.get(c.name, 0) * c.weight
        return round(total, 1)

    def _heuristic_score(self, rubric, output: str) -> dict[str, Any]:
        """
        Fallback scoring without LLM.
        Uses structural heuristics: line count, section presence, formatting.
        Also checks content density to penalize formatted garbage.
        """
        text = output or ""
        lines = text.strip().split("\n")
        line_count = len(lines)
        words = text.split()
        word_count = len(words)

        # ── Content density check (anti-garbage) ──────────────────────
        # Low unique-word ratio indicates repetitive/filler text
        unique_words = set(w.lower().strip(".,;:!?()[]{}\"'") for w in words if len(w) > 2)
        unique_ratio = len(unique_words) / max(word_count, 1)
        is_low_density = unique_ratio < 0.20 and word_count > 50  # <20% unique = likely garbage

        # Check if rubric checklist keywords appear in output
        checklist_keywords = set()
        for c in rubric.criteria:
            for item in c.checklist:
                # Extract meaningful words from checklist items
                for word in item.lower().split():
                    if len(word) > 4:
                        checklist_keywords.add(word)
        text_lower = text.lower()
        keyword_hits = sum(1 for kw in checklist_keywords if kw in text_lower)
        keyword_coverage = keyword_hits / max(len(checklist_keywords), 1)

        # Check for section headers (markdown or numbered)
        section_markers = ["##", "###", "**", "1.", "2.", "3.", "4.", "5."]
        sections_found = sum(1 for m in section_markers if m in text)

        # ── Score each criterion heuristically ────────────────────────
        scores: dict[str, dict[str, Any]] = {}

        # Completeness: based on length + section coverage + checklist keyword presence
        if line_count >= 30 and sections_found >= 4:
            completeness_score = 85.0
        elif line_count >= 15 and sections_found >= 2:
            completeness_score = 65.0
        else:
            completeness_score = 40.0
        # Bonus/penalty for checklist keyword coverage
        completeness_score += keyword_coverage * 10  # up to +10 for matching rubric keywords
        if is_low_density:
            completeness_score -= 20  # penalize filler text
        completeness_score = max(0.0, min(100.0, completeness_score))
        scores["completeness"] = {
            "score": completeness_score,
            "notes": f"Lines={line_count}, sections={sections_found}, keyword_coverage={keyword_coverage:.0%}, density={'LOW' if is_low_density else 'ok'}",
        }

        # Accuracy: structural consistency
        accuracy_score = 75.0  # neutral default
        if "TBD" in text or "[INSERT" in text or "..." in text:
            accuracy_score -= 15
        if "%" in text and "$" in text:
            accuracy_score += 5  # concrete figures
        if is_low_density:
            accuracy_score -= 15  # repetitive text likely inaccurate
        scores["accuracy"] = {
            "score": max(0.0, min(100.0, accuracy_score)),
            "notes": f"Heuristic: format consistency + placeholder check, density={'LOW' if is_low_density else 'ok'}",
        }

        # Actionability: presence of numbers, dates, names (specificity markers)
        specificity_markers = ["$", "%", "202", "2025", "2026", "Q1", "Q2", "https://", "@"]
        specificity = sum(1 for m in specificity_markers if m in text)
        if specificity >= 3:
            actionability_score = 80.0
        elif specificity >= 1:
            actionability_score = 60.0
        else:
            actionability_score = 45.0
        if is_low_density:
            actionability_score -= 15
        actionability_score = max(0.0, min(100.0, actionability_score))
        scores["actionability"] = {
            "score": actionability_score,
            "notes": f"Concrete detail markers: {specificity}/10",
        }

        # Professional quality: formatting consistency
        professional_score = 70.0
        if "```" in text or "|" in text:  # code/table formatting
            professional_score += 10
        if any(text.startswith(f"{m} ") for m in ["-", "*", "1."]):
            professional_score += 5
        if text.count("\n\n") > 3:
            professional_score += 5
        if is_low_density:
            professional_score -= 15
        professional_score = max(0.0, min(100.0, professional_score))
        scores["professional_quality"] = {
            "score": professional_score,
            "notes": f"Heuristic: formatting + structure, density={'LOW' if is_low_density else 'ok'}",
        }

        breakdown = {k: v["score"] for k, v in scores.items()}
        overall = self._weighted_score(rubric, breakdown)

        return {
            "overall_score": round(overall, 1),
            "criteria_scores": scores,
            "breakdown": breakdown,
            "checklist_results": {},
            "summary": f"Heuristic score: {overall:.0f}/100 (LLM unavailable). Length: {word_count} words, {line_count} lines.",
            "scoring_method": "heuristic",
        }

    def score_with_context(
        self,
        department: str,
        output: str,
        task_type: str,
        memory_context: str = "",
        external_context: str = "",
    ) -> dict[str, Any]:
        """Score output while injecting prior context into the prompt."""
        enriched_output = output
        if memory_context or external_context:
            enriched_output = (
                f"{memory_context}\n\n---\n{external_context}\n\n---\nOUTPUT TO SCORE:\n---\n{output}"
            )
        return self.score(department, enriched_output, task_type)
