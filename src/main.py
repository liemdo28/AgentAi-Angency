from __future__ import annotations

from ai.orchestrator import AutonomousAgency
from agency_registry import load_all_departments
from engine import WorkflowEngine
from policies import POLICIES, validate_policies
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
    engine = WorkflowEngine(POLICIES, handoffs=store.load())
    autonomous = AutonomousAgency(existing_tasks=store.load_tasks())

    print(f"Inter-department policies: {len(POLICIES)}")
    print(f"Persisted handoffs: {len(engine.list_handoffs())}")
    print(f"Workflow status: {engine.status_dashboard()}")
    print(f"AI task status: {autonomous.status_dashboard()}")

    for dept, bundle in departments.items():
        print(f"- {dept}: leader={bundle['leader'].role}, employees={len(bundle['employees'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
