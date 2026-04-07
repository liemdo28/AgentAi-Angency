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
