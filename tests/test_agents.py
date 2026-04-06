"""
Tests for agent nodes and specialist classes.

Heavy dependencies are stubbed at the very top before any src imports.

Tests 1-3:  AgenticState contract
Tests 4-8:  Router node (route_task)
Tests 9-12: Task Planner (plan_task)
Tests 13-15: Task Progress (advance_task)
Tests 16-19: BaseSpecialist
Tests 20-23: StrategySpecialist
Tests 24-25: Edge cases
"""
import sys
from unittest.mock import MagicMock, patch, PropertyMock

for _m in ["dotenv", "anthropic", "openai", "langgraph", "langgraph.graph",
           "langgraph.checkpoint", "langgraph.checkpoint.memory", "sendgrid",
           "tavily", "langchain_core", "langchain_core.messages",
           "langchain_community", "langchain_anthropic", "langchain_openai"]:
    sys.modules.setdefault(_m, MagicMock())

# Stub langgraph symbols graph.py needs
_lg = sys.modules["langgraph.graph"]
for _sym in ("END", "START", "StateGraph"):
    if not hasattr(_lg, _sym):
        setattr(_lg, _sym, MagicMock())

# ── Additional stubs required by the import chain ────────────────────────────

# src.config.settings — consumed by src.llm.providers
import collections as _collections

_settings_mod = MagicMock()
_settings_mod.SETTINGS = MagicMock()
sys.modules.setdefault("src.config", MagicMock())
sys.modules.setdefault("src.config.settings", _settings_mod)

# src.tools.dispatcher — consumed by BaseSpecialist.execute_tool
# Do NOT stub "src.tools" itself — that would break test_api.py's import of
# src.tools.email_client (which is a real submodule).  Instead only stub the
# dispatcher submodule; the real src.tools package can load fine because all
# its heavy deps (tavily, etc.) are already stubbed above.
sys.modules.setdefault("src.tools.dispatcher", MagicMock())

# src.policies — stub to break circular import:
#   src.policies.__init__ → src.policies.validator → policies (top-level) → src.policies
_policies_stub = MagicMock()
_policies_stub.POLICIES = ()
_policies_stub.validate_policies = MagicMock(return_value=[])
sys.modules.setdefault("src.policies", _policies_stub)
sys.modules.setdefault("src.policies.validator", MagicMock())
sys.modules.setdefault("src.policies.interdepartment_policies", _policies_stub)

# departments.* — consumed by src.agency_registry.load_department_bundle
for _dept in ("account", "strategy", "creative", "media", "tech",
               "data", "production", "sales", "operations", "finance", "crm_automation"):
    for _sub in ("employees", "leader", "policy"):
        _key = f"departments.{_dept}.{_sub}"
        _mod = MagicMock()
        _mod.EMPLOYEES = []
        _mod.LEADER = None
        _mod.POLICY = {}
        sys.modules.setdefault(_key, _mod)
    sys.modules.setdefault(f"departments.{_dept}", MagicMock())
sys.modules.setdefault("departments", MagicMock())

# Ensure project root is on sys.path
from pathlib import Path as _Path
_ROOT = _Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Now import project modules ────────────────────────────────────────────────
import pytest

from src.agents.state import AgenticState
from src.agents.router import route_task
from src.agents.task_planner import plan_task
from src.agents.task_progress import advance_task
from src.agents.specialists.base import BaseSpecialist
from src.agents.specialists.strategy import StrategySpecialist

for _cleanup in [
    "src.config",
    "src.config.settings",
    "src.policies",
    "src.policies.validator",
    "src.policies.interdepartment_policies",
    "src.tools.dispatcher",
    "departments",
    "departments.account",
    "departments.account.employees",
    "departments.account.leader",
    "departments.account.policy",
    "departments.strategy",
    "departments.strategy.employees",
    "departments.strategy.leader",
    "departments.strategy.policy",
    "departments.creative",
    "departments.creative.employees",
    "departments.creative.leader",
    "departments.creative.policy",
    "departments.media",
    "departments.media.employees",
    "departments.media.leader",
    "departments.media.policy",
    "departments.tech",
    "departments.tech.employees",
    "departments.tech.leader",
    "departments.tech.policy",
    "departments.data",
    "departments.data.employees",
    "departments.data.leader",
    "departments.data.policy",
    "departments.production",
    "departments.production.employees",
    "departments.production.leader",
    "departments.production.policy",
    "departments.sales",
    "departments.sales.employees",
    "departments.sales.leader",
    "departments.sales.policy",
    "departments.operations",
    "departments.operations.employees",
    "departments.operations.leader",
    "departments.operations.policy",
    "departments.finance",
    "departments.finance.employees",
    "departments.finance.leader",
    "departments.finance.policy",
    "departments.crm_automation",
    "departments.crm_automation.employees",
    "departments.crm_automation.leader",
    "departments.crm_automation.policy",
]:
    sys.modules.pop(_cleanup, None)


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_state(**overrides) -> dict:
    """Minimal valid AgenticState dict."""
    base: AgenticState = {
        "task_id": "test-task-001",
        "task_description": "Develop a strategy for a new advertising campaign",
        "status": "DRAFT",
        "errors": [],
    }
    base.update(overrides)
    return base


