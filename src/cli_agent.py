#!/usr/bin/env python
"""
Agency AI CLI - command-line interface for planning and running agency tasks.

Usage:
    python src/cli_agent.py plan --task "Launch a spring real-estate campaign"
    python src/cli_agent.py run --task "Tao strategy direction cho campaign bat dong san"
    python src/cli_agent.py exec --goal "Chay campaign quang cao Nike cho san pham giay the thao"
    python src/cli_agent.py monitor
    python src/cli_agent.py status
    python src/cli_agent.py routes
"""
from __future__ import annotations

import argparse
import logging
import textwrap
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Fix Windows cp1252 encoding for Vietnamese output
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.agency_registry import load_all_departments
from src.agents.supervisor import AgencySupervisor
from src.policies.interdepartment_policies import POLICIES
from src.task_templates import build_task_plan, list_available_task_types

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_run(args: argparse.Namespace) -> int:
    """Run a task through the agency AI workflow."""
    supervisor = AgencySupervisor()

    print(f"\n{'=' * 60}")
    print("  Agency AI - Running Task")
    print(f"{'=' * 60}")
    print(f"  Task: {args.task}")
    print(f"  From: {args.from_dept or '(auto - planner/router will decide)'}")
    print(f"  To:   {args.to_dept or '(auto - planner/router will decide)'}")
    print(f"  Type: {args.task_type or '(auto)'}")
    print(f"{'=' * 60}\n")

    result = supervisor.run(
        task_description=args.task,
        from_department=args.from_dept or None,
        to_department=args.to_dept or None,
        task_type=args.task_type or None,
        quality_threshold=args.threshold,
    )

    status = result.get("status", "?")
    score = result.get("leader_score", 0)
    errors = result.get("errors", [])
    outputs = result.get("generated_outputs", {})
    review_history = result.get("review_history", [])

    print(f"\n{'=' * 60}")
    print("  RESULT")
    print(f"{'=' * 60}")
    print(f"  Task ID:  {result.get('task_id', '?')}")
    print(f"  Status:   {status}")
    print(f"  Score:    {score:.0f}/100")
    print(f"  Type:     {result.get('task_type', 'ad_hoc')}")
    print(f"  Route:    {result.get('from_department', '?')} -> {result.get('to_department', '?')}")
    print(
        f"  Steps:    {len(result.get('task_plan', []))} planned / "
        f"{len(result.get('completed_steps', []))} completed"
    )

    if errors:
        print(f"  Errors:   {errors}")

    print(f"\n  --- Generated Outputs ({len(outputs)} sections) ---")
    if outputs:
        for key, value in outputs.items():
            snippet = str(value)[:300].replace("\n", " ").strip()
            print(f"  [{key}] {snippet}...")
    else:
        print("  (no outputs generated)")

    if review_history:
        print(f"\n  --- Review History ({len(review_history)} checkpoints) ---")
        for review in review_history:
            print(
                "  "
                f"{review.get('step', '?')}: "
                f"{review.get('score', 0):.0f}/{review.get('threshold', 0):.0f} "
                f"({review.get('decision', '?')})"
            )

    specialist_out = result.get("specialist_output", "")
    if specialist_out and args.verbose:
        print("\n  --- Full Specialist Output ---")
        print(textwrap.indent(specialist_out[:3000], "  "))

    if result.get("email_sent"):
        print(
            "\n  Email notification sent to: "
            f"{result.get('metadata', {}).get('notification_sent_to', '?')}"
        )

    print(f"\n{'=' * 60}\n")
    return 0 if status == "PASSED" else 1


def cmd_plan(args: argparse.Namespace) -> int:
    """Preview the multi-step task plan without executing the graph."""
    plan = build_task_plan(
        args.task,
        from_department=args.from_dept or "",
        to_department=args.to_dept or "",
        task_type=args.task_type or "",
    )
    steps = plan.get("steps", [])

    print(f"\n{'=' * 60}")
    print("  Agency AI - Task Plan Preview")
    print(f"{'=' * 60}")
    print(f"  Task: {args.task}")
    print(f"  Type: {plan.get('task_type', 'ad_hoc')}")
    print(f"  Mode: {plan.get('planning_mode', 'router_only')}")
    print(f"  Steps: {len(steps)}")
    print(f"{'=' * 60}\n")

    if not steps:
        print("  No template plan selected. The router will choose a single route at runtime.\n")
        return 0

    for index, step in enumerate(steps, start=1):
        print(f"  {index}. {step['name']}")
        print(f"     Route: {step['from_department']} -> {step['to_department']}")
        print(f"     Objective: {step['objective']}")
        print(f"     Threshold: {step.get('quality_threshold', 98.0):.0f}/100")
        print(f"     Outputs: {', '.join(step['expected_outputs'])}")
        print()

    return 0


