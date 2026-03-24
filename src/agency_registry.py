from __future__ import annotations

from importlib import import_module

DEPARTMENT_KEYS = (
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
)


def load_department_bundle(department: str) -> dict:
    employees_mod = import_module(f"departments.{department}.employees")
    leader_mod = import_module(f"departments.{department}.leader")
    policy_mod = import_module(f"departments.{department}.policy")
    return {
        "employees": employees_mod.EMPLOYEES,
        "leader": leader_mod.LEADER,
        "policy": policy_mod.POLICY,
    }


def load_all_departments() -> dict[str, dict]:
    return {dept: load_department_bundle(dept) for dept in DEPARTMENT_KEYS}