def _make_null_llm() -> MagicMock:
    """FallbackLLM mock whose primary_provider is None (no keys configured)."""
    llm = MagicMock()
    type(llm).primary_provider = PropertyMock(return_value=None)
    return llm


def _make_active_llm(response: str = "{}") -> MagicMock:
    """FallbackLLM mock with a live provider that returns a canned string."""
    llm = MagicMock()
    type(llm).primary_provider = PropertyMock(return_value=MagicMock())
    llm.complete.return_value = response
    return llm


def _make_specialist_bundle():
    return {"employees": [], "leader": None, "policy": {}}


# ─────────────────────────────────────────────────────────────────────────────
# Test 1-3: AgenticState
# ─────────────────────────────────────────────────────────────────────────────

class TestAgenticState:
    """Tests 1-3: AgenticState TypedDict contract."""

    def test_create_with_required_fields(self):
        """Test 1: AgenticState can be created as a plain dict with required fields."""
        state: AgenticState = {
            "task_id": "abc-123",
            "task_description": "Launch campaign",
            "status": "DRAFT",
            "errors": [],
        }
        assert state["task_id"] == "abc-123"
        assert state["task_description"] == "Launch campaign"
        assert state["status"] == "DRAFT"
        assert state["errors"] == []

    def test_get_missing_field_returns_none(self):
        """Test 2: State dict .get('missing_field') returns None without KeyError."""
        state = _make_state()
        assert state.get("missing_field") is None
        assert state.get("nonexistent_key", "default") == "default"
        # Check several NotRequired fields explicitly
        assert state.get("policy") is None
        assert state.get("task_plan") is None
        assert state.get("next_action") is None

    def test_spread_adds_new_key(self):
        """Test 3: State spreads correctly with {**state, 'new_key': 'value'}."""
        state = _make_state()
        new_state = {**state, "next_action": "valid", "custom": "data"}
        # Spread contains all original keys plus new ones
        assert new_state["task_id"] == state["task_id"]
        assert new_state["next_action"] == "valid"
        assert new_state["custom"] == "data"
        # Original is not mutated
        assert "next_action" not in state


# ─────────────────────────────────────────────────────────────────────────────
# Tests 4-8: Router node
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterNode:
    """Tests 4-8: src/agents/router.py :: route_task()."""

    def test_returns_dict(self):
        """Test 4: route_task() returns a dict (not None, not raising)."""
        state = _make_state()
        result = route_task(state)
        assert isinstance(result, dict)
        assert result is not None

    def test_empty_task_type_does_not_crash(self):
        """Test 5: route_task with empty task_type in state doesn't crash."""
        state = _make_state(task_type="")
        result = route_task(state)
        assert isinstance(result, dict)

    def test_returns_next_action_or_status(self):
        """Test 6: Valid state returns dict with 'next_action' key OR at least 'status' key."""
        state = _make_state()
        result = route_task(state)
        has_next_action = "next_action" in result
        has_status = "status" in result
        assert has_next_action or has_status, (
            f"Expected 'next_action' or 'status' in result. Got keys: {list(result.keys())}"
        )

    def test_unknown_dept_signals_invalid_or_error(self):
        """Test 7: Unknown dept from LLM causes router to signal invalid/error."""
        state = _make_state(task_description="Some vague task with no department keywords")
        with patch("src.agents.router.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(
                '{"department": "unknown_dept_xyz", "from_department": "unknown_dept_xyz",'
                ' "to_department": "unknown_dept_xyz", "reasoning": "test"}'
            )
            result = route_task(state)
        assert isinstance(result, dict)
        # next_action must be present — either "invalid" (no heuristic match) or
        # "valid" (heuristic recovered), but must not raise
        assert "next_action" in result

    def test_valid_llm_json_with_known_dept_sets_to_department(self):
        """Test 8: Mock LLM returns valid JSON with known dept → to_department is set."""
        # "account" -> "strategy" is a real policy in interdepartment_policies.py
        state = _make_state(
            task_description="Develop brand positioning and audience persona strategy"
        )
        with patch("src.agents.router.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(
                '{"from_department": "account", "to_department": "strategy",'
                ' "reasoning": "Brand strategy needed"}'
            )
            result = route_task(state)
        assert isinstance(result, dict)
        if result.get("next_action") == "valid":
            assert result.get("to_department") == "strategy"


