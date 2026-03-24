from __future__ import annotations

from agency_registry import load_all_departments
from policies.interdepartment_policies import POLICIES


def validate_policies() -> list[str]:
    errors: list[str] = []
    departments = load_all_departments()
    department_keys = set(departments.keys())

    route_seen: set[tuple[str, str]] = set()
    inbound: dict[str, int] = {key: 0 for key in department_keys}
    outbound: dict[str, int] = {key: 0 for key in department_keys}

    for policy in POLICIES:
        route = (policy.from_department, policy.to_department)

        if policy.from_department not in department_keys:
            errors.append(f"Unknown from_department: {policy.from_department}")
        if policy.to_department not in department_keys:
            errors.append(f"Unknown to_department: {policy.to_department}")

        if route in route_seen:
            errors.append(f"Duplicate policy route: {policy.from_department}->{policy.to_department}")
        else:
            route_seen.add(route)

        if not policy.required_inputs:
            errors.append(f"Empty required_inputs: {policy.from_department}->{policy.to_department}")
        if not policy.expected_outputs:
            errors.append(f"Empty expected_outputs: {policy.from_department}->{policy.to_department}")
        if policy.sla_hours <= 0:
            errors.append(f"Invalid SLA for {policy.from_department}->{policy.to_department}")

        if policy.to_department in departments:
            expected_approver = departments[policy.to_department]["leader"].role
            if policy.approver_role != expected_approver:
                errors.append(
                    f"Approver mismatch {policy.from_department}->{policy.to_department}: "
                    f"expected '{expected_approver}', got '{policy.approver_role}'"
                )

        if policy.from_department in outbound:
            outbound[policy.from_department] += 1
        if policy.to_department in inbound:
            inbound[policy.to_department] += 1

    # Critical routes mandated by workflow
    required_routes = {
        ("sales", "account"),
        ("account", "strategy"),
        ("strategy", "creative"),
        ("strategy", "media"),
        ("data", "strategy"),
        ("media", "account"),
        ("account", "finance"),
        ("creative", "production"),
        ("tech", "operations"),
        ("data", "crm_automation"),
    }

    missing_routes = required_routes - route_seen
    for from_dept, to_dept in sorted(missing_routes):
        errors.append(f"Missing critical route: {from_dept}->{to_dept}")

    # Orphan departments: no inbound or no outbound policy
    for dept in sorted(department_keys):
        if inbound[dept] == 0:
            errors.append(f"Orphan department without inbound policy: {dept}")
        if outbound[dept] == 0:
            errors.append(f"Orphan department without outbound policy: {dept}")

    # Department bundle sanity checks
    for dept, bundle in departments.items():
        if not bundle["employees"]:
            errors.append(f"Department has no employees: {dept}")
        if not bundle["policy"].get("required_inputs"):
            errors.append(f"Department policy missing required_inputs: {dept}")
        if not bundle["policy"].get("core_outputs"):
            errors.append(f"Department policy missing core_outputs: {dept}")

    return errors
