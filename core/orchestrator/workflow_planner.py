"""
Workflow Planner — analyzes natural language requests and creates
multi-department task plans like a real company would.

Flow: User request → Analyze → Create Goal → Create sub-tasks for each department
      with dependencies, budgets, and timelines.

This is the BRAIN that turns "I need a sushi promotion for April" into:
  1. Strategy: Research market + competitors
  2. Data: Pull current menu performance + sales data
  3. Finance: Analyze ad budget + recommend allocation
  4. Creative: Design promotional content
  5. Media: Plan ad campaign across channels
  6. Account: Create client-facing timeline
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from core.agents.roles import ROLE_DEFINITIONS

# ── Keywords → Department mapping ─────────────────────────────────────

ROUTING_RULES = [
    {
        "agent": "dept-strategy",
        "keywords": ["strategy", "research", "competitor", "market", "persona", "funnel", "position", "trend", "analysis"],
        "triggers": ["need a plan", "campaign idea", "how to promote", "marketing strategy"],
        "phase": 1,
        "phase_name": "Research & Strategy",
    },
    {
        "agent": "dept-data",
        "keywords": ["data", "analytics", "metrics", "performance", "report", "dashboard", "sales data", "revenue", "kpi"],
        "triggers": ["how is it selling", "current numbers", "performance data"],
        "phase": 1,
        "phase_name": "Data Analysis",
    },
    {
        "agent": "dept-finance",
        "keywords": ["budget", "cost", "spend", "roi", "roas", "money", "price", "allocat", "financial", "invoice", "billing", "fee"],
        "triggers": ["how much to spend", "budget for", "cost breakdown", "allocate budget"],
        "phase": 1,
        "phase_name": "Budget & Finance",
    },
    {
        "agent": "dept-creative",
        "keywords": ["creative", "design", "post", "content", "copy", "visual", "banner", "video", "photo", "blog", "seo", "caption", "ad copy"],
        "triggers": ["create a post", "write content", "design banner", "make video", "need creative"],
        "phase": 2,
        "phase_name": "Creative Production",
    },
    {
        "agent": "dept-media",
        "keywords": ["media", "ads", "campaign", "advertis", "facebook", "google ads", "instagram", "tiktok", "paid", "impressions", "cpc", "cpm"],
        "triggers": ["run ads", "ad campaign", "boost post", "promote on"],
        "phase": 2,
        "phase_name": "Media Planning",
    },
    {
        "agent": "dept-production",
        "keywords": ["production", "shoot", "photo shoot", "video shoot", "filming", "edit", "post-production"],
        "triggers": ["need photos", "schedule shoot", "film this"],
        "phase": 2,
        "phase_name": "Content Production",
    },
    {
        "agent": "dept-sales",
        "keywords": ["sales", "lead", "prospect", "pitch", "deal", "close", "outreach", "cold call"],
        "triggers": ["find clients", "generate leads", "sales pitch"],
        "phase": 2,
        "phase_name": "Sales Outreach",
    },
    {
        "agent": "dept-crm_automation",
        "keywords": ["crm", "email", "automation", "loyalty", "referral", "newsletter", "follow-up", "drip", "sequence"],
        "triggers": ["send email", "email campaign", "loyalty program", "automate follow"],
        "phase": 3,
        "phase_name": "CRM & Automation",
    },
    {
        "agent": "dept-account",
        "keywords": ["client", "report", "proposal", "timeline", "scope", "brief", "sow", "deliverable"],
        "triggers": ["client report", "project timeline", "update client"],
        "phase": 3,
        "phase_name": "Account Management",
    },
    {
        "agent": "dept-tech",
        "keywords": ["tech", "website", "landing page", "deploy", "api", "tracking", "pixel", "code", "server", "bug", "fix"],
        "triggers": ["update website", "build landing page", "fix the"],
        "phase": 2,
        "phase_name": "Technical Implementation",
    },
    {
        "agent": "dept-operations",
        "keywords": ["operations", "process", "sla", "quality", "review", "approve", "coordinate"],
        "triggers": ["coordinate teams", "ensure quality"],
        "phase": 3,
        "phase_name": "Operations & QA",
    },
    {
        "agent": "connector-review",
        "keywords": ["review", "yelp", "google review", "reputation", "rating", "respond to review"],
        "triggers": ["check reviews", "reply to reviews", "reputation management"],
        "phase": 1,
        "phase_name": "Review Management",
    },
    {
        "agent": "connector-marketing",
        "keywords": ["marketing site", "website content", "site update"],
        "triggers": ["update marketing site"],
        "phase": 3,
        "phase_name": "Marketing Site Sync",
    },
]

# ── Common workflow templates ─────────────────────────────────────────

WORKFLOW_TEMPLATES = {
    "promotion": {
        "name": "Promotional Campaign",
        "description": "Full promotion workflow: research → budget → creative → media → launch",
        "agents": [
            ("dept-strategy", 1, "Research market trends, competitor promotions, and target audience for this campaign"),
            ("dept-data", 1, "Pull current sales data, menu performance, and customer demographics"),
            ("dept-finance", 1, "Analyze available ad budget, recommend allocation across channels, create cost breakdown"),
            ("dept-creative", 2, "Create promotional content: social posts, ad copy, banners, email templates"),
            ("dept-media", 2, "Plan paid ad campaign: channel selection, audience targeting, budget split, scheduling"),
            ("dept-production", 2, "Coordinate photo/video content production if needed"),
            ("dept-crm_automation", 3, "Set up email campaign and automation flows for the promotion"),
            ("dept-account", 3, "Create campaign timeline and progress report"),
        ],
    },
    "content": {
        "name": "Content Creation",
        "description": "Content workflow: research → create → review → publish",
        "agents": [
            ("dept-strategy", 1, "Research content topics, SEO keywords, and competitor content"),
            ("dept-creative", 2, "Write and design the content (posts, blogs, captions)"),
            ("dept-production", 2, "Produce visual assets (photos, videos) if needed"),
            ("dept-operations", 3, "Review content quality and brand compliance"),
        ],
    },
    "ads": {
        "name": "Ad Campaign",
        "description": "Paid advertising workflow: budget → creative → launch → optimize",
        "agents": [
            ("dept-finance", 1, "Review ad budget availability and recommend spend allocation"),
            ("dept-data", 1, "Analyze past campaign performance to inform strategy"),
            ("dept-strategy", 1, "Define targeting strategy and campaign objectives"),
            ("dept-creative", 2, "Create ad creative variants for A/B testing"),
            ("dept-media", 2, "Set up and launch campaigns across selected channels"),
            ("dept-data", 3, "Monitor performance and provide optimization recommendations"),
        ],
    },
    "review_management": {
        "name": "Review Response",
        "description": "Review management workflow: fetch → analyze → respond",
        "agents": [
            ("connector-review", 1, "Fetch and analyze recent reviews across all platforms"),
            ("dept-creative", 2, "Draft professional responses to reviews"),
            ("dept-account", 3, "Report review trends and sentiment to management"),
        ],
    },
    "website": {
        "name": "Website Update",
        "description": "Website workflow: plan → build → test → deploy",
        "agents": [
            ("dept-strategy", 1, "Define website update requirements and goals"),
            ("dept-tech", 2, "Implement technical changes and updates"),
            ("dept-creative", 2, "Create or update visual content and copy"),
            ("dept-operations", 3, "QA testing and deployment approval"),
        ],
    },
}


def _detect_template(text: str) -> str | None:
    """Detect which workflow template best matches the request."""
    text_lower = text.lower()

    # Check for promotion/campaign keywords
    promo_keywords = ["promot", "campaign", "quảng bá", "quảng cáo", "advertis", "boost", "launch"]
    if any(k in text_lower for k in promo_keywords):
        return "promotion"

    # Check for content keywords
    content_keywords = ["post", "blog", "content", "write", "bài viết", "bài post"]
    if any(k in text_lower for k in content_keywords):
        # If also has ad/budget keywords, it's a promotion not just content
        if any(k in text_lower for k in ["budget", "ads", "spend", "campaign"]):
            return "promotion"
        return "content"

    # Check for ad keywords
    ad_keywords = ["ads", "ad campaign", "facebook ads", "google ads", "paid"]
    if any(k in text_lower for k in ad_keywords):
        return "ads"

    # Check for review keywords
    review_keywords = ["review", "yelp", "google review", "reputation", "rating"]
    if any(k in text_lower for k in review_keywords):
        return "review_management"

    # Check for website keywords
    web_keywords = ["website", "landing page", "web update", "site"]
    if any(k in text_lower for k in web_keywords):
        return "website"

    return None


def _score_agents(text: str) -> list[dict]:
    """Score each agent's relevance to the request using keyword matching."""
    text_lower = text.lower()
    scored = []

    for rule in ROUTING_RULES:
        score = 0

        # Keyword matching
        for kw in rule["keywords"]:
            if kw in text_lower:
                score += 2

        # Trigger phrase matching (higher weight)
        for trigger in rule["triggers"]:
            if trigger in text_lower:
                score += 5

        if score > 0:
            role_def = ROLE_DEFINITIONS.get(rule["agent"], {})
            scored.append({
                "agent_id": rule["agent"],
                "title": role_def.get("title", rule["agent"]),
                "score": score,
                "phase": rule["phase"],
                "phase_name": rule["phase_name"],
            })

    # Sort by phase first, then score descending within phase
    scored.sort(key=lambda x: (x["phase"], -x["score"]))
    return scored


