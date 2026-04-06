"""
Comprehensive API test suite for src/api.py.

All heavy dependencies (anthropic, openai, langgraph, sendgrid, aiosqlite,
dotenv, httpx) are stubbed at the sys.modules level before any src import so
the TestClient can be constructed without real credentials or a live database.

For each test the internal collaborators used inside endpoint handlers
(init_db, engine, store, TaskRepository, run_task_sync) are patched via
unittest.mock.patch so that the routing, serialisation, and error-handling
logic of the API layer is exercised in isolation.

PATCH TARGET RATIONALE
----------------------
Every task / DB import inside api.py is done *locally inside function bodies*
(e.g. ``from src.db.repositories.task_repo import TaskRepository``), not at
the api.py module level.  Python's ``from X import Y`` binds the name Y in the
calling module's namespace only when that line executes — so patching
``src.api.TaskRepository`` would patch a name that never exists in src.api and
have no effect.  The correct patch targets are therefore the *defining*
modules:
  - src.db.connection.init_db
  - src.db.connection.get_db
  - src.db.repositories.task_repo.TaskRepository
  - src.task_runner.run_task_sync
  - src.tasks.models.Task          (constructor used inside create_task)
  - src.tasks.models.TaskStatus    (used inside cancel_task comparison)
  - src.ingestion.data_collection.send_data_request_email
  - src.ingestion.data_collection.process_inbound_email
"""

from __future__ import annotations

import base64
import importlib
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub every heavy/optional dependency BEFORE any src import so that the
# module-level WorkflowEngine() constructor in api.py succeeds without
# real policy files, LLM clients, or a live SQLite database.
# ---------------------------------------------------------------------------
for _m in [
    "dotenv",
    "anthropic",
    "openai",
    "langgraph",
    "langgraph.graph",
    "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "sendgrid",
    "aiosqlite",
]:
    sys.modules.setdefault(_m, MagicMock())

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Patch WorkflowEngine and store at module-import time so that the
# ``engine = WorkflowEngine()`` line at module scope in api.py uses a mock,
# and ``store.load()`` (called during lifespan) never touches disk.
# ---------------------------------------------------------------------------
_mock_engine = MagicMock()
_mock_store = MagicMock()

_mock_store.load.return_value = {}
_mock_store.save.return_value = None
_mock_store.handoff_to_dict.return_value = {}

_before_import = set(sys.modules.keys())

with (
    patch.dict("sys.modules", {"store": _mock_store}),
    patch("src.api.WorkflowEngine", return_value=_mock_engine),
):
    from src.api import app
    import src.api as _api_mod
    # Capture all modules loaded during api import so we can restore them.
    _api_modules_snapshot = {
        k: v for k, v in sys.modules.items() if k not in _before_import and k != "store"
    }

# patch.dict restores sys.modules on exit, removing every module that was
# added during the block (models, engine, store, policies, src, src.api, …).
# We re-register them so that:
#   1. patch("src.api.store") / patch("src.api.engine") can locate src.api
#   2. Tests that do `from models import HandoffNotFoundError` get the same
#      class object that api.py already bound — ensuring except-clauses match.
sys.modules.update(_api_modules_snapshot)
sys.modules.pop("store", None)
sys.modules["store"] = importlib.import_module("store")

# ---------------------------------------------------------------------------
# Test client — startup / shutdown lifespan runs automatically.
# raise_server_exceptions=False so 4xx/5xx come back as response objects
# rather than raising Python exceptions inside tests.
# ---------------------------------------------------------------------------
client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_handoff_dict(
    id_: str | None = None,
    state: str = "draft",
) -> dict:
    """Return a plain dict shaped like the HandoffOut Pydantic model."""
    hid = id_ or str(uuid.uuid4())
    return {
        "id": hid,
        "state": state,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "notes": "",
        "provided_inputs": ["lead_profile", "deal_status", "target_kpi"],
        "policy": {
            "from_department": "sales",
            "to_department": "account",
            "required_inputs": ["lead_profile", "deal_status", "target_kpi"],
            "expected_outputs": ["project_brief", "kickoff_schedule"],
            "sla_hours": 8,
            "approver_role": "Account Manager",
        },
    }


