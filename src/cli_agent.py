#!/usr/bin/env python
"""
Agency AI CLI - command-line interface for planning and running agency tasks.

Usage:
    python src/cli_agent.py plan --task "Launch a spring real-estate campaign"
    python src/cli_agent.py run --task "Tao strategy direction cho campaign bat dong san"
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

from src.agency_registry import load_all_departments
from src.agents.supervisor import AgencySupervisor
from src.policies.interdepartment_policies import POLICIES
from src.tasks import build_task_plan, list_available_task_types

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

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
