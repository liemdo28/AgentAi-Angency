from __future__ import annotations

import argparse
import json

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

    args = parser.parse_args()
    store = JsonStore()
    engine = build_engine(store)

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

    store.save(engine.list_handoffs())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
