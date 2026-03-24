from __future__ import annotations

from policies.interdepartment_policies import POLICIES

DEPARTMENTS = {
    "account",
    "strategy",
    "creative",
    "media",
    "tech",
    "data",
    "production",
    "sales",
    "operations",
    "finance",
}


def validate_policies() -> list[str]:
    errors: list[str] = []
    for policy in POLICIES:
        if policy.from_department not in DEPARTMENTS:
            errors.append(f"Unknown from_department: {policy.from_department}")
        if policy.to_department not in DEPARTMENTS:
            errors.append(f"Unknown to_department: {policy.to_department}")
        if policy.sla_hours <= 0:
            errors.append(f"Invalid SLA for {policy.from_department}->{policy.to_department}")
    return errors
