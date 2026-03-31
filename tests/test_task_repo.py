"""Comprehensive tests for TaskRepository, Task model, SLA, and KPI logic.

All tests use in-memory SQLite — no disk I/O, no external services.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub heavy/unavailable dependencies BEFORE any project imports
# ---------------------------------------------------------------------------
for _m in [
    "dotenv",
    "anthropic",
    "openai",
    "httpx",
    "langgraph",
    "langgraph.graph",
    "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "sendgrid",
]:
    sys.modules.setdefault(_m, MagicMock())

import pytest

from src.db.schema import SQL_SCHEMA
from src.tasks.models import Task, TaskStatus, Priority, now_iso


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def db_conn():
    """Fresh in-memory SQLite connection with full schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SQL_SCHEMA)
    return conn


@pytest.fixture
def repo(db_conn):
    """TaskRepository whose get_db is patched to our in-memory connection."""
    from src.db.repositories.task_repo import TaskRepository

    repo_instance = TaskRepository()
    with patch("src.db.repositories.task_repo.get_db", return_value=db_conn):
        yield repo_instance, db_conn


def _make_task(**kwargs) -> Task:
    """Helper: build a minimal valid Task, override any field via kwargs."""
    defaults = dict(goal="Test goal")
    defaults.update(kwargs)
    return Task(**defaults)


# ===========================================================================
# TaskRepository — CRUD
# ===========================================================================


class TestTaskRepositoryCreate:
    def test_create_returns_task_with_same_id(self, repo):
        r, conn = repo
        task = _make_task(goal="Write a report")
        returned = r.create(task)
        assert returned.id == task.id

    def test_create_inserts_row_into_db(self, repo):
        r, conn = repo
        task = _make_task(goal="Insert me")
        r.create(task)
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row is not None
        assert row["goal"] == "Insert me"


class TestTaskRepositoryGet:
    def test_get_retrieves_task_by_id(self, repo):
        r, conn = repo
        task = _make_task(goal="Fetch me")
        r.create(task)
        fetched = r.get(task.id)
        assert fetched is not None
        assert fetched.id == task.id
        assert fetched.goal == "Fetch me"

    def test_get_returns_none_for_nonexistent_id(self, repo):
        r, _ = repo
        result = r.get("does-not-exist-0000")
        assert result is None


