"""
Content Agent — orchestrates the full content generation pipeline.

Pipeline: Plan → Generate → Validate → (await human approval) → Publish

This agent handles steps 1-3 (plan, generate, validate).
Publishing (step 4) is triggered separately via the /content/approve API
after human review on the dashboard.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from core.agents.base import BaseAgent
from core.agents.roles import ROLE_DEFINITIONS

logger = logging.getLogger("agents.content")


class ContentAgent(BaseAgent):
    """AI content generation agent."""

    _role = ROLE_DEFINITIONS.get("content-agent", {})
    description = _role.get("system_prompt", "Automated content generation agent")
    title = _role.get("title", "Content Agent")
    responsibilities = _role.get("responsibilities", [])
    agent_tools = _role.get("tools", [])
    kpis = _role.get("kpis", [])
    model = _role.get("model", "claude-sonnet-4-20250514")
    level = _role.get("level", "specialist")

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute content generation pipeline (plan → generate → validate).

        Does NOT publish — that requires human approval via dashboard.
        """
        context = task.get("context_json", {})
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except Exception:
                context = {}

        brand = context.get("brand", "bakudan")
        content_type = context.get("content_type", "menu")
        project_id = context.get("project_id", "BakudanWebsite_Sub")

        try:
            # Step 1: Plan topic
            from core.content.planner import ContentPlanner
            planner = ContentPlanner()
            topic = planner.plan_topic(brand, content_type, project_id)
            logger.info("Topic planned: %s", topic.get("title"))

            # Step 2: Generate HTML
            from core.content.generator import ContentGenerator
            generator = ContentGenerator()
            result = generator.generate(brand, project_id, topic)
            logger.info("Content generated: %s (%d words)", result["filename"], result["word_count"])

            # Step 3: Validate
            from core.content.validator import ContentValidator
            validator = ContentValidator()
            validation = validator.validate(result["html"], brand, project_id)
            logger.info("Validation: %d/%d checks passed", validation["passed_checks"], validation["total_checks"])

            # Save topic to history
            planner.save_to_history(topic)

            return {
                "status": "done",
                "topic": topic,
                "filename": result["filename"],
                "word_count": result["word_count"],
                "html": result["html"],
                "validation": validation,
                "ready_to_publish": validation["passed"],
                "brand": brand,
                "project_id": project_id,
                "message": (
                    f"Content ready for review: {topic['title']} "
                    f"({result['word_count']} words, {validation['passed_checks']}/{validation['total_checks']} checks)"
                    if validation["passed"]
                    else f"Content generated but validation failed: {validation['blocking_failures']}"
                ),
            }

        except Exception as exc:
            logger.exception("Content agent error: %s", exc)
            return {
                "status": "error",
                "error": str(exc),
                "brand": brand,
                "content_type": content_type,
            }
