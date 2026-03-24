from __future__ import annotations

import argparse
import json

from engine import WorkflowEngine
from policies import POLICIES
from product import ProductManager
from store import JsonStore


def build_context(store: JsonStore) -> tuple[WorkflowEngine, ProductManager]:
    handoffs, clients, projects = store.load_all()
    engine = WorkflowEngine(POLICIES, handoffs=handoffs)
    product = ProductManager(clients=clients, projects=projects)
    return engine, product


def main() -> int:
    parser = argparse.ArgumentParser(description="Agency workflow CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_client = sub.add_parser("create-client")
    p_client.add_argument("name")
    p_client.add_argument("industry")

    p_project = sub.add_parser("create-project")
    p_project.add_argument("client_id")
    p_project.add_argument("name")
    p_project.add_argument("objective")
    p_project.add_argument("owner")

    sub.add_parser("list-clients")
    sub.add_parser("list-projects")

    p_init = sub.add_parser("initiate")
    p_init.add_argument("from_department")
    p_init.add_argument("to_department")
    p_init.add_argument("--payload", default="{}", help='JSON payload, e.g. {"project_brief":"ok"}')
    p_init.add_argument("--client-id", default=None)
    p_init.add_argument("--project-id", default=None)

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("handoff_id")
    p_approve.add_argument("--notes", default="")

    p_block = sub.add_parser("block")
    p_block.add_argument("handoff_id")
    p_block.add_argument("--notes", default="")

    p_list = sub.add_parser("list")
    p_list.add_argument("--project-id", default=None)

    sub.add_parser("status")
    sub.add_parser("routes")
    sub.add_parser("refresh-overdue")

    args = parser.parse_args()
    store = JsonStore()
    engine, product = build_context(store)

    if args.cmd == "create-client":
        client = product.create_client(args.name, args.industry)
        print(client.id)

    elif args.cmd == "create-project":
        project = product.create_project(args.client_id, args.name, args.objective, args.owner)
        print(project.id)

    elif args.cmd == "list-clients":
        print(json.dumps([c.__dict__ | {"created_at": c.created_at.isoformat()} for c in product.list_clients()], indent=2))

    elif args.cmd == "list-projects":
        print(
            json.dumps(
                [p.__dict__ | {"created_at": p.created_at.isoformat()} for p in product.list_projects()],
                indent=2,
            )
        )

    elif args.cmd == "initiate":
        payload = json.loads(args.payload)
        handoff = engine.initiate_handoff(
            args.from_department,
            args.to_department,
            payload,
            client_id=args.client_id,
            project_id=args.project_id,
        )
        print(handoff.id)

    elif args.cmd == "approve":
        handoff = engine.approve(args.handoff_id, args.notes)
        print(handoff.state.value)

    elif args.cmd == "block":
        handoff = engine.block(args.handoff_id, args.notes)
        print(handoff.state.value)

    elif args.cmd == "list":
        if args.project_id:
            rows = [h for h in engine.export_handoffs() if h.get("project_id") == args.project_id]
            print(json.dumps(rows, indent=2))
        else:
            print(json.dumps(engine.export_handoffs(), indent=2))

    elif args.cmd == "status":
        status = engine.status_dashboard()
        status["clients"] = len(product.list_clients())
        status["projects"] = len(product.list_projects())
        print(json.dumps(status, indent=2))

    elif args.cmd == "routes":
        print(json.dumps(engine.list_routes(), indent=2))

    elif args.cmd == "refresh-overdue":
        changed = engine.refresh_overdue()
        print(json.dumps({"updated": changed}))

    store.save_all(engine.list_handoffs(), product.list_clients(), product.list_projects())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
