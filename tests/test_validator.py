from __future__ import annotations

import policies.interdepartment_policies as inter_mod
from models import HandoffPolicy
from policies import POLICIES, validate_policies


def test_no_validation_errors():
    errors = validate_policies()
    assert errors == [], "Unexpected errors:\n" + "\n".join(errors)


def test_all_routes_unique():
    routes = [(p.from_department, p.to_department) for p in POLICIES]
    assert len(routes) == len(set(routes)), "Duplicate routes found"


def test_no_empty_inputs_or_outputs():
    for p in POLICIES:
        assert p.required_inputs, f"Empty inputs: {p.from_department}->{p.to_department}"
        assert p.expected_outputs, f"Empty outputs: {p.from_department}->{p.to_department}"


def test_all_sla_positive():
    for p in POLICIES:
        assert p.sla_hours > 0, f"SLA <= 0: {p.from_department}->{p.to_department}"


def test_critical_routes_present():
    routes = {(p.from_department, p.to_department) for p in POLICIES}
    critical = {
        ("sales", "account"),
        ("account", "strategy"),
        ("strategy", "creative"),
        ("strategy", "media"),
        ("data", "crm_automation"),
        ("crm_automation", "data"),
        ("media", "data"),
        ("production", "account"),
        ("strategy", "account"),
    }
    missing = critical - routes
    assert not missing, f"Missing critical routes: {missing}"


def test_duplicate_route_detected():
    dupe = HandoffPolicy(
        "sales", "account",
        ("lead_profile",), ("project_brief",),
        8, "Account Manager",
    )
    original = inter_mod.POLICIES
    inter_mod.POLICIES = original + (dupe,)
    try:
        errors = validate_policies()
        assert any("Duplicate" in e for e in errors), "Expected duplicate route error"
    finally:
        inter_mod.POLICIES = original


def test_missing_critical_route_detected():
    # Remove sales->account and verify validator catches it
    filtered = tuple(
        p for p in inter_mod.POLICIES
        if not (p.from_department == "sales" and p.to_department == "account")
    )
    original = inter_mod.POLICIES
    inter_mod.POLICIES = filtered
    try:
        errors = validate_policies()
        assert any("sales->account" in e for e in errors), "Expected missing route error"
    finally:
        inter_mod.POLICIES = original
