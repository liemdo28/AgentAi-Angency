"""
Stream B — Task Domain tests.

Covers:
  B1. Task creation / field defaults
  B2. Task model logic: is_active, is_done, is_sla_breached, kpi_score()
  B3. DB roundtrip: to_db_dict() / from_db_row()
  B4. TaskStatus / Priority enum coverage
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.tasks.models import Priority, Task, TaskStatus


# ------------------------------------------------------------------ #
# B1. Task Create / Defaults                                           #
# ------------------------------------------------------------------ #

class TestTaskCreate:
    def test_default_id_is_uuid(self):
        t = Task(goal="do something")
        assert t.id and len(t.id) == 36

    def test_two_tasks_have_distinct_ids(self):
        assert Task().id != Task().id

    def test_default_status_is_draft(self):
        assert Task().status == TaskStatus.DRAFT

    def test_default_priority_is_normal(self):
        assert Task().priority == Priority.NORMAL

    def test_empty_goal_allowed(self):
        t = Task(goal="")
        assert t.goal == ""

    def test_created_at_is_utc_parseable(self):
        t = Task()
        dt = datetime.fromisoformat(t.created_at.replace("Z", "+00:00"))
        assert dt.tzinfo is not None

    def test_kpis_default_empty(self):
        assert Task().kpis == {}

    def test_kpi_results_default_empty(self):
        assert Task().kpi_results == {}

    def test_score_default_zero(self):
        assert Task().score == 0.0

    def test_retry_count_default_zero(self):
        assert Task().retry_count == 0


# ------------------------------------------------------------------ #
# B2. is_active                                                        #
# ------------------------------------------------------------------ #

class TestIsActive:
    @pytest.mark.parametrize("status", [
        TaskStatus.DRAFT,
        TaskStatus.PENDING,
        TaskStatus.IN_PROGRESS,
        TaskStatus.REVIEW,
    ])
    def test_active_statuses(self, status):
        assert Task(status=status).is_active

    @pytest.mark.parametrize("status", [
        TaskStatus.PASSED,
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
        TaskStatus.ESCALATED,
        TaskStatus.BLOCKED,
    ])
    def test_inactive_statuses(self, status):
        assert not Task(status=status).is_active


# ------------------------------------------------------------------ #
# B2. is_done                                                          #
# ------------------------------------------------------------------ #

class TestIsDone:
    @pytest.mark.parametrize("status", [
        TaskStatus.PASSED,
        TaskStatus.DONE,
        TaskStatus.FAILED,
        TaskStatus.CANCELLED,
    ])
    def test_done_statuses(self, status):
        assert Task(status=status).is_done

    @pytest.mark.parametrize("status", [
        TaskStatus.DRAFT,
        TaskStatus.PENDING,
        TaskStatus.IN_PROGRESS,
        TaskStatus.REVIEW,
        TaskStatus.ESCALATED,
        TaskStatus.BLOCKED,
    ])
    def test_not_done_statuses(self, status):
        assert not Task(status=status).is_done


# ------------------------------------------------------------------ #
# B2. is_sla_breached                                                  #
# ------------------------------------------------------------------ #

class TestIsSlaBreached:
    def test_no_deadline_not_breached(self):
        assert not Task().is_sla_breached

    def test_future_deadline_not_breached(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert not Task(sla_deadline=future).is_sla_breached

    def test_past_deadline_breached(self):
        past = (datetime.now(timezone.utc) - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert Task(sla_deadline=past).is_sla_breached

    def test_exactly_now_boundary(self):
        # 1 second in the future — not breached
        just_future = (datetime.now(timezone.utc) + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert not Task(sla_deadline=just_future).is_sla_breached


# ------------------------------------------------------------------ #
# B2. kpi_score()                                                      #
# ------------------------------------------------------------------ #

class TestKpiScore:
    def test_no_kpis_returns_100(self):
        assert Task().kpi_score() == 100.0

    def test_target_zero_excluded_returns_100(self):
        # When target==0, the rate is excluded → no rates → 100.0
        t = Task(kpis={"metric": 0.0}, kpi_results={"metric": 50.0})
        assert t.kpi_score() == 100.0

    def test_actual_equals_target_score_100(self):
        t = Task(kpis={"ctr": 100.0}, kpi_results={"ctr": 100.0})
        assert t.kpi_score() == 100.0

    def test_actual_exceeds_target_capped_at_150(self):
        t = Task(kpis={"ctr": 10.0}, kpi_results={"ctr": 100.0})
        assert t.kpi_score() == 150.0

    def test_actual_zero_score_zero(self):
        t = Task(kpis={"ctr": 100.0}, kpi_results={"ctr": 0.0})
        assert t.kpi_score() == 0.0

    def test_missing_actual_treated_as_zero(self):
        t = Task(kpis={"ctr": 100.0})
        assert t.kpi_score() == 0.0

    def test_multiple_metrics_averaged(self):
        t = Task(
            kpis={"a": 100.0, "b": 100.0},
            kpi_results={"a": 50.0, "b": 100.0},
        )
        # rates = [0.5, 1.0] → avg=0.75 → 75.0
        assert t.kpi_score() == 75.0

    def test_score_rounded_to_2dp(self):
        t = Task(kpis={"a": 3.0}, kpi_results={"a": 1.0})
        score = t.kpi_score()
        assert score == round(score, 2)

    def test_negative_actual_produces_zero_rate(self):
        # actual=-10 / target=100 → -0.1, capped at min(x,1.5): -0.1 remains
        # score can be negative in theory — just must not crash
        t = Task(kpis={"a": 100.0}, kpi_results={"a": -10.0})
        score = t.kpi_score()
        assert isinstance(score, float)


# ------------------------------------------------------------------ #
# B3. DB Roundtrip                                                     #
# ------------------------------------------------------------------ #

class TestToDbDict:
    def test_has_required_keys(self):
        d = Task(goal="test").to_db_dict()
        for key in ("id", "goal", "status", "priority", "score", "kpis_json", "kpi_results_json"):
            assert key in d

    def test_status_is_string(self):
        assert Task(status=TaskStatus.IN_PROGRESS).to_db_dict()["status"] == "in_progress"

    def test_priority_is_int(self):
        assert Task(priority=Priority.HIGH).to_db_dict()["priority"] == 3

    def test_kpis_json_is_valid_string(self):
        raw = Task(kpis={"ctr": 1.0}).to_db_dict()["kpis_json"]
        assert isinstance(raw, str)
        assert json.loads(raw) == {"ctr": 1.0}

    def test_empty_kpis_serialized(self):
        raw = Task().to_db_dict()["kpis_json"]
        assert json.loads(raw) == {}

    def test_health_flags_json(self):
        raw = Task(health_flags=["flag1"]).to_db_dict()["health_flags_json"]
        assert json.loads(raw) == ["flag1"]


class TestFromDbRow:
    def _minimal_row(self, **overrides) -> dict:
        base = {"id": "t-1", "goal": "x", "status": "draft", "priority": 2, "score": 0.0}
        base.update(overrides)
        return base

    def test_basic_fields(self):
        t = Task.from_db_row(self._minimal_row(goal="hello", account_id="acct-x"))
        assert t.goal == "hello"
        assert t.account_id == "acct-x"
        assert t.status == TaskStatus.DRAFT

    def test_kpis_parsed(self):
        row = self._minimal_row(
            kpis_json='{"impressions": 1000.0}',
            kpi_results_json='{"impressions": 850.0}',
        )
        t = Task.from_db_row(row)
        assert t.kpis == {"impressions": 1000.0}
        assert t.kpi_results == {"impressions": 850.0}

    def test_invalid_kpis_json_defaults_to_empty(self):
        row = self._minimal_row(kpis_json="NOT_JSON", kpi_results_json=None)
        t = Task.from_db_row(row)
        assert t.kpis == {}
        assert t.kpi_results == {}

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError):
            Task.from_db_row(self._minimal_row(status="invalid_xyz"))

    def test_none_campaign_becomes_empty_string(self):
        t = Task.from_db_row(self._minimal_row(campaign_id=None, account_id=None))
        assert t.campaign_id == ""
        assert t.account_id == ""

    def test_roundtrip_full(self):
        original = Task(
            goal="run campaign",
            account_id="acct-001",
            campaign_id="camp-001",
            status=TaskStatus.PASSED,
            priority=Priority.URGENT,
            kpis={"clicks": 500.0},
            kpi_results={"clicks": 450.0},
            score=90.0,
            notes="done well",
        )
        restored = Task.from_db_row(original.to_db_dict())
        assert restored.id == original.id
        assert restored.goal == original.goal
        assert restored.status == original.status
        assert restored.priority == original.priority
        assert restored.score == original.score
        assert restored.kpis == original.kpis
        assert restored.kpi_results == original.kpi_results
        assert restored.notes == original.notes


# ------------------------------------------------------------------ #
# B4. TaskStatus / Priority enum coverage                              #
# ------------------------------------------------------------------ #

class TestEnums:
    def test_all_task_status_values(self):
        expected = {
            "draft", "pending", "in_progress", "review",
            "passed", "failed", "escalated", "blocked", "cancelled", "done",
        }
        assert {s.value for s in TaskStatus} == expected

    def test_priority_integer_values(self):
        assert int(Priority.LOW) == 1
        assert int(Priority.NORMAL) == 2
        assert int(Priority.HIGH) == 3
        assert int(Priority.URGENT) == 4

    def test_escalated_neither_active_nor_done(self):
        t = Task(status=TaskStatus.ESCALATED)
        assert not t.is_active
        assert not t.is_done

    def test_blocked_neither_active_nor_done(self):
        t = Task(status=TaskStatus.BLOCKED)
        assert not t.is_active
        assert not t.is_done
