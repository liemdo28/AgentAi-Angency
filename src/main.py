from __future__ import annotations

from agency_registry import load_all_departments
from engine import WorkflowEngine
from policies import POLICIES, validate_policies
from product import ProductManager
from store import JsonStore


def main() -> int:
    departments = load_all_departments()
    print(f"Loaded departments: {len(departments)}")

    errors = validate_policies()
    if errors:
        print("Policy errors found:")
        for error in errors:
            print(f"- {error}")
        return 1

    store = JsonStore()
    handoffs, clients, projects = store.load_all()
    engine = WorkflowEngine(POLICIES, handoffs=handoffs)
    product = ProductManager(clients=clients, projects=projects)
    print(f"Inter-department policies: {len(POLICIES)}")
    print(f"Persisted handoffs: {len(engine.list_handoffs())}")
    print(f"Persisted clients: {len(product.list_clients())}")
    print(f"Persisted projects: {len(product.list_projects())}")
    print(f"Status: {engine.status_dashboard()}")

    for dept, bundle in departments.items():
        print(f"- {dept}: leader={bundle['leader'].role}, employees={len(bundle['employees'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
