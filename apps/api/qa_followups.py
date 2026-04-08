from __future__ import annotations

from typing import Any


def _agent_for_category(category: str, kind: str) -> str:
    if category == "ui":
        return "dept-creative" if kind in {"next_frontend", "static_site", "php_app", "cloudflare_pages"} else "dev-agent"
    if category == "workflow":
        return "dev-agent" if kind in {"next_frontend", "php_app", "python_service", "cloudflare_pages", "mcp_service"} else "dept-operations"
    if category == "features":
        return "dept-tech" if kind in {"python_service", "mcp_service"} else "dev-agent"
    return "dev-agent"


def build_live_qa_fix_plan(
    project: dict[str, Any],
    qa_result: dict[str, Any],
    *,
    max_retest_cycles: int = 5,
) -> dict[str, Any]:
    kind = (project.get("ops_profile") or {}).get("kind") or "generic"
    findings = list(qa_result.get("findings") or [])
    if not findings:
        findings = [
            {
                "category": "workflow",
                "severity": "medium",
                "title": "Live QA needs manual remediation planning",
                "detail": qa_result.get("summary") or "The live run failed to meet the release threshold.",
            }
        ]

    goal_title = f"[{project['id']}] Live QA remediation loop"
    goal_description = (
        f"Bring {project['name']} above the live QA gate. Latest score: {qa_result.get('final_score', 0):.2f}/10. "
        f"Auto-retest should stop after {max_retest_cycles} failed cycle(s) and escalate to CEO if still below threshold."
    )

    task_specs: list[dict[str, Any]] = []
    for index, finding in enumerate(findings[:5], start=1):
        category = finding.get("category") or "workflow"
        agent_id = _agent_for_category(category, kind)
        task_specs.append(
            {
                "title": f"[{project['id']}] Fix {category} finding {index}",
                "assigned_agent_id": agent_id,
                "description": (
                    f"Investigate and fix the live QA finding for {project['name']}: "
                    f"{finding.get('title')}. {finding.get('detail')}"
                ),
                "task_type": "qa_live_fix",
                "priority": 3 if finding.get("severity") == "high" else 2,
                "context_json": {
                    "source": "qa_live",
                    "project_id": project["id"],
                    "project_name": project["name"],
                    "category": category,
                    "finding": finding,
                    "pass_threshold": qa_result.get("pass_threshold", 8.5),
                    "timeout_ms": qa_result.get("timeout_ms", 15000),
                    "max_retest_cycles": max_retest_cycles,
                    "target_url": qa_result.get("target_url"),
                },
            }
        )

    task_specs.append(
        {
            "title": f"[{project['id']}] Coordinate QA remediation loop",
            "assigned_agent_id": "dept-operations",
            "description": (
                f"Coordinate department handoff, verify the fix package, and release the project back to live QA "
                f"once the remediation tasks for {project['name']} are complete."
            ),
            "task_type": "qa_live_coordination",
            "priority": 2,
            "context_json": {
                "source": "qa_live",
                "project_id": project["id"],
                "project_name": project["name"],
                "pass_threshold": qa_result.get("pass_threshold", 8.5),
                "timeout_ms": qa_result.get("timeout_ms", 15000),
                "max_retest_cycles": max_retest_cycles,
                "finding_count": len(task_specs),
                "target_url": qa_result.get("target_url"),
                "summary": qa_result.get("summary"),
            },
        }
    )

    return {
        "goal_title": goal_title,
        "goal_description": goal_description,
        "tasks": task_specs,
    }


def create_live_qa_followup_tasks(
    db: Any,
    project: dict[str, Any],
    qa_result: dict[str, Any],
    *,
    goal_id: str | None = None,
    max_retest_cycles: int = 5,
) -> dict[str, Any]:
    max_retest_cycles = max(1, int(max_retest_cycles))
    plan = build_live_qa_fix_plan(project, qa_result, max_retest_cycles=max_retest_cycles)
    goal = db.get_goal(goal_id) if goal_id else None
    if not goal:
        goal = db.create_goal(
            title=plan["goal_title"],
            description=plan["goal_description"],
            owner="workflow",
        )

    created_tasks = []
    for spec in plan["tasks"]:
        created = db.create_task(
            title=spec["title"],
            assigned_agent_id=spec["assigned_agent_id"],
            goal_id=goal["id"],
            description=spec["description"],
            task_type=spec["task_type"],
            priority=spec["priority"],
            context_json=spec["context_json"],
        )
        created_tasks.append(db.get_task(created["id"]) or created)

    return {"goal": db.get_goal(goal["id"]) or goal, "tasks": created_tasks}


def create_live_qa_ceo_escalation(
    db: Any,
    project: dict[str, Any],
    qa_result: dict[str, Any],
    *,
    goal_id: str,
    retest_attempt: int,
    max_retest_cycles: int,
) -> dict[str, Any]:
    existing = [
        task
        for task in db.list_tasks_by_goal(goal_id)
        if task.get("task_type") == "qa_live_escalation"
    ]
    if existing:
        latest = existing[-1]
        return {"goal": db.get_goal(goal_id), "task": latest}

    created = db.create_task(
        title=f"[{project['id']}] Escalate live QA loop to CEO",
        assigned_agent_id="workflow",
        goal_id=goal_id,
        description=(
            f"Live QA for {project['name']} is still below threshold after {retest_attempt}/{max_retest_cycles} "
            f"automatic retest cycle(s). Review the findings, approve a direction, and decide whether to pause, "
            f"fund, or redirect the release."
        ),
        task_type="qa_live_escalation",
        priority=4,
        context_json={
            "source": "qa_live",
            "project_id": project["id"],
            "project_name": project["name"],
            "retest_attempt": retest_attempt,
            "max_retest_cycles": max_retest_cycles,
            "pass_threshold": qa_result.get("pass_threshold", 8.5),
            "final_score": qa_result.get("final_score"),
            "findings": qa_result.get("findings") or [],
            "summary": qa_result.get("summary"),
            "target_url": qa_result.get("target_url"),
        },
    )
    return {"goal": db.get_goal(goal_id), "task": db.get_task(created["id"]) or created}