def _make_handoff_instance(id_: str | None = None, state: str = "draft") -> MagicMock:
    """Return a MagicMock shaped like a HandoffInstance."""
    hid = id_ or str(uuid.uuid4())
    mock_h = MagicMock()
    mock_h.id = hid
    return mock_h


def _make_task(
    id_: str | None = None,
    status_value: str = "draft",
    score: float = 0.0,
) -> MagicMock:
    """Return a MagicMock shaped like a Task dataclass as consumed by _task_to_out()."""
    from src.tasks.models import Priority, TaskStatus

    tid = id_ or str(uuid.uuid4())
    t = MagicMock()
    t.id = tid
    t.goal = "Run a Q1 report"
    t.description = ""
    t.task_type = "new_campaign"
    t.status = TaskStatus(status_value)
    t.priority = Priority.NORMAL
    t.score = score
    t.account_id = ""
    t.campaign_id = ""
    t.current_department = ""
    t.retry_count = 0
    t.created_at = "2026-01-01T00:00:00Z"
    t.started_at = None
    t.completed_at = None
    t.final_output_text = ""
    t.notes = ""
    return t


def _make_run_result(task_id: str, status: str = "passed", score: float = 92.5) -> dict:
    return {
        "task_id": task_id,
        "status": status,
        "score": score,
        "final_output": "Report generated successfully.",
        "retry_count": 0,
        "errors": [],
    }


# ---------------------------------------------------------------------------
# Common patch target strings
# ---------------------------------------------------------------------------
PATCH_ENGINE = "src.api.engine"
PATCH_STORE = "src.api.store"

# All DB / task imports live inside function bodies — patch the defining module:
PATCH_INIT_DB = "src.db.connection.init_db"
PATCH_GET_DB = "src.db.connection.get_db"
PATCH_TASK_REPO = "src.db.repositories.task_repo.TaskRepository"
PATCH_RUN_TASK_SYNC = "src.task_runner.run_task_sync"
PATCH_SEND_EMAIL = "src.ingestion.data_collection.send_data_request_email"
PATCH_PROCESS_INBOUND = "src.ingestion.data_collection.process_inbound_email"


# ===========================================================================
# HANDOFF ENDPOINTS
# ===========================================================================

