"""
Task Planner node — expands a high-level business brief into
an ordered sequence of inter-department handoff steps.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgenticState
from src.llm import get_llm
from src.utils.json_utils import extract_first_json_object

logger = logging.getLogger(__name__)

# ── Built-in task-type templates ──────────────────────────────────

TASK_TEMPLATES: dict[str, dict[str, Any]] = {
    "new_campaign": {
        "name": "New Campaign Launch",
        "description": "Full agency campaign from brief to execution",
        "default_threshold": 98.0,
        "steps": [
            {
                "name": "Lead Qualification",
                "from_department": "sales",
                "to_department": "account",
                "required_inputs": ["lead_profile", "deal_status", "target_kpi"],
                "expected_outputs": ["project_brief", "kickoff_schedule"],
                "objective": "Qualify the lead and create a project brief",
                "quality_threshold": 98.0,
            },
            {
                "name": "Strategy Development",
                "from_department": "account",
                "to_department": "strategy",
                "required_inputs": ["project_brief", "client_constraints", "budget"],
                "expected_outputs": ["strategy_direction", "funnel_plan"],
                "objective": "Develop the campaign strategy and funnel plan",
                "quality_threshold": 98.0,
            },
            {
                "name": "Creative Production",
                "from_department": "strategy",
                "to_department": "creative",
                "required_inputs": ["strategy_direction", "key_message", "persona"],
                "expected_outputs": ["creative_concept", "content_plan"],
                "objective": "Create creative assets and content plan",
                "quality_threshold": 98.0,
            },
            {
                "name": "Media Planning",
                "from_department": "strategy",
                "to_department": "media",
                "required_inputs": ["funnel_plan", "audience_hypothesis", "budget"],
                "expected_outputs": ["media_plan", "channel_split"],
                "objective": "Plan media channels and budget allocation",
                "quality_threshold": 98.0,
            },
        ],
    },
    "data_report": {
        "name": "Data Report Generation",
        "description": "Generate periodic performance reports",
        "default_threshold": 98.0,
        "steps": [
            {
                "name": "Data Collection & Analysis",
                "from_department": "media",
                "to_department": "data",
                "required_inputs": ["ad_spend_log", "platform_raw_data"],
                "expected_outputs": ["raw_media_dataset", "performance_dashboard"],
                "objective": "Collect and analyze campaign data",
                "quality_threshold": 98.0,
            },
            {
                "name": "Insight Reporting",
                "from_department": "data",
                "to_department": "account",
                "required_inputs": ["weekly_metrics", "insights"],
                "expected_outputs": ["client_report"],
                "objective": "Compile insights into a client-ready report",
                "quality_threshold": 98.0,
            },
        ],
    },
    "retention_campaign": {
        "name": "CRM Retention Campaign",
        "description": "Run a retention/CRM automation campaign",
        "default_threshold": 98.0,
        "steps": [
            {
                "name": "Segment & Automate",
                "from_department": "data",
                "to_department": "crm_automation",
                "required_inputs": ["customer_segments", "behavior_events"],
                "expected_outputs": ["trigger_rules", "segment_definition"],
                "objective": "Define customer segments and automation triggers",
                "quality_threshold": 98.0,
            },
            {
                "name": "Retention Media Brief",
                "from_department": "crm_automation",
                "to_department": "media",
                "required_inputs": ["retention_audience", "lifecycle_offer"],
                "expected_outputs": ["remarketing_brief"],
                "objective": "Create a media brief for retention campaign",
                "quality_threshold": 98.0,
            },
        ],
    },
    "creative_brief": {
        "name": "Creative Brief Only",
        "description": "Generate creative assets for an existing strategy",
        "default_threshold": 98.0,
        "steps": [
            {
                "name": "Creative Production",
                "from_department": "strategy",
                "to_department": "creative",
                "required_inputs": ["strategy_direction", "key_message", "persona"],
                "expected_outputs": ["creative_concept", "content_plan"],
                "objective": "Produce creative concepts and content plan",
                "quality_threshold": 98.0,
            },
        ],
    },
}


SYSTEM_PROMPT = """You are the Agency Task Planner. Your job is to take a high-level
business brief and decompose it into an ordered sequence of inter-department
handoff steps.

You have access to these pre-defined task templates:
{template_names}

If the brief matches a template, use it.
If the brief is custom or partial, create an appropriate partial plan
(1-3 steps max for simple tasks, up to 6 for complex ones).
For each step, specify: name, from_department, to_department, required_inputs,
expected_outputs, objective, quality_threshold (default 98).

