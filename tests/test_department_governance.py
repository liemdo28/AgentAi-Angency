from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from db.repository import ControlPlaneDB


def _client(monkeypatch, tmp_path):
    temp_db = ControlPlaneDB(db_path=str(tmp_path / "governance.db"))
    monkeypatch.setattr(api_main, "db", temp_db)
    monkeypatch.setattr(api_main, "MASTER_DIR", Path(tmp_path / "Master"))
    return TestClient(api_main.app), temp_db


def test_department_seed_defaults(tmp_path):
    db = ControlPlaneDB(db_path=str(tmp_path / "seed.db"))

    departments = db.list_departments()
    policies = db.list_policies()
    permissions = db.list_permissions()

    assert any(item["code"] == "REVIEW_MANAGEMENT" for item in departments)
    assert any(item["policy_code"] == "POLICY_001_REVIEW_LOW_RATING" for item in policies)
    assert any(item["permission_key"] == "reviews.reply" for item in permissions)


def test_department_crud_permissions_and_store_assignment(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    created = client.post(
        "/departments",
        json={
            "code": "TEST_DEPT",
            "name": "Test Department",
            "description": "for qa",
            "category": "qa",
            "status": "active",
            "allow_store_assignment": True,
            "allow_ai_agent_execution": True,
            "allow_human_assignment": True,
            "requires_ceo_visibility_only": False,
            "execution_mode": "suggest_only",
        },
    )
    assert created.status_code == 200
    department_id = created.json()["id"]

    updated_permissions = client.put(
        f"/departments/{department_id}/permissions",
        json={"permissions": [{"key": "reviews.reply", "allowed": True}, {"key": "analytics.read", "allowed": True}]},
    )
    assert updated_permissions.status_code == 200
    assert any(item["permission_key"] == "reviews.reply" and item["allowed"] for item in updated_permissions.json())

    matrix = client.put(
        "/stores/RAW/departments",
        json={
            "departments": [
                {
                    "department_id": department_id,
                    "enabled": True,
                    "locked": False,
                    "hidden": False,
                    "deleted": False,
                    "custom_policy_enabled": True,
                    "execution_mode": "semi_auto",
                }
            ]
        },
    )
    assert matrix.status_code == 200
    assert any(item["department_id"] == department_id and item["enabled"] for item in matrix.json())

    listed = client.get("/stores/RAW/departments")
    assert listed.status_code == 200
    assert any(item["department_id"] == department_id and item["execution_mode"] == "semi_auto" for item in listed.json())

    deleted = client.delete(f"/departments/{department_id}")
    assert deleted.status_code == 409


def test_policy_evaluation_requires_approval_for_negative_review(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    review_department = next(item for item in db.list_departments() if item["code"] == "REVIEW_MANAGEMENT")
    db.set_department_permissions(
        review_department["id"],
        [{"key": "reviews.reply", "allowed": True}],
    )
    db.upsert_store_departments(
        "RAW",
        [
            {
                "department_id": review_department["id"],
                "enabled": True,
                "locked": False,
                "hidden": False,
                "deleted": False,
                "custom_policy_enabled": False,
                "execution_mode": "semi_auto",
            }
        ],
    )

    evaluated = client.post(
        "/policies/evaluate",
        json={
            "actor_type": "agent",
            "actor_id": "agent-review-01",
            "actor_role": "department_head",
            "store_id": "RAW",
            "department_id": review_department["id"],
            "action": "reviews.reply.publish",
            "permission_key": "reviews.reply",
            "context": {"rating": 2, "sentiment": "negative"},
        },
    )
    assert evaluated.status_code == 200
    payload = evaluated.json()
    assert payload["allowed"] is False
    assert payload["decision"] == "require_approval"
    assert payload["matched_policy"] == "POLICY_001_REVIEW_LOW_RATING"

    audit_logs = client.get("/audit-logs?department_id=" + review_department["id"])
    assert audit_logs.status_code == 200
    assert any("governance.evaluate.require_approval" == item["action"] for item in audit_logs.json())


def test_governed_action_creates_approval_and_versions_exist(monkeypatch, tmp_path):
    client, db = _client(monkeypatch, tmp_path)
    review_department = next(item for item in db.list_departments() if item["code"] == "REVIEW_MANAGEMENT")
    db.set_department_permissions(
        review_department["id"],
        [{"key": "reviews.reply", "allowed": True}],
    )
    db.upsert_store_departments(
        "RAW",
        [
            {
                "department_id": review_department["id"],
                "enabled": True,
                "locked": False,
                "hidden": False,
                "deleted": False,
                "custom_policy_enabled": False,
                "execution_mode": "semi_auto",
            }
        ],
    )

    request_result = client.post(
        "/governance/actions/request",
        json={
            "actor_type": "agent",
            "actor_id": "agent-review-01",
            "actor_role": "department_head",
            "store_id": "RAW",
            "department_id": review_department["id"],
            "action": "reviews.reply.publish",
            "permission_key": "reviews.reply",
            "context": {"rating": 2, "sentiment": "negative"},
        },
    )
    assert request_result.status_code == 200
    body = request_result.json()
    assert body["status"] == "pending_approval"
    assert body["approval"]["resource_type"] == "department_action"
    assert body["approval"]["approval_level"] == "store_manager"

    approvals = client.get("/approvals?status=pending&resource_type=department_action")
    assert approvals.status_code == 200
    assert len(approvals.json()) >= 1

    first_policy = client.get("/policies").json()[0]
    versions = client.get(f"/policies/{first_policy['id']}/versions")
    assert versions.status_code == 200
    assert len(versions.json()) >= 1

    simulations = client.get("/policies/simulations?limit=10")
    assert simulations.status_code == 200
    assert any(item["action"] == "reviews.reply.publish" for item in simulations.json())