# 1. POST /handoffs with valid body → 201
def test_post_handoff_valid_returns_201():
    hd = _make_handoff_dict()
    mock_h = _make_handoff_instance(id_=hd["id"])

    mock_engine = MagicMock()
    mock_engine.initiate.return_value = mock_h
    mock_engine.export_handoffs.return_value = {}

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd
    mock_store.save.return_value = None

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.post(
            "/handoffs",
            json={
                "from_department": "sales",
                "to_department": "account",
                "inputs": ["lead_profile", "deal_status", "target_kpi"],
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == hd["id"]
    assert body["state"] == "draft"
    assert "policy" in body


# 2. POST /handoffs missing from_department → 422
def test_post_handoff_missing_from_department_returns_422():
    resp = client.post(
        "/handoffs",
        json={"to_department": "account", "inputs": ["lead_profile"]},
    )
    assert resp.status_code == 422


# 3. GET /handoffs → 200, returns list
def test_list_handoffs_returns_200_with_list():
    hd = _make_handoff_dict()
    mock_h = _make_handoff_instance(id_=hd["id"])

    mock_engine = MagicMock()
    mock_engine.all_handoffs.return_value = [mock_h]

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.get("/handoffs")

    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert "items" in body
    assert isinstance(body["items"], list)
    assert body["total"] == 1


# 4. GET /handoffs?state=draft → 200
def test_list_handoffs_filter_by_state_draft_returns_200():
    hd = _make_handoff_dict(state="draft")
    mock_h = _make_handoff_instance(id_=hd["id"], state="draft")

    mock_engine = MagicMock()
    mock_engine.get_by_state.return_value = [mock_h]

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.get("/handoffs?state=draft")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["items"], list)


# 5. GET /handoffs/{id} existing → 200
def test_get_handoff_existing_returns_200():
    hd = _make_handoff_dict()
    mock_h = _make_handoff_instance(id_=hd["id"])

    mock_engine = MagicMock()
    mock_engine.get_handoff.return_value = mock_h

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.get(f"/handoffs/{hd['id']}")

    assert resp.status_code == 200
    assert resp.json()["id"] == hd["id"]


# 6. GET /handoffs/{id} nonexistent → 404
def test_get_handoff_nonexistent_returns_404():
    from models import HandoffNotFoundError

    mock_engine = MagicMock()
    mock_engine.get_handoff.side_effect = HandoffNotFoundError("not found")

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.get("/handoffs/doesnotexist")

    assert resp.status_code == 404
    assert "detail" in resp.json()


# 7. PATCH /handoffs/{id}/approve → 200
def test_approve_handoff_returns_200():
    hd = _make_handoff_dict(state="approved")
    mock_h = _make_handoff_instance(id_=hd["id"])

    mock_engine = MagicMock()
    mock_engine.approve.return_value = mock_h
    mock_engine.export_handoffs.return_value = {}

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd
    mock_store.save.return_value = None

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.patch(f"/handoffs/{hd['id']}/approve")

    assert resp.status_code == 200
    assert resp.json()["state"] == "approved"


# 8. PATCH /handoffs/{id}/approve nonexistent → 404
def test_approve_nonexistent_handoff_returns_404():
    from models import HandoffNotFoundError

    mock_engine = MagicMock()
    mock_engine.approve.side_effect = HandoffNotFoundError("not found")

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.patch("/handoffs/doesnotexist/approve")

    assert resp.status_code == 404
    assert "detail" in resp.json()


# 9. PATCH /handoffs/{id}/block with {"reason":"test"} → 200
def test_block_handoff_returns_200():
    hd = _make_handoff_dict(state="blocked")
    mock_h = _make_handoff_instance(id_=hd["id"])

    mock_engine = MagicMock()
    mock_engine.block.return_value = mock_h
    mock_engine.export_handoffs.return_value = {}

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd
    mock_store.save.return_value = None

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.patch(
            f"/handoffs/{hd['id']}/block",
            json={"reason": "test"},
        )

    assert resp.status_code == 200
    assert resp.json()["state"] == "blocked"


# 10. POST /handoffs/refresh-overdue → 200
def test_refresh_overdue_returns_200():
    mock_h1 = MagicMock()
    mock_h1.id = str(uuid.uuid4())
    mock_h2 = MagicMock()
    mock_h2.id = str(uuid.uuid4())

    mock_engine = MagicMock()
    mock_engine.refresh_overdue.return_value = [mock_h1, mock_h2]
    mock_engine.export_handoffs.return_value = {}

    mock_store = MagicMock()
    mock_store.save.return_value = None

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.post("/handoffs/refresh-overdue")

    assert resp.status_code == 200
    body = resp.json()
    assert body["flagged_count"] == 2
    assert isinstance(body["ids"], list)
    assert len(body["ids"]) == 2


# 11. GET /status → 200 with dict
def test_get_status_returns_200_with_count_fields():
    mock_engine = MagicMock()
    mock_engine.status.return_value = {
        "draft": 3,
        "approved": 1,
        "blocked": 0,
        "overdue": 2,
    }
    with patch(PATCH_ENGINE, mock_engine):
        resp = client.get("/status")

    assert resp.status_code == 200
    body = resp.json()
    assert "draft" in body
    assert "approved" in body
    assert "blocked" in body
    assert "overdue" in body
    assert isinstance(body["draft"], int)


# 12. GET /routes → 200 with list
def test_get_routes_returns_200_with_list():
    mock_policy = MagicMock()
    mock_policy.from_department = "sales"
    mock_policy.to_department = "account"
    mock_policy.sla_hours = 8
    mock_policy.approver_role = "Account Manager"
    mock_policy.required_inputs = ["lead_profile"]
    mock_policy.expected_outputs = ["project_brief"]

    mock_engine = MagicMock()
    mock_engine.list_routes.return_value = [mock_policy]

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.get("/routes")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 1
    route = body[0]
    assert route["from"] == "sales"
    assert route["to"] == "account"
    assert "sla_hours" in route
    assert "required_inputs" in route


# ===========================================================================
# TASK ENDPOINTS
# ===========================================================================

# 13. POST /tasks with {"goal":"Run campaign","task_type":"new_campaign"} → 201 with id field
def test_create_task_valid_returns_201():
    """
    Because create_task does ``from src.tasks.models import Task`` inside the
    function body, we patch ``src.tasks.models.Task`` (the constructor in the
    defining module) so the call inside create_task returns our mock task.
    """
    task = _make_task()

    mock_repo = MagicMock()
    mock_repo.create.return_value = None

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
        patch("src.tasks.models.Task", return_value=task),
    ):
        resp = client.post(
            "/tasks",
            json={"goal": "Run campaign", "task_type": "new_campaign"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["id"] == task.id


# 14. POST /tasks missing goal → 422
def test_create_task_missing_goal_returns_422():
    resp = client.post("/tasks", json={"description": "no goal here"})
    assert resp.status_code == 422


# 15. POST /tasks with empty goal string "" → 422
def test_create_task_empty_goal_returns_422():
    resp = client.post("/tasks", json={"goal": "   "})
    assert resp.status_code == 422


# 16. GET /tasks → 200
def test_list_tasks_returns_200_empty_list():
    mock_repo = MagicMock()
    mock_repo.list_active.return_value = []

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get("/tasks")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# 17. GET /tasks?status=passed → 200
def test_list_tasks_by_status_filter():
    task = _make_task(status_value="passed")

    mock_repo = MagicMock()
    mock_repo.list_by_status.return_value = [task]

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get("/tasks?status=passed")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "passed"


# 18. GET /tasks/{id} existing → 200 with goal field
def test_get_task_existing_returns_200():
    task = _make_task()

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get(f"/tasks/{task.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == task.id
    assert "goal" in body
    assert body["goal"] == task.goal


# 19. GET /tasks/{id} nonexistent → 404
def test_get_task_nonexistent_returns_404():
    mock_repo = MagicMock()
    mock_repo.get.return_value = None

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get("/tasks/doesnotexist")

    assert resp.status_code == 404
    assert "detail" in resp.json()


# 20. POST /tasks/{id}/run → 202 with queued status
def test_run_task_returns_202_with_queued_status():
    """
    The API now queues work asynchronously and returns 202 immediately.
    """
    task = _make_task()

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
        patch("src.api._run_task_background"),
    ):
        resp = client.post(f"/tasks/{task.id}/run")

    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"] == task.id
    assert body["status"] == "IN_PROGRESS"
    assert "queued" in body["message"].lower()
    mock_repo.upsert.assert_called_once()


# 21. POST /tasks/{id}/run nonexistent id → 404
def test_run_task_nonexistent_returns_404():
    mock_repo = MagicMock()
    mock_repo.get.return_value = None

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post("/tasks/doesnotexist/run")

    assert resp.status_code == 404
    assert "detail" in resp.json()


# 22. POST /tasks/{id}/cancel → 200
def test_cancel_task_returns_200():
    """
    cancel_task does ``from src.tasks.models import TaskStatus`` inside the
    function body; the status comparison uses the real TaskStatus enum loaded
    from that module.  Our mock task.status = TaskStatus("in_progress") so it
    won't match the terminal states, and the handler proceeds to cancel.
    """
    task = _make_task(status_value="in_progress")

    mock_repo = MagicMock()
    mock_repo.get.return_value = task
    mock_repo.update_status.return_value = None

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post(f"/tasks/{task.id}/cancel")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["task_id"] == task.id


# 23. POST /tasks/{id}/cancel nonexistent → 404
def test_cancel_task_nonexistent_returns_404():
    mock_repo = MagicMock()
    mock_repo.get.return_value = None

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post("/tasks/doesnotexist/cancel")

    assert resp.status_code == 404
    assert "detail" in resp.json()


# 24. GET /tasks/{id}/review-history → 200
def test_get_review_history_returns_200():
    """
    get_review_history does ``from src.db.connection import get_db, init_db``
    inside the function body — patch both at the defining module.
    """
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_GET_DB, return_value=mock_conn),
    ):
        tid = str(uuid.uuid4())
        resp = client.get(f"/tasks/{tid}/review-history")

    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body
    assert "history" in body
    assert isinstance(body["history"], list)