Return a JSON object:
{{
  "task_type": "<matched template name or 'custom'>",
  "planning_mode": "template" | "llm_generated" | "router_only",
  "steps": [
    {{
      "name": "...",
      "from_department": "...",
      "to_department": "...",
      "required_inputs": ["..."],
      "expected_outputs": ["..."],
      "objective": "...",
      "quality_threshold": 98.0
    }}
  ]
}}"""


def _match_template(task_desc: str) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Match task against built-in templates using weighted keyword scoring.

    Weights:
      - Action keywords (tao/generate/create → creative): 3pts
      - Department keywords (creative/media/strategy/data): 3pts
      - Output keywords (headline/copy/report/analysis): 2pts
      - Template name words: 1pt
      - Department codes in steps: 0.5pts
      - Generic "campaign": 0.25pts (low weight — common word)
    """
    desc_lower = task_desc.lower()

    # Action keyword → hint at creative work
    creative_action = any(w in desc_lower for w in [
        "tao", "tao", "viet", "generate", "create", "design",
        "headline", "copy", "ad copy", "banner", "content",
        "quang cao", "poster", "video script", "script",
    ])
    # Output keyword → hint at data/analytics work
    data_action = any(w in desc_lower for w in [
        "report", "phan tich", "analysis", "insight",
        "dashboard", "metrics", "performance", "so lieu",
        "bao cao", "chi so",
    ])
    # Retention/CRM keyword
    retention_action = any(w in desc_lower for w in [
        "retention", "loyalty", "winback", "email", "automation",
        "reminder", "khach hang cu", "previous customer",
    ])
    # Generic "new campaign" flag (low weight)
    is_new_campaign = any(w in desc_lower for w in [
        "new campaign", "chay campaign", "bat dau campaign",
        "ra mat campaign", "khoi dong",
    ])

    scores: dict[str, float] = {}

    for key, tmpl in TASK_TEMPLATES.items():
        score = 0.0

        # Template name words (baseline)
        name_words = tmpl["name"].lower().split()
        for word in name_words:
            if len(word) > 3 and word in desc_lower:
                score += 1.0

        # Department codes from steps
        for step in tmpl.get("steps", []):
            for dept in [step["from_department"], step["to_department"]]:
                if dept in desc_lower:
                    score += 0.5

        # Weighted keyword hints (these override the generic template score)
        if key == "creative_brief" and creative_action:
            score += 5.0
        if key == "new_campaign" and (creative_action or data_action or retention_action):
            # Don't penalize, but don't inflate either
            pass
        if key == "new_campaign" and is_new_campaign:
            score += 2.0
        if key == "data_report" and data_action:
            score += 5.0
        if key == "retention_campaign" and retention_action:
            score += 5.0

        if score > 0:
            scores[key] = score

    if not scores:
        return "custom", "router_only", []
    best = max(scores, key=lambda k: scores[k])
    tmpl = TASK_TEMPLATES[best]
    return best, "template", list(tmpl["steps"])


def _llm_generate_plan(task_desc: str, from_dept: str, to_dept: str) -> dict[str, Any]:
    """Use LLM to generate a custom multi-step plan."""
    llm = get_llm()
    if llm.primary_provider is None:
        return {"task_type": "custom", "planning_mode": "router_only", "steps": []}

    template_names = ", ".join(TASK_TEMPLATES.keys())
    user_prompt = f"""Business brief:
{task_desc}

{f"Constrained from: {from_dept}" if from_dept else ""}
{f"Constrained to: {to_dept}" if to_dept else ""}

{template_names}

Return ONLY JSON."""

    try:
        response = llm.complete(
            prompt=user_prompt,
            system=SYSTEM_PROMPT.format(template_names=template_names),
            temperature=0.3,
            max_tokens=1536,
        )
        return extract_first_json_object(response)
    except Exception as exc:
        logger.warning("Task planner LLM failed: %s", exc)
        return {"task_type": "custom", "planning_mode": "router_only", "steps": []}


def plan_task(state: AgenticState) -> AgenticState:
    """
    Task Planner node — builds an ordered task plan from the brief.
    Updates state with: task_type, task_plan, current_step, current_step_index.
    """
    task_desc = state.get("task_description", "")
    task_type_hint = state.get("task_type", "")
    from_dept = state.get("from_department", "").strip()
    to_dept = state.get("to_department", "").strip()
    errors: list[str] = list(state.get("errors", []))

    # 1. Template match first (fastest, deterministic)
    if task_type_hint and task_type_hint in TASK_TEMPLATES:
        matched_type = task_type_hint
        planning_mode = "template"
        steps = list(TASK_TEMPLATES[task_type_hint]["steps"])
        logger.info("Task planner: matched template '%s'", matched_type)
    else:
        matched_type, planning_mode, steps = _match_template(task_desc)

    # 2. If no template match and no explicit route, try LLM generation
    if planning_mode == "router_only" and not (from_dept and to_dept):
        logger.info("Task planner: generating plan via LLM for '%s'", task_desc[:60])
        llm_plan = _llm_generate_plan(task_desc, from_dept, to_dept)
        matched_type = llm_plan.get("task_type", "custom")
        planning_mode = llm_plan.get("planning_mode", "router_only")
        steps = llm_plan.get("steps", [])

    # 3. If still no steps (router_only or LLM failed), set up for single-step via router
    if not steps:
        planning_mode = "router_only"
        steps = []
        logger.info("Task planner: no plan generated — router will handle single-step")

    # Set first step
    first_step = steps[0] if steps else {}
    current_step_index = 0 if first_step else 0

    logger.info(
        "Task planner: type=%s mode=%s steps=%d",
        matched_type,
        planning_mode,
        len(steps),
    )

    return {
        **state,
        "task_type": matched_type,
        "task_plan": steps,
        "current_step_index": current_step_index,
        "current_step": first_step,
        "completed_steps": [],
        "planning_mode": planning_mode,
        "metadata": {
            **state.get("metadata", {}),
            "steps_count": len(steps),
        },
        "errors": errors,
    }
