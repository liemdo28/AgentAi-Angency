from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from db.repository import ControlPlaneDB


def test_project_snapshot_repository_round_trip(tmp_path):
    db = ControlPlaneDB(db_path=str(tmp_path / "control-plane.db"))
    db.upsert_project_snapshot(
        project_id="integration-full",
        machine_id="stockton-frontdesk-01",
        machine_name="Stockton Frontdesk",
        source_type="integration-full",
        app_version="v2.2",
        snapshot={
            "generated_at": "2026-04-07T10:00:00+00:00",
            "summary": {"download_gap_count": 2, "qb_gap_count": 1},
        },
    )

    latest = db.get_latest_project_snapshot("integration-full")

    assert latest is not None
    assert latest["machine_id"] == "stockton-frontdesk-01"
    assert latest["summary"]["download_gap_count"] == 2


def test_projects_endpoint_prefers_remote_snapshot(monkeypatch, tmp_path):
    temp_db = ControlPlaneDB(db_path=str(tmp_path / "control-plane.db"))
    monkeypatch.setattr(api_main, "db", temp_db)
    monkeypatch.setattr(api_main, "MASTER_DIR", Path(tmp_path / "Master"))
    monkeypatch.setenv("AGENTAI_EDGE_TOKEN", "secret-token")

    client = TestClient(api_main.app)

    payload = {
        "machine_id": "stockton-frontdesk-01",
        "machine_name": "Stockton Frontdesk",
        "source_type": "integration-full",
        "app_version": "v2.2",
        "snapshot": {
            "generated_at": "2026-04-07T10:00:00+00:00",
            "summary": {
                "stores_tracked": 7,
                "download_gap_count": 3,
                "qb_gap_count": 2,
                "failed_qb_count": 0,
            },
            "latest_downloads": [],
            "latest_qb_sync": [],
            "latest_qb_attempts": [],
            "ai_suggestions": [],
            "world_clocks": [],
        },
    }

    response = client.post(
        "/edge/projects/integration-full/snapshot",
        headers={"X-AgentAI-Token": "secret-token"},
        json=payload,
    )
    assert response.status_code == 200

    projects = client.get("/projects")
    assert projects.status_code == 200
    integration = next(item for item in projects.json() if item["id"] == "integration-full")

    assert integration["integration_ops"]["source_mode"] == "remote"
    assert integration["integration_ops"]["source_machine_name"] == "Stockton Frontdesk"
    assert integration["integration_ops"]["summary"]["download_gap_count"] == 3
    assert len(integration["integration_ops"]["remote_nodes"]) == 1


def test_edge_command_queue_dispatch_and_result(monkeypatch, tmp_path):
    temp_db = ControlPlaneDB(db_path=str(tmp_path / "control-plane.db"))
    monkeypatch.setattr(api_main, "db", temp_db)
    monkeypatch.setattr(api_main, "MASTER_DIR", Path(tmp_path / "Master"))
    monkeypatch.setenv("AGENTAI_EDGE_TOKEN", "secret-token")

    client = TestClient(api_main.app)

    created = client.post(
        "/projects/integration-full/commands",
        json={
            "machine_id": "stockton-frontdesk-01",
            "machine_name": "Stockton Frontdesk",
            "command_type": "download_missing_reports",
            "title": "Stockton catch-up",
            "payload": {
                "store": "Stockton",
                "start_date": "2026-04-05",
                "end_date": "2026-04-06",
                "report_types": ["sales_summary", "orders"],
            },
        },
    )
    assert created.status_code == 200
    command_id = created.json()["id"]

    dispatched = client.get(
        "/edge/projects/integration-full/commands/stockton-frontdesk-01",
        headers={"X-AgentAI-Token": "secret-token"},
    )
    assert dispatched.status_code == 200
    command = dispatched.json()["command"]
    assert command["id"] == command_id
    assert command["status"] == "dispatched"

    acknowledged = client.post(
        f"/edge/commands/{command_id}/ack",
        headers={"X-AgentAI-Token": "secret-token"},
        json={"heartbeat_seconds": 120},
    )
    assert acknowledged.status_code == 200
    assert acknowledged.json()["command"]["status"] == "running"

    heartbeat = client.post(
        f"/edge/commands/{command_id}/heartbeat",
        headers={"X-AgentAI-Token": "secret-token"},
        json={"heartbeat_seconds": 120},
    )
    assert heartbeat.status_code == 200
    assert heartbeat.json()["command"]["last_heartbeat_at"] is not None

    completed = client.post(
        f"/edge/commands/{command_id}/result",
        headers={"X-AgentAI-Token": "secret-token"},
        json={"status": "success", "result": {"success": 4, "failed": 0, "total": 4}},
    )
    assert completed.status_code == 200
    assert completed.json()["command"]["status"] == "success"

    commands = client.get("/projects/integration-full/commands")
    assert commands.status_code == 200
    assert commands.json()[0]["result"]["success"] == 4


def test_edge_command_retries_then_fails_after_lease_expiry(tmp_path):
    db = ControlPlaneDB(db_path=str(tmp_path / "control-plane.db"))
    created = db.create_edge_command(
        project_id="integration-full",
        machine_id="stockton-frontdesk-01",
        machine_name="Stockton Frontdesk",
        command_type="download_missing_reports",
        payload={"store": "Stockton"},
        max_attempts=2,
    )

    first = db.dispatch_next_edge_command(project_id="integration-full", machine_id="stockton-frontdesk-01", lease_seconds=1)
    assert first is not None
    db.acknowledge_edge_command(command_id=created["id"], heartbeat_seconds=1)

    with db._conn() as conn:
        conn.execute(
            "UPDATE cp_edge_commands SET lease_expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", created["id"]),
        )
        conn.commit()

    second = db.dispatch_next_edge_command(project_id="integration-full", machine_id="stockton-frontdesk-01", lease_seconds=1)
    assert second is not None
    assert second["attempt_count"] == 2

    with db._conn() as conn:
        conn.execute(
            "UPDATE cp_edge_commands SET status = 'running', lease_expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", created["id"]),
        )
        conn.commit()

    none_left = db.dispatch_next_edge_command(project_id="integration-full", machine_id="stockton-frontdesk-01", lease_seconds=1)
    assert none_left is None
    latest = db.list_edge_commands(project_id="integration-full", machine_id="stockton-frontdesk-01", limit=1)[0]
    assert latest["status"] == "failed"
