"""
Agent Executor — the bridge between pending DB tasks and real LLM execution.

When the orchestrator picks up a task, the executor:
1. Loads the agent's role definition (system prompt, tools, KPIs)
2. Builds a structured prompt from the task context
3. Routes to the right LLM (Ollama for simple, Claude for complex)
4. Calls the LLM and parses the response
5. Saves the result back to the DB
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.agents.roles import ROLE_DEFINITIONS
from core.llm.router import LLMRouter

logger = logging.getLogger("orchestrator.executor")

# Shared router instance
_router = LLMRouter()


def get_router() -> LLMRouter:
    return _router


class AgentExecutor:
    """Executes tasks by calling LLMs with role-specific prompts."""

    def __init__(self, router: LLMRouter | None = None):
        self.router = router or _router

    def execute(self, task: dict, role_key: str | None = None) -> dict:
        """Execute a task using the appropriate agent role and LLM.

        Args:
            task: Task dict from DB (id, title, description, assigned_agent_id, context_json, etc.)
            role_key: Override role key. Defaults to task["assigned_agent_id"].

        Returns:
            {"status": "success"|"error", "output": str, "provider": str, "tokens_est": int}
        """
        agent_id = role_key or task.get("assigned_agent_id", "workflow")
        role = ROLE_DEFINITIONS.get(agent_id, {})

        if not role:
            logger.warning("No role definition for agent %s", agent_id)
            return {"status": "error", "output": f"No role definition for {agent_id}", "provider": "none"}

        # Build prompts
        system_prompt = self._build_system_prompt(role)
        user_prompt = self._build_user_prompt(task, role)

        # Route to LLM
        task_type = task.get("task_type", "default")
        description = task.get("description", task.get("title", ""))
        provider = self.router.route(task_type, description)

        if provider == "none":
            # Rule-based: return a structured response without LLM
            return self._rule_based_execute(task, role)

        # Call LLM
        logger.info("Executing task %s via %s (agent: %s)", task.get("id", "?")[:8], provider, agent_id)

        result = self.router.complete(
            prompt=user_prompt,
            system=system_prompt,
            task_type=task_type,
            description=description,
            max_tokens=4096,
            temperature=0.7,
        )

        if result.startswith("[LLM Error]"):
            return {"status": "error", "output": result, "provider": provider, "tokens_est": 0}

        return {
            "status": "success",
            "output": result,
            "provider": provider,
            "tokens_est": len(result) // 4,
            "agent_id": agent_id,
            "agent_title": role.get("title", agent_id),
        }

    def _build_system_prompt(self, role: dict) -> str:
        """Build a comprehensive system prompt from the role definition."""
        parts = [role.get("system_prompt", "You are a helpful assistant.")]

        responsibilities = role.get("responsibilities", [])
        if responsibilities:
            parts.append("\n\nYour key responsibilities:")
            for r in responsibilities:
                parts.append(f"- {r}")

        tools = role.get("tools", [])
        if tools:
            parts.append(f"\n\nAvailable tools: {', '.join(tools)}")

        kpis = role.get("kpis", [])
        if kpis:
            parts.append(f"\n\nYour KPIs: {', '.join(kpis)}")

        parts.append("\n\nRespond with actionable, structured output. Be specific and professional.")
        return "\n".join(parts)

    def _build_user_prompt(self, task: dict, role: dict) -> str:
        """Build the user prompt from task details."""
        parts = []

        title = task.get("title", "Untitled task")
        parts.append(f"## Task: {title}")

        description = task.get("description", "")
        if description:
            parts.append(f"\n### Description:\n{description}")

        # Include context
        context = task.get("context_json", {})
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except (json.JSONDecodeError, TypeError):
                context = {}

        if context.get("original_request"):
            parts.append(f"\n### Original Request:\n{context['original_request']}")

        if context.get("phase_name"):
            parts.append(f"\n### Phase: {context['phase_name']} (Phase {context.get('phase', '?')})")

        if context.get("project_id"):
            parts.append(f"\n### Project: {context['project_id']}")

        parts.append("\n### Instructions:")
        parts.append("Please provide a detailed, actionable response for this task.")
        parts.append("Structure your response with clear sections and specific recommendations.")

        return "\n".join(parts)

    def _rule_based_execute(self, task: dict, role: dict) -> dict:
        """Handle simple rule-based tasks without LLM."""
        title = task.get("title", "")
        description = task.get("description", "")

        # Generate a structured response based on task type
        output = (
            f"## Task Completed (Rule-based)\n\n"
            f"**Agent:** {role.get('title', 'Unknown')}\n"
            f"**Task:** {title}\n\n"
            f"This task was handled via rule-based execution (no LLM required).\n"
            f"Action taken: Processed '{description[:100]}'"
        )

        return {
            "status": "success",
            "output": output,
            "provider": "none",
            "tokens_est": 0,
            "agent_id": task.get("assigned_agent_id", ""),
            "agent_title": role.get("title", ""),
        }
