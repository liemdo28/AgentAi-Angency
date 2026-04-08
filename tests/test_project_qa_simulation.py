from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api import main as api_main
from db.repository import ControlPlaneDB


def test_project_qa_simulation_endpoint(monkeypatch, tmp_path):
    temp_db = ControlPlaneDB(db_path=str(tmp_path / "control-plane.db"))
    project_root = tmp_path / "Master"
    project_dir = project_root / "review" / "review-dashboard"
    project_dir.mkdir(parents=True)
    (project_dir / "package.json").write_text(
        '{"name":"review-dashboard","scripts":{"dev":"next dev","build":"next build"},"dependencies":{"next":"14.2.15"}}',
        encoding="utf-8",
    )
    (project_dir / ".env.example").write_text("NEXT_PUBLIC_API_URL=\n", encoding="utf-8")

    monkeypatch.setattr(api_main, "db", temp_db)
    monkeypatch.setattr(api_main, "MASTER_DIR", project_root)
    monkeypatch.setattr(
        api_main,
        "PROJECT_REGISTRY",
        {
            "review-dashboard": {
                "name": "ReviewOps Dashboard",
                "type": "node",
                "category": "reviews",
                "description": "Next.js frontend for review management system",
                "relative_path": "review/review-dashboard",
                "port": 3000,
                "tech": ["Next.js", "React", "Tailwind"],
                "github": None,
            }
        },
    )

    client = TestClient(api_main.app)
    response = client.post(
        "/projects/review-dashboard/qa-simulate",
        json={
            "goal": "Validate CEO -> departments -> tester loop for the review dashboard",
            "tester_count": 1000,
            "max_iterations": 100,
            "pass_threshold": 8.5,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "review-dashboard"
    assert payload["tester_count"] == 1000
    assert payload["max_iterations"] == 100
    assert payload["iterations_run"] >= 1
    assert payload["iterations_run"] <= 100
    assert payload["final_score"] >= 8.5
    assert payload["passed"] is True
    assert payload["final_report"]["handoff_target"] == "CEO -> user/admin"
    assert len(payload["department_plan"]) >= 4
    assert len(payload["history"]) == payload["iterations_run"]
    assert payload["latest_iteration"]["pass"] is True