# ===========================================================================
# DATA COLLECTION ENDPOINTS
# ===========================================================================

# 25. POST /data-collection/request with account_id, account_email, report_date → 200
def test_data_collection_request_returns_200():
    result = {
        "status": "sent",
        "message_id": "abc123",
        "account_id": "acct-001",
    }

    with patch(PATCH_SEND_EMAIL, return_value=result):
        resp = client.post(
            "/data-collection/request",
            json={
                "account_id": "acct-001",
                "account_email": "client@example.com",
                "report_date": "2026-03",
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["status"] == "sent"


# 26. POST /data-collection/inbound with raw_bytes (base64), account_mapping → 200
def test_data_collection_inbound_returns_200():
    raw = b"From: client@example.com\r\nSubject: Report\r\n\r\nBody text"
    encoded = base64.b64encode(raw).decode()

    result = {
        "status": "processed",
        "account_id": "acct-001",
        "attachments_saved": [],
        "task_id": None,
    }

    with patch(PATCH_PROCESS_INBOUND, return_value=result):
        resp = client.post(
            "/data-collection/inbound",
            json={
                "raw_email_b64": encoded,
                "account_mapping": {"example.com": "acct-001"},
                "trigger_task": False,
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "account_id" in body


# ===========================================================================
# RESPONSE SHAPE TESTS
# ===========================================================================

# 27. POST /tasks response body has keys: id, status, goal, score
def test_create_task_response_shape():
    task = _make_task(score=0.0)

    mock_repo = MagicMock()
    mock_repo.create.return_value = None

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
        patch("src.tasks.models.Task", return_value=task),
    ):
        resp = client.post("/tasks", json={"goal": "Validate schema"})

    assert resp.status_code == 201
    body = resp.json()
    for key in ("id", "status", "goal", "score"):
        assert key in body, f"Missing field in CreateTask response: {key}"


# 28. GET /tasks/{id}/review-history returns list
def test_get_review_history_returns_list_in_history_field():
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_GET_DB, return_value=mock_conn),
    ):
        tid = str(uuid.uuid4())
        resp = client.get(f"/tasks/{tid}/review-history")

    assert resp.status_code == 200
    assert isinstance(resp.json()["history"], list)


# ===========================================================================
# ADDITIONAL EDGE-CASE TESTS (total 30+)
# ===========================================================================

# 29. Run task response shape: task_id, status, message
def test_run_task_response_shape():
    task = _make_task()

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
        patch("src.api._run_task_background"),
    ):
        resp = client.post(f"/tasks/{task.id}/run")

    assert resp.status_code == 202
    body = resp.json()
    for field in ("task_id", "status", "message"):
        assert field in body, f"Missing field in RunTaskResult: {field}"
    assert isinstance(body["message"], str)


