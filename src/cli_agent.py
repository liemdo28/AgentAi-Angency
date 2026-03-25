#!/usr/bin/env python
"""
Agency AI CLI — simple command-line interface for running agency tasks.

Usage:
    python src/cli_agent.py run --task "Tạo strategy direction cho campaign bất động sản"
    python src/cli_agent.py status
    python src/cli_agent.py routes
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import textwrap
from pathlib import Path

# Ensure project root is on path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.supervisor import AgencySupervisor
from src.policies.interdepartment_policies import POLICIES
from src.agency_registry import load_all_departments

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_run(args: argparse.Namespace) -> int:
    """Run a task through the agency AI workflow."""
    supervisor = AgencySupervisor()

    print(f"\n{'='*60}")
    print(f"  Agency AI - Running Task")
    print(f"{'='*60}")
    print(f"  Task: {args.task}")
    print(f"  From: {args.from_dept or '(auto — router will decide)'}")
    print(f"  To:   {args.to_dept or '(auto — router will decide)'}")
    print(f"{'='*60}\n")

    result = supervisor.run(
        task_description=args.task,
        from_department=args.from_dept or None,
        to_department=args.to_dept or None,
    )

    # Pretty-print result summary
    status = result.get("status", "?")
    score = result.get("leader_score", 0)
    errors = result.get("errors", [])
    outputs = result.get("generated_outputs", {})

    print(f"\n{'='*60}")
    print(f"  RESULT")
    print(f"{'='*60}")
    print(f"  Task ID:  {result.get('task_id', '?')}")
    print(f"  Status:   {status}")
    print(f"  Score:    {score:.0f}/100")
    print(f"  Route:    {result.get('from_department','?')} -> {result.get('to_department','?')}")

    if errors:
        print(f"  Errors:   {errors}")

    print(f"\n  --- Generated Outputs ({len(outputs)} sections) ---")
    if outputs:
        for key, value in outputs.items():
            snippet = str(value)[:300].replace("\n", " ").strip()
            print(f"  [{key}] {snippet}...")
    else:
        print("  (no outputs generated)")

    # Show specialist output if available
    specialist_out = result.get("specialist_output", "")
    if specialist_out and args.verbose:
        print(f"\n  --- Full Specialist Output ---")
        print(textwrap.indent(specialist_out[:3000], "  "))

    if result.get("email_sent"):
        print(f"\n  📧 Email notification sent to: {result.get('metadata', {}).get('notification_sent_to', '?')}")

    print(f"\n{'='*60}\n")
    return 0 if status in ("PASSED",) else 1


def cmd_routes(args: argparse.Namespace) -> int:
    """List all available inter-department routes."""
    departments = load_all_departments()
    print(f"\n{'='*60}")
    print(f"  Agency Routes - {len(POLICIES)} policies across {len(departments)} departments")
    print(f"{'='*60}\n")

    for p in POLICIES:
        inputs = ", ".join(p.required_inputs)
        outputs = ", ".join(p.expected_outputs)
        print(f"  {p.from_department:15} -> {p.to_department:15}  [{p.sla_hours}h]  ({p.approver_role})")
        print(f"    Inputs:  {inputs}")
        print(f"    Outputs: {outputs}")
        print()

    return 0


def cmd_departments(args: argparse.Namespace) -> int:
    """List all departments and their staff."""
    departments = load_all_departments()
    print(f"\n{'='*60}")
    print(f"  Departments — {len(departments)} total")
    print(f"{'='*60}\n")

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
    from src.llm import get_llm
    from src.config import SETTINGS

    llm = get_llm()
    info = llm.provider_info

    print(f"\n{'='*60}")
    print(f"  Agency AI — System Status")
    print(f"{'='*60}\n")
    print(f"  Score threshold: {SETTINGS.SCORE_THRESHOLD}%")
    print(f"  Max retries:    {SETTINGS.MAX_ROUTE_RETRIES}")
    print(f"  Departments:    11")
    print(f"  Policies:        {len(POLICIES)}")
    print(f"\n  LLM Providers:")
    for prov, available in info.items():
        status = "[OK]" if available else "[--]"
        print(f"    {prov:12} {status}")

    if not any(info.values()):
        print(f"\n  [!] No LLM providers configured!")
        print(f"      Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or OLLAMA_BASE_URL")
        print(f"      in a .env file in the project root.\n")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Agency AI CLI - run agency tasks through the AI workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Run a task through the AI workflow")
    p_run.add_argument("--task", "-t", required=True, help="Task description")
    p_run.add_argument("--from", dest="from_dept", default="", help="Source department (optional)")
    p_run.add_argument("--to", dest="to_dept", default="", help="Target department (optional)")
    p_run.add_argument("--verbose", "-v", action="store_true", help="Show full specialist output")
    p_run.set_defaults(func=cmd_run)

    # routes
    p_routes = sub.add_parser("routes", help="List all inter-department routes")
    p_routes.set_defaults(func=cmd_routes)

    # departments
    p_depts = sub.add_parser("departments", help="List all departments")
    p_depts.set_defaults(func=cmd_departments)

    # status
    p_status = sub.add_parser("status", help="Show system status")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
