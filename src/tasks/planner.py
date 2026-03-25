"""Business-task planning layer that turns one brief into many handoffs."""
from __future__ import annotations

from typing import Any

from models import HandoffPolicy
from src.policies.interdepartment_policies import POLICIES


def _find_policy(from_department: str, to_department: str) -> HandoffPolicy:
    for policy in POLICIES:
        if (
            policy.from_department == from_department
            and policy.to_department == to_department
        ):
            return policy
    raise ValueError(f"No policy found for {from_department}->{to_department}")


TASK_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "campaign_launch": [
        {
            "name": "Strategy Brief",
            "objective": "Turn the business brief into a strategic direction and funnel plan.",
            "route": ("account", "strategy"),
            "quality_threshold": 94.0,
        },
        {
            "name": "Creative Development",
            "objective": "Create concepts, messaging, and campaign assets from the strategy.",
            "route": ("strategy", "creative"),
            "quality_threshold": 95.0,
        },
        {
            "name": "Media Planning",
            "objective": "Translate the funnel plan into channels, pacing, and media allocation.",
            "route": ("strategy", "media"),
            "quality_threshold": 94.0,
        },
        {
            "name": "Launch Asset Packaging",
            "objective": "Prepare approved creative for media deployment and launch readiness.",
            "route": ("creative", "media"),
            "quality_threshold": 96.0,
        },
        {
            "name": "Client Launch Update",
            "objective": "Package the launch-ready plan and risks for the client-facing team.",
            "route": ("media", "account"),
            "quality_threshold": 98.0,
        },
    ],
    "campaign_optimization": [
        {
            "name": "Performance Diagnosis",
            "objective": "Analyze media performance and detect the highest-impact issues.",
            "route": ("media", "data"),
            "quality_threshold": 94.0,
        },
        {
            "name": "Optimization Plan",
            "objective": "Convert performance findings into concrete budget and channel actions.",
            "route": ("data", "media"),
            "quality_threshold": 95.0,
        },
        {
            "name": "Creative Refresh",
            "objective": "Generate new creative variants based on winners and underperformers.",
            "route": ("media", "creative"),
            "quality_threshold": 95.0,
        },
        {
            "name": "Relaunch Assets",
            "objective": "Return new assets to media for rollout in the next optimization cycle.",
            "route": ("creative", "media"),
            "quality_threshold": 96.0,
        },
        {
            "name": "Client Performance Update",
            "objective": "Summarize the optimization plan in client-ready language.",
            "route": ("media", "account"),
            "quality_threshold": 98.0,
        },
    ],
    "retention_program": [
        {
            "name": "Segment Discovery",
            "objective": "Find customer segments and behavior triggers that matter for retention.",
            "route": ("data", "crm_automation"),
            "quality_threshold": 94.0,
        },
        {
            "name": "Remarketing Brief",
            "objective": "Turn lifecycle triggers into remarketing and retention actions.",
            "route": ("crm_automation", "media"),
            "quality_threshold": 95.0,
        },
        {
            "name": "Client Retention Update",
            "objective": "Prepare a client-facing update on retention performance and next actions.",
            "route": ("crm_automation", "account"),
            "quality_threshold": 98.0,
        },
    ],
    "client_reporting": [
        {
            "name": "Data Story",
            "objective": "Convert metrics and anomalies into an insight-led report package.",
            "route": ("data", "account"),
            "quality_threshold": 97.0,
        },
    ],
}


def list_available_task_types() -> list[str]:
    return sorted(TASK_TEMPLATES)


def detect_task_type(task_description: str, from_department: str = "", to_department: str = "") -> str:
    text = f"{task_description} {from_department} {to_department}".lower()

    if any(keyword in text for keyword in ("retention", "crm", "lifecycle", "churn", "win-back")):
        return "retention_program"
    if any(keyword in text for keyword in ("report", "dashboard", "weekly update", "monthly review")):
        return "client_reporting"
    if any(keyword in text for keyword in ("optimize", "optimise", "roas", "performance", "scale", "pacing")):
        return "campaign_optimization"
    if any(keyword in text for keyword in ("campaign", "launch", "go live", "creative", "media plan", "strategy")):
        return "campaign_launch"
    return "ad_hoc"


def _policy_to_step(template_step: dict[str, Any]) -> dict[str, Any]:
    from_department, to_department = template_step["route"]
    policy = _find_policy(from_department, to_department)
    return {
        "name": template_step["name"],
        "objective": template_step["objective"],
        "from_department": policy.from_department,
        "to_department": policy.to_department,
        "required_inputs": list(policy.required_inputs),
        "expected_outputs": list(policy.expected_outputs),
        "sla_hours": policy.sla_hours,
        "approver_role": policy.approver_role,
        "quality_threshold": float(template_step["quality_threshold"]),
    }


def build_task_plan(
    task_description: str,
    *,
    from_department: str = "",
    to_department: str = "",
    task_type: str = "",
) -> dict[str, Any]:
    """Create a business-task plan for the graph to execute."""
    normalized_from = from_department.strip().lower()
    normalized_to = to_department.strip().lower()
    resolved_type = task_type or detect_task_type(
        task_description,
        from_department=normalized_from,
        to_department=normalized_to,
    )

    if normalized_from and normalized_to:
        policy = _find_policy(normalized_from, normalized_to)
        return {
            "task_type": resolved_type if resolved_type != "ad_hoc" else "single_route",
            "planning_mode": "single_route",
            "steps": [
                {
                    "name": f"{policy.from_department.title()} to {policy.to_department.title()}",
                    "objective": task_description,
                    "from_department": policy.from_department,
                    "to_department": policy.to_department,
                    "required_inputs": list(policy.required_inputs),
                    "expected_outputs": list(policy.expected_outputs),
                    "sla_hours": policy.sla_hours,
                    "approver_role": policy.approver_role,
                    "quality_threshold": 98.0,
                }
            ],
        }

    if resolved_type in TASK_TEMPLATES:
        return {
            "task_type": resolved_type,
            "planning_mode": "template",
            "steps": [_policy_to_step(step) for step in TASK_TEMPLATES[resolved_type]],
        }

    return {
        "task_type": resolved_type,
        "planning_mode": "router_only",
        "steps": [],
    }
