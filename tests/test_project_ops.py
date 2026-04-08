from __future__ import annotations

from pathlib import Path

from apps.api import main as api_main
from apps.api.project_ops import build_project_ops_profile


def test_build_project_ops_profile_for_next_frontend(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"name":"review-dashboard","scripts":{"dev":"next dev","build":"next build"},"dependencies":{"next":"14.2.15"}}',
        encoding="utf-8",
    )
    (tmp_path / ".env.local.example").write_text("NEXT_PUBLIC_API_URL=\n", encoding="utf-8")

    profile = build_project_ops_profile(
        "review-dashboard",
        tmp_path,
        {"name": "ReviewOps Dashboard", "type": "node"},
        "idle",
    )

    assert profile["kind"] == "next_frontend"
    assert any(signal["label"] == "Env template" for signal in profile["signals"])
    assert any(item["id"] == "review-dashboard-frontend-verify" for item in profile["suggestions"])
    assert any(item["id"] == "review-dashboard-qa-simulate" and item["action_type"] == "qa_simulation" for item in profile["suggestions"])


def test_build_project_ops_profile_for_python_service(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='review-system'\n", encoding="utf-8")
    (tmp_path / "docker-compose.yml").write_text("services:\n  db:\n    image: postgres\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("DATABASE_URL=\n", encoding="utf-8")

    profile = build_project_ops_profile(
        "review-system",
        tmp_path,
        {"name": "Review Automation System", "type": "python"},
        "idle",
    )

    assert profile["kind"] == "python_service"
    assert any(signal["label"] == "Infrastructure" for signal in profile["signals"])
    assert any(item["id"] == "review-system-service-verify" for item in profile["suggestions"])
    assert any(item["id"] == "review-system-qa-simulate" and item["action_type"] == "qa_simulation" for item in profile["suggestions"])


def test_projects_endpoint_uses_relative_path(monkeypatch, tmp_path):
    nested = tmp_path / "review" / "review-system"
    nested.mkdir(parents=True)
    (nested / "pyproject.toml").write_text("[project]\nname='review-system'\n", encoding="utf-8")
    (nested / "README.md").write_text("review system", encoding="utf-8")

    monkeypatch.setattr(api_main, "MASTER_DIR", tmp_path)
    monkeypatch.setattr(
        api_main,
        "PROJECT_REGISTRY",
        {
            "review-system": {
                "name": "Review Automation System",
                "type": "python",
                "category": "reviews",
                "description": "Auto-fetch reviews",
                "relative_path": "review/review-system",
                "port": 8000,
                "tech": ["FastAPI"],
                "github": "liemdo28/review-automation-system",
            }
        },
    )

    projects = api_main.list_projects()

    assert len(projects) == 1
    assert projects[0]["exists"] is True
    assert Path(projects[0]["local_path"]) == nested
    assert projects[0]["ops_profile"]["kind"] == "python_service"
    assert any(item["action_type"] == "qa_simulation" for item in projects[0]["ops_profile"]["suggestions"])