def cmd_routes(args: argparse.Namespace) -> int:
    """List all available inter-department routes."""
    departments = load_all_departments()
    print(f"\n{'=' * 60}")
    print(f"  Agency Routes - {len(POLICIES)} policies across {len(departments)} departments")
    print(f"{'=' * 60}\n")

    for policy in POLICIES:
        inputs = ", ".join(policy.required_inputs)
        outputs = ", ".join(policy.expected_outputs)
        print(
            f"  {policy.from_department:15} -> {policy.to_department:15}  "
            f"[{policy.sla_hours}h]  ({policy.approver_role})"
        )
        print(f"    Inputs:  {inputs}")
        print(f"    Outputs: {outputs}")
        print()

    return 0


def cmd_exec(args: argparse.Namespace) -> int:
    """
    CEO Exec: operator gives a goal, AI does the work end-to-end.

    This is the primary command for running the AI Agency.
    Uses CEO Brain (Layer 1) to interpret the goal, create a Task,
    execute the LangGraph workflow, score it, and retry if needed.
    """
    from src.agents.supervisor import AgencySupervisor
    from src.ceo.brain import CEOBrain

    goal = args.goal
    mode = args.mode.upper() if args.mode else "CREATE_TASK"

    print(f"\n{'=' * 60}")
    print("  CEO EXEC - AI Doing The Work")
    print(f"{'=' * 60}")
    print(f"  Goal:  {goal}")
    print(f"  Mode:  {mode}")
    print(f"{'=' * 60}\n")

    try:
        ceo = CEOBrain()
        result = ceo.run(goal, mode=mode)
    except Exception as exc:
        # Fallback: direct supervisor run (if DB not init yet)
        print(f"  [Note] CEOBrain init failed ({exc}), falling back to direct run...\n")
        supervisor = AgencySupervisor()
        result = supervisor.run(task_description=goal)

    # ── Parse result ────────────────────────────────────────────────
    action = result.get("action", "unknown")
    task_id = result.get("task_id", "?")
    status = result.get("status", "?")
    score = result.get("score", result.get("leader_score", 0))
    decisions = result.get("decisions", [])
    sla_violations = result.get("sla_violations", [])
    campaign_health = result.get("campaign_health", {})
    active_tasks = result.get("active_tasks", 0)

    print(f"\n{'=' * 60}")
    print("  CEO RESULT")
    print(f"{'=' * 60}")
    print(f"  Action:   {action}")
    if task_id != "?":
        print(f"  Task ID:  {task_id}")
    print(f"  Status:   {status}")
    print(f"  Score:    {score:.0f}/100")

    # ── MONITOR mode output ─────────────────────────────────────────
    if mode == "MONITOR":
        print(f"\n  --- Monitoring Summary ---")
        print(f"  Active tasks:       {active_tasks}")
        print(f"  SLA violations:     {len(sla_violations)}")
        print(f"  Health scores:      {len(campaign_health)} campaigns")
        for cid, hscore in list(campaign_health.items())[:5]:
            bar = "=" * int(hscore / 10)
            print(f"    {cid[:8]}: {hscore:.0f}/100 |{bar}|")

        if decisions:
            print(f"\n  --- Decisions ({len(decisions)}) ---")
            for d in decisions:
                dt = d.get("decision_type", "?")
                tid = d.get("task_id", "?")[:12]
                reason = d.get("reason", "")[:60]
                print(f"    [{dt}] {tid}: {reason}")

    # ── CREATE_TASK mode output ─────────────────────────────────────
    elif mode == "CREATE_TASK":
        supervisor_result = result.get("result", {})
        outputs = supervisor_result.get("generated_outputs", {})
        review_history = supervisor_result.get("review_history", [])

        if outputs:
            print(f"\n  --- Generated Outputs ({len(outputs)} sections) ---")
            for key, value in outputs.items():
                snippet = str(value)[:200].replace("\n", " ")[:200].strip()
                print(f"  [{key}] {snippet}...")

        if review_history:
            print(f"\n  --- Review History ({len(review_history)} checkpoints) ---")
            for r in review_history:
                step = r.get("step", "?")
                sc = r.get("score", 0)
                th = r.get("threshold", 98)
                dec = r.get("decision", "?")
                method = r.get("scoring_method", "llm")
                print(f"    [{step}] score={sc:.0f}/{th:.0f} -> {dec} ({method})")

        # Show specialist full output if verbose
        specialist_out = supervisor_result.get("specialist_output", "")
        if specialist_out and args.verbose:
            print(f"\n  --- Full Specialist Output ---")
            safe_out = specialist_out[:2000].encode("utf-8", errors="replace").decode("utf-8")
            print(textwrap.indent(safe_out, "    "))

        # Escalation check
        if score < 60:
            print(f"\n  [!] ESCALATION TRIGGERED: score {score:.0f} < 60")
            print(f"  [!] Manual review required.")

    print(f"\n{'=' * 60}\n")
    return 0 if status in ("PASSED", "DONE", "monitor_complete") else 1


