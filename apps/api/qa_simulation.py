from __future__ import annotations

import math
from typing import Any


_WEIGHTS = {
    "errors": 0.35,
    "ui": 0.20,
    "workflow": 0.20,
    "features": 0.25,
}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _kind_family(kind: str, meta: dict[str, Any]) -> str:
    if kind in {"next_frontend", "static_site"}:
        return "frontend"
    if kind in {"python_service", "mcp_service"}:
        return "backend"
    if kind == "cloudflare_pages":
        return "edge"
    if kind == "php_app":
        return "fullstack"
    return meta.get("type") or "generic"


def _department_plan(kind: str, category: str, tech: list[str]) -> list[dict[str, str]]:
    departments: list[dict[str, str]] = [
        {
            "department": "CEO Office",
            "mission": "Phan tich yeu cau, xac dinh muc tieu ban giao, va kich hoat vong hop tac lien phong ban.",
        },
        {
            "department": "Operations",
            "mission": "Chia viec, theo doi trang thai, va dieu phoi vong fix -> retest cho toi khi dat nguong.",
        },
    ]

    if kind in {"next_frontend", "static_site", "php_app"}:
        departments.append(
            {
                "department": "Design",
                "mission": "Ra soat giao dien, do nhat quan, kha nang su dung, va cac tinh huong responsive.",
            }
        )

    if kind in {"python_service", "mcp_service", "php_app", "cloudflare_pages"}:
        departments.append(
            {
                "department": "Engineering / IT",
                "mission": "Xu ly loi, on dinh workflow, va dam bao cac tinh nang cot loi van hanh dung.",
            }
        )

    if category in {"analytics", "operations", "reviews"} or any(
        item.lower() in {"sqlite", "postgresql", "mysql", "redis", "langgraph"} for item in tech
    ):
        departments.append(
            {
                "department": "Data / Analytics",
                "mission": "Kiem tra du lieu dau vao/dau ra, log, metric, va su dung feedback tester de uu tien fix.",
            }
        )

    if category in {"website", "reviews"}:
        departments.append(
            {
                "department": "Marketing",
                "mission": "Danh gia thong diep, hanh trinh nguoi dung, va muc do san sang ban giao cho user/admin.",
            }
        )

    departments.append(
        {
            "department": "Compliance / QA",
            "mission": "Tong hop report cua 1.000 tester, cham diem theo 4 tru cot, va quyet dinh pass/fail.",
        }
    )

    seen: set[str] = set()
    unique_departments: list[dict[str, str]] = []
    for item in departments:
        key = item["department"]
        if key in seen:
            continue
        seen.add(key)
        unique_departments.append(item)
    return unique_departments


def _pillar_scores(project: dict[str, Any]) -> dict[str, float]:
    ops_profile = project.get("ops_profile") or {}
    signals = ops_profile.get("signals") or []
    kind = ops_profile.get("kind") or "generic"
    family = _kind_family(kind, project)
    status = (project.get("status") or "").lower()

    error_count = sum(1 for item in signals if item.get("status") == "error")
    warning_count = sum(1 for item in signals if item.get("status") == "warning")
    ok_count = sum(1 for item in signals if item.get("status") == "ok")

    runtime_penalty = {
        "online": 0.0,
        "running": 0.1,
        "idle": 0.7,
        "warning": 1.0,
        "offline": 1.3,
    }.get(status, 0.9)

    dirty_penalty = 0.35 if project.get("dirty") else 0.0
    latency_penalty = 0.25 if (project.get("latency_ms") or 0) > 1200 else 0.0

    errors_score = 9.2 - runtime_penalty - (error_count * 0.55) - (warning_count * 0.18) - dirty_penalty - latency_penalty
    ui_score = 7.4
    if family in {"frontend", "fullstack"}:
        ui_score += 0.9
    if family == "edge":
        ui_score += 0.4
    ui_score -= error_count * 0.25
    ui_score -= warning_count * 0.16

    workflow_score = 7.7 + (0.35 if ok_count >= 2 else 0.0) - (error_count * 0.35) - (warning_count * 0.12)
    if status in {"online", "running"}:
        workflow_score += 0.55
    elif status == "offline":
        workflow_score -= 0.55

    feature_score = 7.9 + (0.25 if project.get("exists") else -0.8) + (0.15 if project.get("github") else 0.0)
    feature_score -= error_count * 0.28
    feature_score -= warning_count * 0.12

    return {
        "errors": _clamp(errors_score, 4.8, 9.3),
        "ui": _clamp(ui_score, 5.2, 9.2),
        "workflow": _clamp(workflow_score, 5.0, 9.35),
        "features": _clamp(feature_score, 5.0, 9.3),
    }