# 30. Blank department name → 422 (Pydantic dept_not_blank validator)
def test_post_handoff_blank_department_returns_422():
    resp = client.post(
        "/handoffs",
        json={"from_department": "  ", "to_department": "account", "inputs": ["x"]},
    )
    assert resp.status_code == 422


# 31. Empty inputs list → 422 (Pydantic inputs_not_empty validator)
def test_post_handoff_empty_inputs_returns_422():
    resp = client.post(
        "/handoffs",
        json={"from_department": "sales", "to_department": "account", "inputs": []},
    )
    assert resp.status_code == 422


# 32. Invalid state query param → 400
def test_list_handoffs_invalid_state_returns_400():
    mock_engine = MagicMock()
    mock_engine.all_handoffs.return_value = []

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.get("/handoffs?state=INVALID_STATE")

    assert resp.status_code == 400
    assert "detail" in resp.json()


# 33. Cancel PASSED task → 409 Conflict
def test_cancel_task_already_passed_returns_409():
    task = _make_task(status_value="passed")

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post(f"/tasks/{task.id}/cancel")

    assert resp.status_code == 409


# 34. account_email without '@' → 422
def test_data_collection_request_invalid_email_returns_422():
    resp = client.post(
        "/data-collection/request",
        json={
            "account_id": "acct-001",
            "account_email": "not-an-email",
            "report_date": "2026-03",
        },
    )
    assert resp.status_code == 422


