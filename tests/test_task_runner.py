"""
Stream C — AI Pipeline tests.

Covers:
  C1. Graph contract: initial state building, missing/bad fields handled
  C2. Score & Retry: status mapping, score extraction, retry_count
  C3. Persistence: task marked IN_PROGRESS before graph, updated after, exception path
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

# ── Stub all heavy/optional deps before src.* imports ──────────────
# These packages may not be installed in the test environment.
# Stub them so unit tests run without the full AI stack.
_STUBS = [
    "langgraph", "langgraph.graph", "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "dotenv",
    "anthropic", "openai", "httpx",
    "sendgrid",
]
for _mod in _STUBS:
    sys.modules.setdefault(_mod, MagicMock())

# Provide the specific symbols graph.py needs
_lg = sys.modules["langgraph.graph"]
for _sym in ("END", "START", "StateGraph"):
    if not hasattr(_lg, _sym):
        setattr(_lg, _sym, MagicMock())

import pytest  # noqa: F401 — used by subclasses

from src.tasks.models import Task, TaskStatus


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def make_task(**kwargs) -> Task:
    defaults = dict(goal="Run a test campaign", account_id="acct-1", task_type="campaign")
    defaults.update(kwargs)
    return Task(**defaults)


def make_graph_result(**overrides) -> dict:
    """Minimal valid graph result state."""
    base = {
        "status": "PASSED",
        "leader_score": 85.0,
        "specialist_output": "Output text",
        "generated_outputs": {"key": "value"},
        "review_history": [{"step": "leader_review", "score": 85.0}],
        "errors": [],
        "retry_count": 0,
    }
    base.update(overrides)
    return base


def run_with_mock_graph(task: Task, graph_result: dict) -> dict:
    """Run run_task_sync with a fully mocked graph + DB layer."""
    from src.task_runner import run_task_sync

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = graph_result

    with (
        patch("src.task_runner.get_graph", return_value=mock_graph),
        patch("src.task_runner.init_db"),
        patch("src.task_runner.TaskRepository") as MockRepo,
    ):
        instance = MockRepo.return_value
        instance.upsert.return_value = task
        instance.update.return_value = task
        return run_task_sync(task)


# ------------------------------------------------------------------ #
# C2. Status Mapping                                                   #
# ------------------------------------------------------------------ #

class TestStatusMapping:
    def test_passed_maps_to_passed(self):
        result = run_with_mock_graph(make_task(), make_graph_result(status="PASSED"))
        assert result["status"] == TaskStatus.PASSED.value

    def test_review_failed_maps_to_escalated(self):
        result = run_with_mock_graph(
            make_task(), make_graph_result(status="REVIEW_FAILED", errors=[])
        )
        assert result["status"] == TaskStatus.ESCALATED.value

    def test_errors_present_maps_to_failed(self):
        result = run_with_mock_graph(
            make_task(),
            make_graph_result(status="DONE", errors=["Something broke"]),
        )
        assert result["status"] == TaskStatus.FAILED.value

    def test_unknown_status_no_errors_maps_to_failed(self):
        result = run_with_mock_graph(
            make_task(), make_graph_result(status="UNKNOWN_XYZ", errors=[])
        )
        assert result["status"] == TaskStatus.FAILED.value

    def test_missing_status_field_defaults_to_failed_or_done(self):
        graph_result = make_graph_result()
        del graph_result["status"]
        # No "status" key → result_state.get("status","FAILED") → new_status = FAILED or DONE
        result = run_with_mock_graph(make_task(), graph_result)
        assert result["status"] in (TaskStatus.FAILED.value, TaskStatus.DONE.value)


# ------------------------------------------------------------------ #
# C1. Score & Output Extraction                                        #
# ------------------------------------------------------------------ #

class TestScoreExtraction:
    def test_score_extracted_correctly(self):
        result = run_with_mock_graph(make_task(), make_graph_result(leader_score=72.5))
        assert result["score"] == 72.5

    def test_missing_leader_score_defaults_to_zero(self):
        graph_result = make_graph_result()
        del graph_result["leader_score"]
        result = run_with_mock_graph(make_task(), graph_result)
        assert result["score"] == 0.0

    def test_review_history_returned(self):
        history = [{"step": "s1", "score": 90}]
        result = run_with_mock_graph(make_task(), make_graph_result(review_history=history))
        assert result["review_history"] == history

    def test_empty_review_history_returned(self):
        result = run_with_mock_graph(make_task(), make_graph_result(review_history=[]))
        assert result["review_history"] == []

    def test_missing_review_history_defaults_to_empty(self):
        graph_result = make_graph_result()
        del graph_result["review_history"]
        result = run_with_mock_graph(make_task(), graph_result)
        assert result["review_history"] == []

    def test_retry_count_extracted(self):
        result = run_with_mock_graph(make_task(), make_graph_result(retry_count=2))
        assert result["retry_count"] == 2

    def test_result_contains_task_id(self):
        task = make_task()
        result = run_with_mock_graph(task, make_graph_result())
        assert result["task_id"] == task.id

    def test_generated_outputs_non_dict_coerced_to_empty(self):
        result = run_with_mock_graph(
            make_task(), make_graph_result(generated_outputs="bad_string")
        )
        assert result["final_output_json"] == {}

    def test_missing_generated_outputs_defaults_to_empty(self):
        graph_result = make_graph_result()
        del graph_result["generated_outputs"]
        result = run_with_mock_graph(make_task(), graph_result)
        assert result["final_output_json"] == {}

    def test_negative_retry_count_in_graph(self):
        # Should not crash; just stored as-is (int cast)
        result = run_with_mock_graph(make_task(), make_graph_result(retry_count=-1))
        assert isinstance(result["retry_count"], int)


# ------------------------------------------------------------------ #
# C3. Persistence                                                      #
# ------------------------------------------------------------------ #

class TestPersistence:
    def test_task_marked_in_progress_before_graph_invoke(self):
        """repo.upsert must be called with IN_PROGRESS BEFORE graph.invoke."""
        from src.task_runner import run_task_sync

        task = make_task()
        call_order = []
        mock_graph = MagicMock()

        def record_invoke(_state):
            call_order.append("invoke")
            return make_graph_result()

        mock_graph.invoke.side_effect = record_invoke

        with (
            patch("src.task_runner.get_graph", return_value=mock_graph),
            patch("src.task_runner.init_db"),
            patch("src.task_runner.TaskRepository") as MockRepo,
        ):
            instance = MockRepo.return_value

            def record_upsert(t):
                call_order.append(("upsert", t.status))
                return t

            instance.upsert.side_effect = record_upsert
            instance.update.return_value = task
            run_task_sync(task)

        upsert_idx = next(i for i, x in enumerate(call_order) if isinstance(x, tuple) and x[0] == "upsert")
        invoke_idx = call_order.index("invoke")
        assert upsert_idx < invoke_idx
        assert call_order[upsert_idx][1] == TaskStatus.IN_PROGRESS

    def test_repo_update_called_after_graph_completes(self):
        from src.task_runner import run_task_sync

        task = make_task()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = make_graph_result(status="PASSED")

        with (
            patch("src.task_runner.get_graph", return_value=mock_graph),
            patch("src.task_runner.init_db"),
            patch("src.task_runner.TaskRepository") as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert.return_value = task
            instance.update.return_value = task
            run_task_sync(task)

        assert instance.update.called

    def test_exception_in_graph_returns_failed(self):
        from src.task_runner import run_task_sync

        task = make_task()
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("Graph exploded")

        with (
            patch("src.task_runner.get_graph", return_value=mock_graph),
            patch("src.task_runner.init_db"),
            patch("src.task_runner.TaskRepository") as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert.return_value = task
            instance.update.return_value = task
            result = run_task_sync(task)

        assert result["status"] == TaskStatus.FAILED.value
        assert "Graph exploded" in result["errors"][0]

    def test_exception_result_has_zero_score(self):
        from src.task_runner import run_task_sync

        task = make_task()
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = ValueError("bad input")

        with (
            patch("src.task_runner.get_graph", return_value=mock_graph),
            patch("src.task_runner.init_db"),
            patch("src.task_runner.TaskRepository") as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert.return_value = task
            instance.update.return_value = task
            result = run_task_sync(task)

        assert result["score"] == 0.0

    def test_db_update_raises_returns_failed(self):
        """If repo.update raises after graph passes, exception handler takes over."""
        from src.task_runner import run_task_sync

        task = make_task()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = make_graph_result(status="PASSED")

        with (
            patch("src.task_runner.get_graph", return_value=mock_graph),
            patch("src.task_runner.init_db"),
            patch("src.task_runner.TaskRepository") as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert.return_value = task
            instance.update.side_effect = Exception("DB down")
            result = run_task_sync(task)

        assert result["status"] == TaskStatus.FAILED.value

    def test_exception_path_still_calls_update(self):
        """Even on failure, task.notes is set and repo.update is attempted."""
        from src.task_runner import run_task_sync

        task = make_task()
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("crash")

        with (
            patch("src.task_runner.get_graph", return_value=mock_graph),
            patch("src.task_runner.init_db"),
            patch("src.task_runner.TaskRepository") as MockRepo,
        ):
            instance = MockRepo.return_value
            instance.upsert.return_value = task
            instance.update.return_value = task
            run_task_sync(task)

        # update should have been called in the except block
        assert instance.update.called


# ------------------------------------------------------------------ #
# C1. _build_initial_state                                             #
# ------------------------------------------------------------------ #

class TestBuildInitialState:
    def test_has_task_id(self):
        from src.task_runner import _build_initial_state
        task = make_task()
        state = _build_initial_state(task)
        assert state["task_id"] == task.id

    def test_status_is_in_progress_string(self):
        from src.task_runner import _build_initial_state
        state = _build_initial_state(make_task())
        assert state["status"] == "IN_PROGRESS"

    def test_description_merges_goal_and_description(self):
        from src.task_runner import _build_initial_state
        task = make_task(goal="goal text", description="desc text")
        state = _build_initial_state(task)
        assert "goal text" in state["task_description"]
        assert "desc text" in state["task_description"]

    def test_goal_only_description(self):
        from src.task_runner import _build_initial_state
        task = make_task(goal="only goal", description="")
        state = _build_initial_state(task)
        assert state["task_description"] == "only goal"

    def test_context_merged_into_metadata(self):
        from src.task_runner import _build_initial_state
        task = make_task()
        state = _build_initial_state(task, context={"sector": "retail"})
        assert state["metadata"]["sector"] == "retail"

    def test_errors_empty_list(self):
        from src.task_runner import _build_initial_state
        state = _build_initial_state(make_task())
        assert state["errors"] == []

    def test_kpis_in_metadata(self):
        from src.task_runner import _build_initial_state
        task = make_task(kpis={"ctr": 50.0})
        state = _build_initial_state(task)
        assert state["metadata"]["kpis"] == {"ctr": 50.0}

    def test_retry_count_from_task(self):
        from src.task_runner import _build_initial_state
        task = make_task(retry_count=3)
        state = _build_initial_state(task)
        assert state["retry_count"] == 3