def _target_scores(initial: dict[str, float], departments: list[dict[str, str]], signals: list[dict[str, str]]) -> dict[str, float]:
    error_count = sum(1 for item in signals if item.get("status") == "error")
    warning_count = sum(1 for item in signals if item.get("status") == "warning")
    department_bonus = min(0.65, 0.12 + (len(departments) * 0.07))
    friction_penalty = min(0.5, error_count * 0.08 + warning_count * 0.03)
    return {
        key: _clamp(value + department_bonus - friction_penalty + 0.45, 6.5, 9.6)
        for key, value in initial.items()
    }


def _weighted_score(scores: dict[str, float]) -> float:
    return round(sum(scores[key] * weight for key, weight in _WEIGHTS.items()), 2)


def _grade(score: float) -> str:
    if score >= 9.2:
        return "excellent"
    if score >= 8.5:
        return "release_ready"
    if score >= 7.5:
        return "needs_polish"
    return "high_risk"


def _findings(project: dict[str, Any], initial_scores: dict[str, float]) -> list[dict[str, Any]]:
    ops_profile = project.get("ops_profile") or {}
    signals = ops_profile.get("signals") or []
    findings: list[dict[str, Any]] = []

    for signal in signals:
        status = signal.get("status")
        label = signal.get("label", "Signal")
        value = signal.get("value", "")
        if status == "error":
            findings.append(
                {
                    "category": "errors",
                    "severity": "high",
                    "title": f"{label} needs immediate attention",
                    "detail": value or "Core runtime or configuration signal failed.",
                }
            )
        elif status == "warning":
            category = "ui" if label.lower() in {"env template", "build cache", "seo asset", "entry page"} else "workflow"
            findings.append(
                {
                    "category": category,
                    "severity": "medium",
                    "title": f"{label} should be tightened before release",
                    "detail": value or "A warning signal may reduce tester confidence.",
                }
            )

    weakest = min(initial_scores, key=initial_scores.get)
    if weakest == "ui":
        findings.append(
            {
                "category": "ui",
                "severity": "medium",
                "title": "UI consistency still has visible drift",
                "detail": "Tester feedback expects clearer states, spacing, and less friction on primary flows.",
            }
        )
    elif weakest == "workflow":
        findings.append(
            {
                "category": "workflow",
                "severity": "medium",
                "title": "Workflow needs another stabilization pass",
                "detail": "Cross-step handoff and operational readiness should be verified before final sign-off.",
            }
        )
    elif weakest == "features":
        findings.append(
            {
                "category": "features",
                "severity": "medium",
                "title": "Feature coverage is not fully convincing yet",
                "detail": "Critical happy-path scenarios should be exercised again after the next fix package.",
            }
        )
    else:
        findings.append(
            {
                "category": "errors",
                "severity": "high",
                "title": "Defect density is still above release comfort",
                "detail": "Stability and edge-case handling should improve before the tester team signs off.",
            }
        )

    return findings[:6]