def cmd_monitor(args: argparse.Namespace) -> int:
    """CEO Monitor: scan active tasks, check SLA, health, and display decisions."""
    from src.ceo.brain import CEOBrain

    print(f"\n{'=' * 60}")
    print("  CEO MONITOR - System Health Check")
    print(f"{'=' * 60}\n")

    try:
        ceo = CEOBrain()
        result = ceo.run("", mode="MONITOR")
    except Exception as exc:
        print(f"  [ERROR] Monitor failed: {exc}\n")
        return 1

    active = result.get("active_tasks", 0)
    violations = result.get("sla_violations", [])
    health = result.get("campaign_health", {})
    decisions = result.get("decisions", [])

    print(f"  Active tasks:  {active}")
    print(f"  SLA violations: {len(violations)}")
    print(f"  Campaigns:     {len(health)}")

    if violations:
        print(f"\n  --- SLA Violations ---")
        for v in violations:
            print(f"    Task {v.get('task_id','')}: {v.get('reason', v)}")

    if decisions:
        print(f"\n  --- Decisions ({len(decisions)}) ---")
        for d in decisions:
            dt = d.get("decision_type", "?")
            tid = d.get("task_id", "?")
            ra = d.get("recommended_action", "?")
            print(f"    [{dt}] {tid}: {ra}")

    if not violations and not decisions:
        print(f"\n  [OK] All systems healthy. No action required.")

    print(f"\n{'=' * 60}\n")
    return 0


def cmd_departments(args: argparse.Namespace) -> int:
    """List all departments and their staff."""
    departments = load_all_departments()
    print(f"\n{'=' * 60}")
    print(f"  Departments - {len(departments)} total")
    print(f"{'=' * 60}\n")

    for dept_key, bundle in sorted(departments.items()):
        leader = bundle["leader"]
        employees = bundle["employees"]
        print(f"  [{dept_key.upper()}]")
        print(f"    Leader: {leader.full_name} ({leader.role})")
        print(f"    Employees ({len(employees)}):")
        for emp in employees:
            print(f"      - {emp.full_name} ({emp.role})")
        print()

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show system status and available LLM providers."""
    from src.config import SETTINGS
    from src.llm import get_llm

    llm = get_llm()
    info = llm.provider_info

    print(f"\n{'=' * 60}")
    print("  Agency AI - System Status")
    print(f"{'=' * 60}\n")
    print(f"  Score threshold: {SETTINGS.SCORE_THRESHOLD}%")
    print(f"  Max retries:    {SETTINGS.MAX_ROUTE_RETRIES}")
    print("  Departments:    11")
    print(f"  Policies:       {len(POLICIES)}")
    print(f"  Task types:     {', '.join(list_available_task_types())}")
    print("\n  LLM Providers:")
    for provider, available in info.items():
        status = "configured" if available else "not configured"
        print(f"    {provider:12} {status}")

    if not any(info.values()):
        print("\n  No remote LLM providers configured.")
        print("  The system will fall back to deterministic drafting and heuristic review.\n")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Agency AI CLI - plan and run agency tasks through the AI workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run a task through the AI workflow")
    p_run.add_argument("--task", "-t", required=True, help="Task description")
    p_run.add_argument("--from", dest="from_dept", default="", help="Source department (optional)")
    p_run.add_argument("--to", dest="to_dept", default="", help="Target department (optional)")
    p_run.add_argument("--task-type", default="", help="Override task type template")
    p_run.add_argument("--threshold", type=float, default=98.0, help="Quality threshold for the task")
    p_run.add_argument("--verbose", "-v", action="store_true", help="Show full specialist output")
    p_run.set_defaults(func=cmd_run)

    p_plan = sub.add_parser("plan", help="Preview the multi-step task plan")
    p_plan.add_argument("--task", "-t", required=True, help="Task description")
    p_plan.add_argument("--from", dest="from_dept", default="", help="Source department (optional)")
    p_plan.add_argument("--to", dest="to_dept", default="", help="Target department (optional)")
    p_plan.add_argument("--task-type", default="", help="Override task type template")
    p_plan.set_defaults(func=cmd_plan)

    p_routes = sub.add_parser("routes", help="List all routes")
    p_routes.set_defaults(func=cmd_routes)

    p_depts = sub.add_parser("departments", help="List all departments")
    p_depts.set_defaults(func=cmd_departments)

    p_status = sub.add_parser("status", help="Show system status")
    p_status.set_defaults(func=cmd_status)

    # ── CEO Layer commands ─────────────────────────────────────────
    p_exec = sub.add_parser(
        "exec",
        help="CEO Exec: operator gives a goal, AI does the work end-to-end (CREATE_TASK)"
    )
    p_exec.add_argument("--goal", "-g", required=True, help="Business goal in natural language")
    p_exec.add_argument("--mode", default="CREATE_TASK",
                        help="CEO mode: CREATE_TASK (default) or MONITOR")
    p_exec.add_argument("--verbose", "-v", action="store_true", help="Show full specialist output")
    p_exec.set_defaults(func=cmd_exec)

    p_monitor = sub.add_parser(
        "monitor",
        help="CEO Monitor: scan active tasks, check SLA, health scores"
    )
    p_monitor.set_defaults(func=cmd_monitor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