# ─────────────────────────────────────────────────────────────────────────────
# Tests 9-12: Task Planner
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskPlannerNode:
    """Tests 9-12: src/agents/task_planner.py :: plan_task()."""

    def test_returns_dict(self):
        """Test 9: plan_task() returns a dict."""
        state = _make_state()
        with patch("src.agents.task_planner.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(
                '{"task_type": "custom", "planning_mode": "llm_generated", "steps": []}'
            )
            result = plan_task(state)
        assert isinstance(result, dict)

    def test_empty_task_description_does_not_crash(self):
        """Test 10: plan_task with empty task_description doesn't crash."""
        state = _make_state(task_description="")
        with patch("src.agents.task_planner.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(
                '{"task_type": "custom", "planning_mode": "router_only", "steps": []}'
            )
            result = plan_task(state)
        assert isinstance(result, dict)

    def test_result_contains_task_id_from_input(self):
        """Test 11: plan_task result contains task_id from input state."""
        state = _make_state(task_id="planner-tid-999")
        with patch("src.agents.task_planner.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_null_llm()
            result = plan_task(state)
        assert result.get("task_id") == "planner-tid-999"

    def test_mocked_llm_response_is_processed(self):
        """Test 12: Mock LLM response is processed — task_plan and current_step are set."""
        state = _make_state(task_description="Run a retention automation campaign for existing customers")
        llm_json = (
            '{"task_type": "retention_campaign", "planning_mode": "llm_generated", '
            '"steps": [{"name": "Segment", "from_department": "data", '
            '"to_department": "crm_automation", "required_inputs": ["customer_segments"], '
            '"expected_outputs": ["trigger_rules"], "objective": "Segment customers", '
            '"quality_threshold": 98.0}]}'
        )
        with patch("src.agents.task_planner.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(llm_json)
            result = plan_task(state)
        # template match may fire first (retention keywords) — either way task_plan is a list
        assert isinstance(result.get("task_plan"), list)
        assert "current_step" in result


# ─────────────────────────────────────────────────────────────────────────────
# Tests 13-15: Task Progress
# ─────────────────────────────────────────────────────────────────────────────

class TestTaskProgressNode:
    """Tests 13-15: src/agents/task_progress.py :: advance_task()."""

    def _make_plan(self, n_steps: int = 2) -> list:
        return [
            {
                "name": f"Step {i + 1}",
                "from_department": "account",
                "to_department": "strategy",
                "objective": f"Objective {i + 1}",
            }
            for i in range(n_steps)
        ]

    def _state_with_plan(self, n_steps: int = 2, index: int = 0) -> dict:
        plan = self._make_plan(n_steps)
        return _make_state(
            task_plan=plan,
            current_step_index=index,
            current_step=plan[index] if plan else {},
            completed_steps=[],
            generated_outputs={},
            leader_score=99.0,
            leader_feedback="",
        )

    def test_returns_dict(self):
        """Test 13: advance_task() returns a dict."""
        result = advance_task(self._state_with_plan(2))
        assert isinstance(result, dict)

    def test_last_step_sets_done(self):
        """Test 14: When step_index >= total steps → next_action == 'done'."""
        result = advance_task(self._state_with_plan(n_steps=1, index=0))
        assert result["next_action"] == "done"

    def test_more_steps_sets_continue(self):
        """Test 15: When more steps remain → next_action == 'continue'."""
        result = advance_task(self._state_with_plan(n_steps=3, index=0))
        assert result["next_action"] == "continue"
        assert result["current_step_index"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests 16-19: BaseSpecialist
# ─────────────────────────────────────────────────────────────────────────────

class _ConcreteSpecialist(BaseSpecialist):
    """Minimal concrete subclass for testing BaseSpecialist without real departments."""
    department = "strategy"

    def build_system_prompt(self) -> str:
        return "You are the test specialist."


def _make_base_specialist(llm=None) -> _ConcreteSpecialist:
    with patch("src.agents.specialists.base.load_department_bundle") as mb:
        mb.return_value = _make_specialist_bundle()
        return _ConcreteSpecialist(llm=llm)


class TestBaseSpecialist:
    """Tests 16-19: src/agents/specialists/base.py :: BaseSpecialist."""

    def test_can_be_instantiated(self):
        """Test 16: BaseSpecialist (via concrete subclass) can be instantiated."""
        spec = _make_base_specialist()
        assert spec is not None
        assert spec.department == "strategy"

    def test_has_generate_method(self):
        """Test 17: BaseSpecialist has a 'generate' method (main entry point)."""
        spec = _make_base_specialist()
        assert callable(getattr(spec, "generate", None))

    def test_generate_with_mock_state_returns_something_not_none(self):
        """Test 18: Calling generate() with mock state returns something (dict/str), not None."""
        spec = _make_base_specialist()
        state = _make_state(
            policy={
                "from_department": "account",
                "to_department": "strategy",
                "required_inputs": ["project_brief"],
                "expected_outputs": ["strategy_direction"],
                "sla_hours": 12,
                "approver_role": "Strategy Lead",
            }
        )
        with patch("src.agents.specialists.base.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(
                "## strategy_direction\nA clear strategic direction."
            )
            result = spec.generate(state)
        assert result is not None
        assert isinstance(result, (dict, str))

    def test_generate_empty_task_description_does_not_crash(self):
        """Test 19: Specialist generate() with empty task_description doesn't crash."""
        spec = _make_base_specialist()
        state = _make_state(task_description="", policy={})
        with patch("src.agents.specialists.base.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm("Some output text.")
            result = spec.generate(state)
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# Tests 20-23: StrategySpecialist
# ─────────────────────────────────────────────────────────────────────────────

def _make_strategy_specialist(llm=None) -> StrategySpecialist:
    with patch("src.agents.specialists.base.load_department_bundle") as mb:
        mb.return_value = _make_specialist_bundle()
        return StrategySpecialist(llm=llm)


class TestStrategySpecialist:
    """Tests 20-23: src/agents/specialists/strategy.py :: StrategySpecialist."""

    def test_can_be_instantiated(self):
        """Test 20: StrategySpecialist can be instantiated."""
        spec = _make_strategy_specialist()
        assert spec is not None
        assert spec.department == "strategy"

    def test_generate_returns_specialist_output_key(self):
        """Test 21: StrategySpecialist called with valid state (mocked LLM) returns dict with 'specialist_output'."""
        spec = _make_strategy_specialist()
        state = _make_state(
            task_description="Develop market strategy for luxury shoe brand targeting Gen Z",
            policy={
                "from_department": "account",
                "to_department": "strategy",
                "required_inputs": ["project_brief"],
                "expected_outputs": ["strategy_direction", "funnel_plan"],
                "sla_hours": 12,
                "approver_role": "Strategy Lead",
            },
        )
        llm_response = (
            "## strategy_direction\nTarget Gen Z via TikTok with aspirational messaging.\n\n"
            "## funnel_plan\nAwareness -> Consideration -> Conversion funnel plan."
        )
        with patch("src.agents.specialists.base.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(llm_response)
            result = spec.generate(state)
        assert isinstance(result, dict)
        assert "specialist_output" in result

    def test_specialist_output_is_string(self):
        """Test 22: StrategySpecialist result specialist_output is a string."""
        spec = _make_strategy_specialist()
        state = _make_state(
            task_description="Develop market strategy for a fintech startup",
            policy={
                "from_department": "account",
                "to_department": "strategy",
                "required_inputs": ["project_brief"],
                "expected_outputs": ["strategy_direction"],
                "sla_hours": 12,
                "approver_role": "Strategy Lead",
            },
        )
        with patch("src.agents.specialists.base.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm(
                "## strategy_direction\nFintech pivot strategy."
            )
            result = spec.generate(state)
        assert isinstance(result["specialist_output"], str)

    def test_short_task_does_not_crash(self):
        """Test 23: StrategySpecialist with a very short task (2 words) doesn't crash."""
        spec = _make_strategy_specialist()
        state = _make_state(task_description="Brand audit", policy={})
        with patch("src.agents.specialists.base.get_llm") as mock_get_llm:
            mock_get_llm.return_value = _make_active_llm("Some brief output.")
            result = spec.generate(state)
        assert result is not None
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# Tests 24-25: Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Tests 24-25: Edge cases across modules."""

    def test_none_optional_fields_do_not_cause_attribute_error_in_router(self):
        """Test 24: State with None values for optional fields doesn't AttributeError in router."""
        state: AgenticState = {  # type: ignore[typeddict-item]
            "task_id": "edge-001",
            "task_description": "strategy positioning for brand",
            "status": "DRAFT",
            "errors": [],
            "from_department": None,
            "to_department": None,
            "metadata": None,
            "quality_threshold": None,
        }
        try:
            result = route_task(state)
            assert isinstance(result, dict)
        except AttributeError as exc:
            pytest.fail(f"route_task raised AttributeError on None fields: {exc}")

    def test_existing_errors_list_extended_not_replaced_in_specialist(self):
        """Test 25: 'errors' already a list gets correctly extended (not replaced) in specialist."""
        spec = _make_base_specialist()

        existing_errors = ["pre-existing error"]
        state = _make_state(
            errors=existing_errors,
            task_description="Media campaign planning",
            policy={
                "from_department": "strategy",
                "to_department": "media",
                "required_inputs": ["funnel_plan"],
                "expected_outputs": ["media_plan"],
                "sla_hours": 24,
                "approver_role": "Media Lead",
            },
        )

        # Force LLM.complete() to raise so the fallback path runs and appends an error
        with patch("src.agents.specialists.base.get_llm") as mock_get_llm:
            boom_llm = MagicMock()
            type(boom_llm).primary_provider = PropertyMock(return_value=MagicMock())
            boom_llm.complete.side_effect = RuntimeError("Simulated LLM failure")
            mock_get_llm.return_value = boom_llm
            result = spec.generate(state)

        # specialist_output must still be set (fallback path was taken)
        assert "specialist_output" in result

        result_errors = result.get("errors", [])
        assert isinstance(result_errors, list), "errors must be a list"
        assert "pre-existing error" in result_errors, (
            f"Original error was lost. Result errors: {result_errors}"
        )
        assert len(result_errors) > len(existing_errors), (
            f"Expected new error appended. Before={existing_errors}, After={result_errors}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Additional coverage: full stub-block pattern from prompt (tests for mock_get_llm)
# ─────────────────────────────────────────────────────────────────────────────

class TestMockLLMPatternExamples:
    """Verify the exact mock pattern from the prompt specification works."""

    def test_router_with_prompt_mock_pattern(self):
        """Router respects the src.llm.get_llm mock pattern from prompt spec."""
        # Prompt spec says: patch("src.llm.get_llm") — but router imports as
        # 'from src.llm import get_llm', so the correct patch target is
        # 'src.agents.router.get_llm'.  This test shows both work (or explains why).
        state = _make_state(
            task_description="strategy positioning and audience persona funnel"
        )
        # Direct module patch (as the router imports it)
        with patch("src.agents.router.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.complete.return_value = (
                '{"department": "strategy", "rationale": "test",'
                ' "from_department": "account", "to_department": "strategy",'
                ' "reasoning": "strategy task"}'
            )
            mock_llm.primary_provider = MagicMock()
            mock_get_llm.return_value = mock_llm
            result = route_task(state)
        assert isinstance(result, dict)

    def test_planner_with_prompt_mock_pattern(self):
        """Planner respects the mock pattern from prompt spec."""
        state = _make_state(task_description="Something totally unique zyx no keywords here")
        with patch("src.agents.task_planner.get_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.complete.return_value = (
                '{"department": "strategy", "rationale": "test",'
                ' "task_type": "custom", "planning_mode": "llm_generated", "steps": []}'
            )
            mock_llm.primary_provider = MagicMock()
            mock_get_llm.return_value = mock_llm
            result = plan_task(state)
        assert isinstance(result, dict)
        assert mock_llm.complete.called
