from __future__ import annotations

from agency_registry import load_all_departments
from policies import POLICIES, validate_policies


def main() -> int:
    departments = load_all_departments()
    print(f"Loaded departments: {len(departments)}")

    errors = validate_policies()
    if errors:
        print("Policy errors found:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Inter-department policies: {len(POLICIES)}")
    for dept, bundle in departments.items():
        print(f"- {dept}: leader={bundle['leader'].role}, employees={len(bundle['employees'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
