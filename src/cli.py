from __future__ import annotations

import argparse
import json

from ai.orchestrator import AutonomousAgency
from engine import WorkflowEngine
from policies import POLICIES
from store import JsonStore


def build_engine(store: JsonStore) -> WorkflowEngine:
    return WorkflowEngine(POLICIES, handoffs=store.load())


def main() -> int:
    parser = argparse.ArgumentParser(description="Agency workflow CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("initiate")
    p_init.add_argument("from_department")
    p_init.add_argument("to_department")
    p_init.add_argument("--payload", default="{}", help='JSON payload, e.g. {"project_brief":"ok"}')

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("handoff_id")
    p_approve.add_argument("--notes", default="")

    p_block = sub.add_parser("block")
    p_block.add_argument("handoff_id")
    p_block.add_argument("--notes", default="")

    sub.add_parser("list")
    sub.add_parser("status")
    sub.add_parser("routes")
    sub.add_parser("refresh-overdue")

    # Autonomous AI layer commands
    p_ai_task = sub.add_parser("ai-create-task")
    p_ai_task.add_argument("department")
    p_ai_task.add_argument("goal")
    p_ai_task.add_argument("kpi")
    p_ai_task.add_argument("deadline")
    p_ai_task.add_argument("--context", default="{}")

    p_ai_run = sub.add_parser("ai-run-task")
    p_ai_run.add_argument("task_id")

    sub.add_parser("ai-status")

    args = parser.parse_args()
    store = JsonStore()
    engine = build_engine(store)
    autonomous = AutonomousAgency(existing_tasks=store.load_tasks())

    if args.cmd == "initiate":
        payload = json.loads(args.payload)
        handoff = engine.initiate_handoff(args.from_department, args.to_department, payload)
        print(handoff.id)

    elif args.cmd == "approve":
        handoff = engine.approve(args.handoff_id, args.notes)
        print(handoff.state.value)

    elif args.cmd == "block":
        handoff = engine.block(args.handoff_id, args.notes)
        print(handoff.state.value)

    elif args.cmd == "list":
        print(json.dumps(engine.export_handoffs(), indent=2))

    elif args.cmd == "status":
        print(json.dumps(engine.status_dashboard(), indent=2))

    elif args.cmd == "routes":
        print(json.dumps(engine.list_routes(), indent=2))

    elif args.cmd == "refresh-overdue":
        changed = engine.refresh_overdue()
        print(json.dumps({"updated": changed}))

    elif args.cmd == "ai-create-task":
        task = autonomous.create_task(
            goal=args.goal,
            kpi=args.kpi,
            deadline=args.deadline,
            department=args.department,
            context=json.loads(args.context),
        )
        print(task.id)

    elif args.cmd == "ai-run-task":
        task = autonomous.run_task(args.task_id)
        print(json.dumps({"id": task.id, "status": task.status.value, "score": task.score}, indent=2))

    elif args.cmd == "ai-status":
        print(json.dumps(autonomous.status_dashboard(), indent=2))

    store.save(engine.list_handoffs())
    store.save_tasks(autonomous.list_tasks())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