def plan_workflow(text: str, context: dict | None = None) -> dict:
    """
    Analyze a natural language request and create a multi-department workflow plan.

    Returns:
        {
            "template": "promotion" | "content" | ... | None,
            "template_name": "Promotional Campaign",
            "summary": "...",
            "phases": [
                {
                    "phase": 1,
                    "name": "Research & Planning",
                    "tasks": [
                        {"agent_id": "dept-strategy", "title": "...", "description": "...", "priority": 3},
                        ...
                    ]
                },
                ...
            ],
            "total_tasks": 8,
            "estimated_agents": 6,
        }
    """
    text_lower = text.lower()

    # 1. Try to match a template
    template_key = _detect_template(text)

    if template_key and template_key in WORKFLOW_TEMPLATES:
        template = WORKFLOW_TEMPLATES[template_key]

        # Build phases from template
        phases_map: dict[int, dict] = {}
        for agent_id, phase_num, task_desc in template["agents"]:
            if phase_num not in phases_map:
                phase_names = {1: "Research & Planning", 2: "Execution", 3: "Review & Launch"}
                phases_map[phase_num] = {
                    "phase": phase_num,
                    "name": phase_names.get(phase_num, f"Phase {phase_num}"),
                    "tasks": [],
                }

            role_def = ROLE_DEFINITIONS.get(agent_id, {})
            # Customize task description based on user's actual request
            customized_desc = f"{task_desc}. Context: {text}"

            phases_map[phase_num]["tasks"].append({
                "agent_id": agent_id,
                "agent_title": role_def.get("title", agent_id),
                "title": f"[{role_def.get('title', agent_id)}] {task_desc.split('.')[0]}",
                "description": customized_desc,
                "priority": 3 if phase_num == 1 else 2,
                "tools": role_def.get("tools", []),
                "kpis": role_def.get("kpis", []),
            })

        phases = [phases_map[k] for k in sorted(phases_map.keys())]
        total_tasks = sum(len(p["tasks"]) for p in phases)
        unique_agents = len(set(
            t["agent_id"] for p in phases for t in p["tasks"]
        ))

        return {
            "template": template_key,
            "template_name": template["name"],
            "summary": template["description"],
            "request": text,
            "phases": phases,
            "total_tasks": total_tasks,
            "estimated_agents": unique_agents,
        }

    # 2. Fallback: score agents by keyword matching
    scored = _score_agents(text)
    if not scored:
        # Default: route to CEO agent
        scored = [{
            "agent_id": "workflow",
            "title": "CEO Agent",
            "score": 1,
            "phase": 1,
            "phase_name": "General Processing",
        }]

    # Group into phases
    phases_map: dict[int, dict] = {}
    for item in scored:
        phase_num = item["phase"]
        if phase_num not in phases_map:
            phase_names = {1: "Research & Planning", 2: "Execution", 3: "Review & Launch"}
            phases_map[phase_num] = {
                "phase": phase_num,
                "name": phase_names.get(phase_num, f"Phase {phase_num}"),
                "tasks": [],
            }

        role_def = ROLE_DEFINITIONS.get(item["agent_id"], {})
        phases_map[phase_num]["tasks"].append({
            "agent_id": item["agent_id"],
            "agent_title": item["title"],
            "title": f"[{item['title']}] Handle: {text[:60]}",
            "description": f"{item['phase_name']} — {text}",
            "priority": 3 if phase_num == 1 else 2,
            "tools": role_def.get("tools", []),
            "kpis": role_def.get("kpis", []),
        })

    phases = [phases_map[k] for k in sorted(phases_map.keys())]
    total_tasks = sum(len(p["tasks"]) for p in phases)
    unique_agents = len(set(t["agent_id"] for p in phases for t in p["tasks"]))

    return {
        "template": None,
        "template_name": "Custom Workflow",
        "summary": f"Auto-routed workflow with {unique_agents} agents across {len(phases)} phases",
        "request": text,
        "phases": phases,
        "total_tasks": total_tasks,
        "estimated_agents": unique_agents,
    }