class TestTaskRepositoryUpdate:
    def test_update_changes_task_status(self, repo):
        r, conn = repo
        task = _make_task(goal="Update me", status=TaskStatus.DRAFT)
        r.create(task)

        task.status = TaskStatus.IN_PROGRESS
        r.update(task)

        row = conn.execute(
            "SELECT status FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row["status"] == "in_progress"


class TestTaskRepositoryDelete:
    def test_delete_removes_task_returns_true(self, repo):
        r, conn = repo
        task = _make_task(goal="Delete me")
        r.create(task)
        result = r.delete(task.id)
        assert result is True
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row is None

    def test_delete_returns_false_for_nonexistent_id(self, repo):
        r, _ = repo
        result = r.delete("ghost-id-9999")
        assert result is False


class TestTaskRepositoryListActive:
    def test_list_active_returns_only_non_terminal_tasks(self, repo):
        r, conn = repo
        active_task = _make_task(goal="Active", status=TaskStatus.IN_PROGRESS)
        r.create(active_task)
        active = r.list_active()
        assert any(t.id == active_task.id for t in active)

    def test_list_active_excludes_terminal_statuses(self, repo):
        r, conn = repo
        terminal_statuses = [
            TaskStatus.PASSED,
            TaskStatus.DONE,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        ]
        terminal_tasks = []
        for status in terminal_statuses:
            t = _make_task(goal=f"Terminal {status.value}", status=status)
            r.create(t)
            terminal_tasks.append(t)

        active = r.list_active()
        active_ids = {t.id for t in active}
        for t in terminal_tasks:
            assert t.id not in active_ids, (
                f"Terminal task with status {t.status} should not appear in list_active()"
            )


class TestTaskRepositoryListByStatus:
    def test_list_by_status_filters_correctly(self, repo):
        r, conn = repo
        t1 = _make_task(goal="Review task 1", status=TaskStatus.REVIEW)
        t2 = _make_task(goal="Review task 2", status=TaskStatus.REVIEW)
        t3 = _make_task(goal="Draft task", status=TaskStatus.DRAFT)
        for t in (t1, t2, t3):
            r.create(t)

        results = r.list_by_status("review")
        result_ids = {t.id for t in results}
        assert t1.id in result_ids
        assert t2.id in result_ids
        assert t3.id not in result_ids


class TestTaskRepositoryUpsert:
    def test_upsert_inserts_new_task(self, repo):
        r, conn = repo
        task = _make_task(goal="Upsert new")
        r.upsert(task)
        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row is not None
        assert row["goal"] == "Upsert new"

    def test_upsert_replaces_existing_task(self, repo):
        r, conn = repo
        task = _make_task(goal="Original goal", status=TaskStatus.DRAFT)
        r.create(task)

        task.status = TaskStatus.PASSED
        task.goal = "Updated goal"
        r.upsert(task)

        row = conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row["status"] == "passed"
        assert row["goal"] == "Updated goal"
        # Only one row should exist
        count = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()[0]
        assert count == 1


class TestTaskRepositoryUpdateStatus:
    def test_update_status_to_in_progress_sets_started_at(self, repo):
        r, conn = repo
        task = _make_task(goal="Start me")
        r.create(task)
        r.update_status(task.id, TaskStatus.IN_PROGRESS)

        row = conn.execute(
            "SELECT status, started_at FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row["status"] == "in_progress"
        assert row["started_at"] is not None

    def test_update_status_to_passed_sets_completed_at(self, repo):
        r, conn = repo
        task = _make_task(goal="Complete me")
        r.create(task)
        r.update_status(task.id, TaskStatus.PASSED)

        row = conn.execute(
            "SELECT status, completed_at FROM tasks WHERE id = ?", (task.id,)
        ).fetchone()
        assert row["status"] == "passed"
        assert row["completed_at"] is not None


# ===========================================================================
# save_review_history()
# ===========================================================================


class TestSaveReviewHistory:
    def test_inserts_row_into_review_history(self, repo):
        r, conn = repo
        task = _make_task(goal="Review history task")
        r.create(task)

        r.save_review_history(
            task_id=task.id,
            step_name="quality_check",
            score=87.5,
            threshold=80.0,
            decision="pass",
            feedback="Good work",
            breakdown={"grammar": 0.9, "clarity": 0.85},
            mode="llm",
        )

        rows = conn.execute(
            "SELECT * FROM review_history WHERE task_id = ?", (task.id,)
        ).fetchall()
        assert len(rows) == 1

    def test_can_retrieve_review_history_rows_for_task_id(self, repo):
        r, conn = repo
        task = _make_task(goal="Multi-review task")
        r.create(task)

        for i in range(3):
            r.save_review_history(
                task_id=task.id,
                step_name=f"step_{i}",
                score=float(70 + i * 5),
                threshold=75.0,
                decision="retry" if i < 2 else "pass",
                feedback=f"Feedback {i}",
                breakdown={"metric": float(i)},
            )

        rows = conn.execute(
            "SELECT * FROM review_history WHERE task_id = ? ORDER BY created_at",
            (task.id,),
        ).fetchall()
        assert len(rows) == 3
        assert rows[0]["step_name"] == "step_0"
        assert rows[2]["step_name"] == "step_2"
        assert rows[2]["decision"] == "pass"


# ===========================================================================
# add_audit_log()
# ===========================================================================


class TestAddAuditLog:
    def test_inserts_row_into_audit_log(self, repo):
        r, conn = repo
        r.add_audit_log(
            actor="ceo_agent",
            action_type="task_approved",
            entity_type="task",
            entity_id="task-abc-123",
            details={"reason": "meets quality standards"},
        )

        rows = conn.execute("SELECT * FROM audit_log").fetchall()
        assert len(rows) == 1

    def test_audit_log_row_contains_correct_actor_and_action_type(self, repo):
        r, conn = repo
        r.add_audit_log(
            actor="escalation_bot",
            action_type="escalation_raised",
            entity_type="task",
            entity_id="task-xyz-999",
            details={"priority": "urgent"},
        )

        row = conn.execute(
            "SELECT * FROM audit_log WHERE actor = 'escalation_bot'"
        ).fetchone()
        assert row is not None
        assert row["actor"] == "escalation_bot"
        assert row["action_type"] == "escalation_raised"


# ===========================================================================
# Task.from_db_row()
# ===========================================================================


class TestTaskFromDbRow:
    def _sample_row(self, **overrides) -> dict:
        base = {
            "id": "row-test-id",
            "campaign_id": "camp-1",
            "account_id": "acc-1",
            "goal": "Test from_db_row",
            "description": "Some description",
            "task_type": "content",
            "status": "in_progress",
            "priority": 3,
            "score": 75.5,
            "kpis_json": json.dumps({"clicks": 1000.0}),
            "kpi_results_json": json.dumps({"clicks": 800.0}),
            "deadline": "2026-04-01T00:00:00Z",
            "sla_deadline": "2026-03-30T00:00:00Z",
            "started_at": "2026-03-26T08:00:00Z",
            "completed_at": None,
            "current_department": "marketing",
            "planning_mode": "template",
            "health_flags_json": json.dumps(["low_engagement"]),
            "retry_count": 2,
            "escalation_count": 1,
            "final_output_text": "Draft output",
            "final_output_json": json.dumps({"draft": True}),
            "specialist_outputs_json": json.dumps({"writer": "done"}),
            "notes": "Some notes",
        }
        base.update(overrides)
        return base

    def test_correctly_parses_all_fields_including_json_columns(self):
        row = self._sample_row()
        task = Task.from_db_row(row)

        assert task.id == "row-test-id"
        assert task.goal == "Test from_db_row"
        assert task.status == TaskStatus.IN_PROGRESS
        assert task.priority == Priority.HIGH
        assert task.score == 75.5
        assert task.kpis == {"clicks": 1000.0}
        assert task.kpi_results == {"clicks": 800.0}
        assert task.health_flags == ["low_engagement"]
        assert task.retry_count == 2
        assert task.escalation_count == 1
        assert task.final_output_json == {"draft": True}
        assert task.specialist_outputs_json == {"writer": "done"}

    def test_handles_none_values_in_optional_fields(self):
        row = self._sample_row(
            completed_at=None,
            started_at=None,
            sla_deadline=None,
            deadline=None,
            campaign_id=None,
            account_id=None,
        )
        task = Task.from_db_row(row)

        assert task.completed_at is None
        assert task.started_at is None
        assert task.sla_deadline is None
        assert task.deadline is None
        assert task.campaign_id == ""
        assert task.account_id == ""

    def test_handles_malformed_json_gracefully(self):
        row = self._sample_row(
            kpis_json="{bad json!!",
            kpi_results_json="not-json",
            health_flags_json="[unclosed",
            final_output_json="???",
            specialist_outputs_json="",
        )
        task = Task.from_db_row(row)

        # All JSON fields should fall back to their defaults
        assert task.kpis == {}
        assert task.kpi_results == {}
        assert task.health_flags == []
        assert task.final_output_json == {}
        assert task.specialist_outputs_json == {}


# ===========================================================================
# Task.to_db_dict()
# ===========================================================================


class TestTaskToDbDict:
    def test_returns_dict_with_all_expected_keys(self):
        task = _make_task(goal="Serialize me")
        d = task.to_db_dict()

        expected_keys = {
            "id", "campaign_id", "account_id", "goal", "description",
            "task_type", "status", "priority", "score",
            "kpis_json", "kpi_results_json",
            "deadline", "sla_deadline", "started_at", "completed_at",
            "current_department", "planning_mode",
            "health_flags_json", "retry_count", "escalation_count",
            "final_output_text", "final_output_json", "specialist_outputs_json",
            "notes",
        }
        assert expected_keys.issubset(set(d.keys()))

    def test_status_is_serialized_as_string_value(self):
        task = _make_task(status=TaskStatus.REVIEW)
        d = task.to_db_dict()
        assert d["status"] == "review"
        assert isinstance(d["status"], str)

    def test_priority_is_serialized_as_integer(self):
        task = _make_task(priority=Priority.URGENT)
        d = task.to_db_dict()
        assert d["priority"] == 4
        assert isinstance(d["priority"], int)

    def test_json_fields_are_serialized_as_strings(self):
        task = _make_task(
            kpis={"impressions": 5000.0},
            health_flags=["sla_at_risk"],
        )
        task.final_output_json = {"result": "success"}
        d = task.to_db_dict()

        assert isinstance(d["kpis_json"], str)
        assert json.loads(d["kpis_json"]) == {"impressions": 5000.0}

        assert isinstance(d["health_flags_json"], str)
        assert json.loads(d["health_flags_json"]) == ["sla_at_risk"]

        assert isinstance(d["final_output_json"], str)
        assert json.loads(d["final_output_json"]) == {"result": "success"}


# ===========================================================================
# SLA Tracker (via Task.is_sla_breached property)
# ===========================================================================


class TestSLATracker:
    def _past_deadline(self) -> str:
        dt = datetime.now(timezone.utc) - timedelta(hours=2)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _future_deadline(self) -> str:
        dt = datetime.now(timezone.utc) + timedelta(hours=48)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_sla_deadline_is_set_correctly(self):
        deadline = self._future_deadline()
        task = _make_task(goal="SLA task", sla_deadline=deadline)
        assert task.sla_deadline == deadline

    def test_is_sla_breached_returns_true_when_past_deadline(self):
        task = _make_task(
            goal="Overdue task",
            sla_deadline=self._past_deadline(),
        )
        assert task.is_sla_breached is True

    def test_is_sla_breached_returns_false_when_deadline_in_future(self):
        task = _make_task(
            goal="On-time task",
            sla_deadline=self._future_deadline(),
        )
        assert task.is_sla_breached is False

    def test_is_sla_breached_returns_false_when_no_deadline_set(self):
        task = _make_task(goal="No deadline task")
        assert task.is_sla_breached is False


# ===========================================================================
# KPI Score (via Task.kpi_score() method)
# ===========================================================================


class TestKPIScore:
    def test_kpi_score_returns_100_when_no_kpis_defined(self):
        task = _make_task(goal="No KPIs")
        assert task.kpi_score() == 100.0

    def test_kpi_score_returns_correct_ratio_when_all_targets_met(self):
        task = _make_task(goal="KPI all met")
        task.kpis = {"clicks": 1000.0, "impressions": 5000.0}
        task.kpi_results = {"clicks": 1000.0, "impressions": 5000.0}
        # Each KPI is at exactly 1.0 achievement -> avg 1.0 -> 100.0
        assert task.kpi_score() == 100.0

    def test_kpi_score_returns_partial_score_when_kpis_partially_met(self):
        task = _make_task(goal="KPI partial")
        task.kpis = {"clicks": 1000.0, "impressions": 2000.0}
        # clicks: 500/1000 = 0.5, impressions: 1000/2000 = 0.5 -> avg 0.5 -> 50.0
        task.kpi_results = {"clicks": 500.0, "impressions": 1000.0}
        score = task.kpi_score()
        assert score == 50.0

    def test_kpi_score_caps_achievement_at_150_percent(self):
        task = _make_task(goal="KPI over-achieved")
        task.kpis = {"clicks": 100.0}
        # 300/100 = 3.0, capped at 1.5 -> 150.0
        task.kpi_results = {"clicks": 300.0}
        score = task.kpi_score()
        assert score == 150.0

    def test_kpi_score_returns_100_when_all_targets_are_zero(self):
        """Avoid division-by-zero; rates list stays empty so returns 100."""
        task = _make_task(goal="Zero target KPIs")
        task.kpis = {"clicks": 0.0}
        task.kpi_results = {"clicks": 500.0}
        assert task.kpi_score() == 100.0

    def test_kpi_score_handles_missing_actual(self):
        """KPI in targets but not in results defaults to 0.0."""
        task = _make_task(goal="Missing actual KPI")
        task.kpis = {"revenue": 10000.0}
        task.kpi_results = {}  # no actuals recorded
        # 0 / 10000 = 0.0 -> score 0.0
        assert task.kpi_score() == 0.0


# ===========================================================================
# Round-trip integration: create → get → verify fields survive serialization
# ===========================================================================


class TestRoundTrip:
    def test_task_fields_survive_db_roundtrip(self, repo):
        r, conn = repo
        task = _make_task(
            goal="Round-trip goal",
            status=TaskStatus.REVIEW,
            priority=Priority.HIGH,
            kpis={"revenue": 5000.0},
            kpi_results={"revenue": 4500.0},
            health_flags=["at_risk"],
            retry_count=1,
            notes="Important note",
        )
        task.final_output_json = {"summary": "draft"}
        r.create(task)

        fetched = r.get(task.id)
        assert fetched is not None
        assert fetched.goal == "Round-trip goal"
        assert fetched.status == TaskStatus.REVIEW
        assert fetched.priority == Priority.HIGH
        assert fetched.kpis == {"revenue": 5000.0}
        assert fetched.kpi_results == {"revenue": 4500.0}
        assert fetched.health_flags == ["at_risk"]
        assert fetched.retry_count == 1
        assert fetched.notes == "Important note"
        assert fetched.final_output_json == {"summary": "draft"}