def simulate_project_qa_loop(
    project: dict[str, Any],
    *,
    goal: str = "",
    tester_count: int = 1000,
    max_iterations: int = 100,
    pass_threshold: float = 8.5,
) -> dict[str, Any]:
    tester_count = int(_clamp(float(tester_count), 50, 5000))
    max_iterations = int(_clamp(float(max_iterations), 1, 100))
    pass_threshold = _clamp(float(pass_threshold), 6.0, 9.8)

    ops_profile = project.get("ops_profile") or {}
    kind = ops_profile.get("kind") or "generic"
    departments = _department_plan(kind, project.get("category", ""), project.get("tech") or [])
    initial_scores = _pillar_scores(project)
    signals = ops_profile.get("signals") or []
    targets = _target_scores(initial_scores, departments, signals)
    findings = _findings(project, initial_scores)

    improvement_rate = min(0.26, 0.11 + (len(departments) * 0.015))
    history: list[dict[str, Any]] = []
    final_scores = dict(initial_scores)
    final_score = _weighted_score(final_scores)
    stopped_reason = "max_iterations_reached"

    for iteration in range(1, max_iterations + 1):
        progress = 1 - math.exp(-improvement_rate * iteration)
        scores = {
            key: round(initial_scores[key] + ((targets[key] - initial_scores[key]) * progress), 2)
            for key in initial_scores
        }
        overall = _weighted_score(scores)
        tester_approval_rate = _clamp((overall - 5.5) / 4.5, 0.08, 0.99)
        approvals = int(round(tester_count * tester_approval_rate))
        bug_reports = max(0, tester_count - approvals)
        history.append(
            {
                "iteration": iteration,
                "tester_score": overall,
                "pass": overall >= pass_threshold,
                "approvals": approvals,
                "bug_reports": bug_reports,
                "ui_flags": int(round(tester_count * max(0.01, (8.8 - scores["ui"]) / 13))),
                "workflow_flags": int(round(tester_count * max(0.01, (8.8 - scores["workflow"]) / 13))),
                "feature_flags": int(round(tester_count * max(0.01, (8.8 - scores["features"]) / 13))),
                "error_flags": int(round(tester_count * max(0.01, (8.9 - scores["errors"]) / 12))),
            }
        )
        final_scores = scores
        final_score = overall
        if overall >= pass_threshold:
            stopped_reason = "score_threshold_reached"
            break

    unresolved_findings = []
    if final_score < pass_threshold:
        unresolved_findings = findings[:3]
    else:
        weakest = min(final_scores, key=final_scores.get)
        if final_scores[weakest] < pass_threshold + 0.25:
            unresolved_findings = [item for item in findings if item["category"] == weakest][:2]

    goal_text = goal.strip() or f"Release {project.get('name', project.get('id', 'project'))} safely through the CEO -> departments -> tester loop"
    latest_loop = history[-1]
    ceo_summary = (
        f"CEO received the request to deliver {project.get('name', project.get('id', 'this project'))}, "
        f"mapped it into {len(departments)} departments, and routed all output through a 1,000 tester QA gate."
    )

    return {
        "project_id": project.get("id"),
        "project_name": project.get("name"),
        "goal": goal_text,
        "tester_count": tester_count,
        "max_iterations": max_iterations,
        "pass_threshold": round(pass_threshold, 2),
        "iterations_run": len(history),
        "passed": final_score >= pass_threshold,
        "stopped_reason": stopped_reason,
        "final_score": round(final_score, 2),
        "final_grade": _grade(final_score),
        "ceo_summary": ceo_summary,
        "department_plan": departments,
        "initial_scores": initial_scores,
        "final_scores": final_scores,
        "latest_iteration": latest_loop,
        "history": history,
        "initial_findings": findings,
        "unresolved_findings": unresolved_findings,
        "final_report": {
            "qa_gate": "pass" if final_score >= pass_threshold else "fail",
            "handoff_target": "CEO -> user/admin" if final_score >= pass_threshold else "Departments -> tester retest queue",
            "summary": (
                f"Tester team stopped after {len(history)} round(s) with score {final_score:.2f}/10."
                if final_score >= pass_threshold
                else f"Tester team used all {len(history)} round(s) and still needs another fix cycle."
            ),
        },
    }
