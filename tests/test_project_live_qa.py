from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api import main as api_main
from core.orchestrator import executor as executor_module
from db.repository import ControlPlaneDB


def _project_registry():
    return {
        "review-dashboard": {
            "name": "ReviewOps Dashboard",
            "type": "node",
            "category": "reviews",
            "description": "Next.js frontend for review management system",
            "relative_path": "review/review-dashboard",
            "port": 3000,
            "tech": ["Next.js", "React", "Tailwind"],
            "github": None,
            "url": "https://review-dashboard.example.com",
        }
    }


def _failed_live_result(score: float = 7.9) -> dict:
    return {
        "project_id": "review-dashboard",
        "project_name": "ReviewOps Dashboard",
        "target_url": "https://review-dashboard.example.com",
        "profiles": [{"name": "desktop"}, {"name": "tablet"}, {"name": "mobile"}],
        "aggregate_scores": {"errors": 7.4, "ui": 8.0, "workflow": 7.8, "features": 8.0},
        "final_score": score,
        "pass_threshold": 8.5,
        "passed": False,
        "summary": "Live browser QA stayed below the release threshold.",
        "findings": [
            {
                "category": "ui",
                "severity": "medium",
                "title": "Mobile layout drifts on the primary dashboard",
                "detail": "Spacing and hierarchy collapse on narrow viewports.",
            },
            {
                "category": "workflow",
                "severity": "high",
                "title": "Submit flow throws on retry",
                "detail": "The browser surfaced a visible error during the main action flow.",
            },
        ],
    }


def _passed_live_result(score: float = 8.8) -> dict:
    return {
        "project_id": "review-dashboard",
        "project_name": "ReviewOps Dashboard",
        "target_url": "https://review-dashboard.example.com",
        "profiles": [{"name": "desktop"}, {"name": "tablet"}, {"name": "mobile"}],
        "aggregate_scores": {"errors": 8.7, "ui": 8.8, "workflow": 8.8, "features": 8.9},
        "final_score": score,
        "pass_threshold": 8.5,
        "passed": True,
        "summary": "Live browser QA ran across 3 viewport(s) and finished above threshold.",
        "findings": [],
    }


def _setup(monkeypatch, tmp_path):
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
    monkeypatch.setattr(api_main, "PROJECT_REGISTRY", _project_registry())
    return temp_db


def test_project_live_qa_creates_fix_tasks_on_failure(monkeypatch, tmp_path):
    temp_db = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(api_main, "run_live_project_qa", lambda *args, **kwargs: _failed_live_result())

    client = TestClient(api_main.app)
    response = client.post(
        "/projects/review-dashboard/qa-live",
        json={"pass_threshold": 8.5, "timeout_ms": 12000, "auto_create_fix_tasks": True, "max_retest_cycles": 3},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["passed"] is False
    assert payload["followup_goal"] is not None
    assert payload["loop_summary"]["status"] == "fixing"
    assert payload["loop_summary"]["max_retest_cycles"] == 3

    goal_tasks = temp_db.list_tasks_by_goal(payload["followup_goal"]["id"])
    assert any(task["task_type"] == "qa_live_fix" for task in goal_tasks)
    assert any(task["task_type"] == "qa_live_coordination" for task in goal_tasks)


def test_execute_task_auto_triggers_live_retest_when_remediation_finishes(monkeypatch, tmp_path):
    temp_db = _setup(monkeypatch, tmp_path)
    live_results = [_failed_live_result(), _passed_live_result()]

    def fake_live_qa(*args, **kwargs):
        return live_results.pop(0)

    monkeypatch.setattr(api_main, "run_live_project_qa", fake_live_qa)
    monkeypatch.setattr(
        executor_module.AgentExecutor,
        "execute",
        lambda self, task: {"status": "success", "output": f"fixed {task['id']}"},
    )

    client = TestClient(api_main.app)
    response = client.post(
        "/projects/review-dashboard/qa-live",
        json={"pass_threshold": 8.5, "timeout_ms": 12000, "auto_create_fix_tasks": True, "max_retest_cycles": 3},
    )
    goal_id = response.json()["followup_goal"]["id"]

    last_payload = None
    for task in temp_db.list_tasks_by_goal(goal_id):
        execute_response = client.post(f"/tasks/{task['id']}/execute")
        assert execute_response.status_code == 200
        last_payload = execute_response.json()

    assert last_payload is not None
    assert last_payload["qa_retest"]["result"]["passed"] is True
    assert last_payload["qa_retest"]["result"]["loop_summary"]["status"] == "passed"

    retests = [task for task in temp_db.list_tasks_by_goal(goal_id) if task["task_type"] == "qa_live_retest"]
    assert len(retests) == 1
    assert retests[0]["status"] == "success"


def test_execute_task_escalates_after_retry_limit(monkeypatch, tmp_path):
    temp_db = _setup(monkeypatch, tmp_path)
    live_results = [_failed_live_result(), _failed_live_result(score=8.1)]

    def fake_live_qa(*args, **kwargs):
        return live_results.pop(0)

    monkeypatch.setattr(api_main, "run_live_project_qa", fake_live_qa)
    monkeypatch.setattr(
        executor_module.AgentExecutor,
        "execute",
        lambda self, task: {"status": "success", "output": f"fixed {task['id']}"},
    )

    client = TestClient(api_main.app)
    response = client.post(
        "/projects/review-dashboard/qa-live",
        json={"pass_threshold": 8.5, "timeout_ms": 12000, "auto_create_fix_tasks": True, "max_retest_cycles": 1},
    )
    goal_id = response.json()["followup_goal"]["id"]

    last_payload = None
    for task in temp_db.list_tasks_by_goal(goal_id):
        execute_response = client.post(f"/tasks/{task['id']}/execute")
        assert execute_response.status_code == 200
        last_payload = execute_response.json()

    assert last_payload is not None
    qa_retest = last_payload["qa_retest"]["result"]
    assert qa_retest["passed"] is False
    assert qa_retest["escalation_task"] is not None
    assert qa_retest["followup_tasks"] == []
    assert qa_retest["loop_summary"]["status"] == "escalated"

    goal_tasks = temp_db.list_tasks_by_goal(goal_id)
    escalations = [task for task in goal_tasks if task["task_type"] == "qa_live_escalation"]
    assert len(escalations) == 1
    assert escalations[0]["assigned_agent_id"] == "workflow"