# 35. Invalid base64 in inbound payload → 400
def test_data_collection_inbound_bad_base64_returns_400():
    resp = client.post(
        "/data-collection/inbound",
        json={
            "raw_email_b64": "!!!not-valid-base64!!!",
            "account_mapping": {"example.com": "acct-001"},
        },
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


# 36. send_data_request_email returns status=failed → 502
def test_data_collection_request_failed_status_returns_502():
    with patch(
        PATCH_SEND_EMAIL,
        return_value={"status": "failed", "error": "SMTP timeout"},
    ):
        resp = client.post(
            "/data-collection/request",
            json={
                "account_id": "acct-001",
                "account_email": "client@example.com",
                "report_date": "2026-03",
            },
        )
    assert resp.status_code == 502


# 37. enqueue failure in run_task → 500
def test_run_task_enqueue_runtime_error_returns_500():
    task = _make_task()

    mock_repo = MagicMock()
    mock_repo.get.return_value = task
    mock_repo.upsert.side_effect = RuntimeError("Queue exploded")

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post(f"/tasks/{task.id}/run")

    assert resp.status_code == 500
    assert "detail" in resp.json()


# 38. SQLite OperationalError in run_task → 503
def test_run_task_db_operational_error_returns_503():
    import sqlite3

    task = _make_task()

    mock_repo = MagicMock()
    mock_repo.get.side_effect = sqlite3.OperationalError("database is locked")

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post(f"/tasks/{task.id}/run")

    assert resp.status_code == 503


# 39. GET /tasks?campaign_id=xxx filters by campaign
def test_list_tasks_by_campaign_filter():
    task = _make_task()
    task.campaign_id = "camp-42"

    mock_repo = MagicMock()
    mock_repo.list_by_campaign.return_value = [task]

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get("/tasks?campaign_id=camp-42")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# 40. Priority 99 is outside enum → 400
def test_create_task_invalid_priority_returns_400():
    """
    Priority(99) raises ValueError inside the endpoint — mapped to 400.
    We still patch init_db and TaskRepository so the code path reaches
    the Priority() constructor rather than failing earlier on DB init.
    """
    mock_repo = MagicMock()

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post("/tasks", json={"goal": "Valid goal", "priority": 99})

    assert resp.status_code == 400
    assert "detail" in resp.json()


# 41. MissingInputsError from engine → 400
def test_handoff_missing_inputs_returns_400():
    from models import MissingInputsError

    mock_engine = MagicMock()
    mock_engine.initiate.side_effect = MissingInputsError("Missing: budget_approved")

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.post(
            "/handoffs",
            json={
                "from_department": "sales",
                "to_department": "account",
                "inputs": ["some_other_thing"],
            },
        )

    assert resp.status_code == 400
    assert "detail" in resp.json()


# 42. RouteNotFoundError from engine → 404
def test_post_handoff_unknown_route_returns_404():
    from models import RouteNotFoundError

    mock_engine = MagicMock()
    mock_engine.initiate.side_effect = RouteNotFoundError("No route sales->Unknown")

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.post(
            "/handoffs",
            json={
                "from_department": "sales",
                "to_department": "Unknown",
                "inputs": ["foo"],
            },
        )

    assert resp.status_code == 404
    assert "detail" in resp.json()


# 43. All 404 responses contain a string "detail" field
def test_404_responses_contain_detail_field():
    from models import HandoffNotFoundError

    mock_engine = MagicMock()
    mock_engine.get_handoff.side_effect = HandoffNotFoundError("not found")

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.get("/handoffs/no-such-id")

    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert isinstance(body["detail"], str)


# 44. GET /tasks/{id} score field is a float
def test_get_task_score_is_float():
    task = _make_task(score=87.3)

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get(f"/tasks/{task.id}")

    assert resp.status_code == 200
    assert isinstance(resp.json()["score"], float)
    assert resp.json()["score"] > 0


# 45. InvalidStateTransitionError on approve → 409 Conflict
def test_approve_already_blocked_handoff_returns_409():
    from models import InvalidStateTransitionError

    mock_engine = MagicMock()
    mock_engine.approve.side_effect = InvalidStateTransitionError(
        "Cannot approve handoff in state 'blocked'."
    )

    with patch(PATCH_ENGINE, mock_engine):
        resp = client.patch("/handoffs/some-id/approve")

    assert resp.status_code == 409
    assert "detail" in resp.json()


# 46. process_inbound_email returns unmatched → 422
def test_data_collection_inbound_unmatched_sender_returns_422():
    raw = b"From: unknown@no-match.com\r\nSubject: Report\r\n\r\nBody"
    encoded = base64.b64encode(raw).decode()

    with patch(
        PATCH_PROCESS_INBOUND,
        return_value={"status": "unmatched"},
    ):
        resp = client.post(
            "/data-collection/inbound",
            json={
                "raw_email_b64": encoded,
                "account_mapping": {"known.com": "acct-001"},
            },
        )

    assert resp.status_code == 422
    assert "detail" in resp.json()


# 47. GET /handoffs pagination offset/limit respected
def test_list_handoffs_pagination_offset():
    hd1 = _make_handoff_dict()
    hd2 = _make_handoff_dict()
    mock_h1 = _make_handoff_instance(id_=hd1["id"])
    mock_h2 = _make_handoff_instance(id_=hd2["id"])

    call_count = [0]

    def side_handoff_to_dict(h):
        # Return different dicts for different mocks
        if h is mock_h1:
            return hd1
        return hd2

    mock_engine = MagicMock()
    mock_engine.all_handoffs.return_value = [mock_h1, mock_h2]

    mock_store = MagicMock()
    mock_store.handoff_to_dict.side_effect = side_handoff_to_dict

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        # With offset=1 we should only get the second item
        resp = client.get("/handoffs?limit=1&offset=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2   # total is count before slicing
    assert len(body["items"]) == 1
    assert body["offset"] == 1
    assert body["limit"] == 1


# 48. GET /handoffs with multiple states — state=approved filter
def test_list_handoffs_filter_by_state_approved():
    hd = _make_handoff_dict(state="approved")
    mock_h = _make_handoff_instance(id_=hd["id"], state="approved")

    mock_engine = MagicMock()
    mock_engine.get_by_state.return_value = [mock_h]

    mock_store = MagicMock()
    mock_store.handoff_to_dict.return_value = hd

    with patch(PATCH_ENGINE, mock_engine), patch(PATCH_STORE, mock_store):
        resp = client.get("/handoffs?state=approved")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1


# 49. Cancel CANCELLED task → 409
def test_cancel_task_already_cancelled_returns_409():
    task = _make_task(status_value="cancelled")

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post(f"/tasks/{task.id}/cancel")

    assert resp.status_code == 409


# 50. Cancel DONE task → 409
def test_cancel_task_already_done_returns_409():
    task = _make_task(status_value="done")

    mock_repo = MagicMock()
    mock_repo.get.return_value = task

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.post(f"/tasks/{task.id}/cancel")

    assert resp.status_code == 409


# 51. GET /tasks?status=passed → list_by_status is called (not list_active)
def test_list_tasks_status_filter_calls_list_by_status():
    task = _make_task(status_value="passed")

    mock_repo = MagicMock()
    mock_repo.list_by_status.return_value = [task]
    mock_repo.list_active.return_value = []  # should NOT be called

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_TASK_REPO, return_value=mock_repo),
    ):
        resp = client.get("/tasks?status=passed")

    assert resp.status_code == 200
    mock_repo.list_by_status.assert_called_once_with("passed")
    mock_repo.list_active.assert_not_called()


# 52. review-history with rows that have breakdown_json → breakdown key in output
def test_get_review_history_with_breakdown_json():
    import json as _json

    breakdown_data = {"quality": 90.0, "accuracy": 85.0}
    row_mock = MagicMock()
    # Make dict(row) work by having __iter__ return items
    row_dict = {
        "id": str(uuid.uuid4()),
        "task_id": "tid-001",
        "step_name": "leader_review",
        "score": 87.5,
        "threshold": 80.0,
        "decision": "pass",
        "feedback": "Good work",
        "breakdown_json": _json.dumps(breakdown_data),
        "mode": "llm",
    }
    # patch dict() call behavior by making fetchall return dict-like rows
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [row_dict]
    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_cursor

    with (
        patch(PATCH_INIT_DB),
        patch(PATCH_GET_DB, return_value=mock_conn),
    ):
        resp = client.get("/tasks/tid-001/review-history")

    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "tid-001"
    assert "history" in body
