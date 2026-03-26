"""
Integration tests for the scoring system — rubric registry, score engine, retry logic.
Tests run WITHOUT LLM (heuristic/fallback mode) to verify the full scoring pipeline.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest


# ── Rubric Registry ──────────────────────────────────────────────────────────

class TestRubricRegistry:
    def test_all_11_departments_have_rubrics(self):
        from src.scoring.rubric_registry import RubricRegistry

        registry = RubricRegistry()
        depts = registry.list_departments()
        assert len(depts) >= 11
        expected = {
            "strategy", "creative", "media", "data", "account",
            "tech", "sales", "operations", "finance", "crm_automation", "production",
        }
        assert expected.issubset(set(depts))

    def test_each_rubric_has_4_criteria(self):
        from src.scoring.rubric_registry import RubricRegistry

        registry = RubricRegistry()
        for dept in registry.list_departments():
            rubric = registry.get(dept)
            assert len(rubric.criteria) == 4, f"{dept} should have 4 criteria"
            names = {c.name for c in rubric.criteria}
            assert names == {"completeness", "accuracy", "actionability", "professional_quality"}

    def test_weights_sum_to_1(self):
        from src.scoring.rubric_registry import RubricRegistry

        registry = RubricRegistry()
        for dept in registry.list_departments():
            rubric = registry.get(dept)
            total = sum(c.weight for c in rubric.criteria)
            assert abs(total - 1.0) < 0.01, f"{dept} weights sum to {total}, expected 1.0"

    def test_crm_alias_resolves(self):
        """'crm' should resolve to 'crm_automation' rubric."""
        from src.scoring.rubric_registry import get_rubric

        rubric = get_rubric("crm")
        assert rubric.department == "crm_automation"

    def test_crm_automation_direct(self):
        from src.scoring.rubric_registry import get_rubric

        rubric = get_rubric("crm_automation")
        assert rubric.department == "crm_automation"

    def test_unknown_department_falls_back_to_strategy(self):
        from src.scoring.rubric_registry import get_rubric

        rubric = get_rubric("nonexistent_dept")
        assert rubric.department == "strategy"

    def test_quality_threshold_default_98(self):
        from src.scoring.rubric_registry import RubricRegistry

        registry = RubricRegistry()
        for dept in registry.list_departments():
            threshold = registry.quality_threshold(dept)
            assert threshold == 98.0, f"{dept} threshold should be 98.0"

    def test_min_acceptable_default_60(self):
        from src.scoring.rubric_registry import RubricRegistry

        registry = RubricRegistry()
        for dept in registry.list_departments():
            min_score = registry.min_acceptable(dept)
            assert min_score == 60.0, f"{dept} min acceptable should be 60.0"


# ── Score Engine (heuristic mode) ────────────────────────────────────────────

class TestScoreEngineHeuristic:
    """Tests run in heuristic mode (no LLM configured)."""

    def _make_engine(self):
        from src.scoring.score_engine import ScoreEngine
        return ScoreEngine()

    def test_empty_output_scores_low(self):
        engine = self._make_engine()
        result = engine.score("strategy", "", task_type="ad_hoc")
        assert result["scoring_method"] == "heuristic"
        assert result["overall_score"] < 70  # heuristic gives ~56 for empty

    def test_short_output_scores_moderate(self):
        engine = self._make_engine()
        output = "## Summary\nThis is a brief strategy output.\n\n1. Recommendation one\n2. Recommendation two\n"
        result = engine.score("strategy", output, task_type="ad_hoc")
        assert result["scoring_method"] == "heuristic"
        assert 30 < result["overall_score"] < 80

    def test_rich_output_scores_higher(self):
        engine = self._make_engine()
        # Simulate a detailed report
        sections = []
        for i in range(10):
            sections.append(f"## Section {i}\n" + "\n".join(
                f"- Point {j}: Detail about metric {j} with $1,000 budget and 25% growth in Q1 2026"
                for j in range(5)
            ))
        output = "\n\n".join(sections)
        result = engine.score("data", output, task_type="data_report")
        assert result["scoring_method"] == "heuristic"
        assert result["overall_score"] > 60

    def test_result_has_required_keys(self):
        engine = self._make_engine()
        result = engine.score("media", "Some output text", task_type="ad_hoc")
        assert "overall_score" in result
        assert "criteria_scores" in result
        assert "breakdown" in result
        assert "scoring_method" in result
        assert "summary" in result

    def test_breakdown_keys_match_criteria(self):
        engine = self._make_engine()
        result = engine.score("creative", "## Headlines\n1. Bold headline\n2. Creative idea\n")
        breakdown = result["breakdown"]
        assert "completeness" in breakdown
        assert "accuracy" in breakdown
        assert "actionability" in breakdown
        assert "professional_quality" in breakdown

    def test_all_departments_score_without_error(self):
        """Every department should score without raising an exception."""
        engine = self._make_engine()
        departments = [
            "strategy", "creative", "media", "data", "account",
            "tech", "sales", "operations", "finance", "crm_automation", "production",
        ]
        for dept in departments:
            result = engine.score(dept, f"## Report for {dept}\nSome content here.", task_type="ad_hoc")
            assert isinstance(result["overall_score"], float), f"{dept} score should be float"
            assert 0 <= result["overall_score"] <= 100, f"{dept} score out of range"


# ── Retry With Feedback ──────────────────────────────────────────────────────

class TestRetryDecision:
    """Test the RetryWithFeedback decision logic (no DB needed)."""

    def _make_task(self, score=0.0, retry_count=0):
        from src.tasks.models import Task, TaskStatus, Priority
        return Task(
            goal="Test task",
            task_type="ad_hoc",
            status=TaskStatus.IN_PROGRESS,
            priority=Priority.NORMAL,
            score=score,
            retry_count=retry_count,
        )

    def test_high_score_accepts(self):
        from src.scoring.retry_with_feedback import RetryWithFeedback
        engine = RetryWithFeedback()
        task = self._make_task(score=0, retry_count=0)
        decision = engine.decide(task, "strategy", "output", existing_score=99.0)
        assert decision.final_decision == "accept"
        assert not decision.should_retry

    def test_very_low_score_escalates(self):
        from src.scoring.retry_with_feedback import RetryWithFeedback
        engine = RetryWithFeedback()
        task = self._make_task(score=0, retry_count=0)
        decision = engine.decide(task, "strategy", "output", existing_score=30.0)
        assert decision.final_decision == "escalate"

    def test_medium_score_retries(self):
        from src.scoring.retry_with_feedback import RetryWithFeedback
        engine = RetryWithFeedback()
        task = self._make_task(score=0, retry_count=0)
        decision = engine.decide(task, "strategy", "output", existing_score=75.0)
        assert decision.final_decision == "retry"
        assert decision.should_retry

    def test_max_retries_escalates(self):
        from src.scoring.retry_with_feedback import RetryWithFeedback
        engine = RetryWithFeedback()
        task = self._make_task(score=0, retry_count=3)
        decision = engine.decide(task, "strategy", "output", existing_score=75.0)
        assert decision.final_decision == "escalate"

    def test_feedback_contains_rubric_info(self):
        from src.scoring.retry_with_feedback import RetryWithFeedback
        engine = RetryWithFeedback()
        task = self._make_task(score=0, retry_count=0)
        decision = engine.decide(task, "data", "short output", existing_score=70.0)
        assert decision.should_retry
        assert "Attempt" in decision.feedback
        assert "threshold" in decision.feedback.lower() or "Threshold" in decision.feedback


# ── Escalation Trigger ───────────────────────────────────────────────────────

class TestEscalationTrigger:
    def _make_task(self, **kwargs):
        from src.tasks.models import Task, TaskStatus, Priority
        defaults = dict(
            goal="Test task",
            status=TaskStatus.IN_PROGRESS,
            priority=Priority.NORMAL,
            score=0.0,
            retry_count=0,
        )
        defaults.update(kwargs)
        return Task(**defaults)

    def test_low_score_triggers_escalation(self):
        from src.scoring.escalation_trigger import EscalationTrigger
        trigger = EscalationTrigger(task_repo=None)
        task = self._make_task(score=40.0)
        record = trigger.check_task(task)
        assert record is not None
        assert record.escalation_type == "low_quality"

    def test_max_retries_triggers_escalation(self):
        from src.scoring.escalation_trigger import EscalationTrigger
        trigger = EscalationTrigger(task_repo=None)
        task = self._make_task(retry_count=3, score=80.0)
        record = trigger.check_task(task)
        assert record is not None
        assert record.escalation_type == "max_retries"

    def test_normal_task_no_escalation(self):
        from src.scoring.escalation_trigger import EscalationTrigger
        trigger = EscalationTrigger(task_repo=None)
        task = self._make_task(score=85.0, retry_count=1)
        record = trigger.check_task(task)
        assert record is None

    def test_already_escalated_skipped(self):
        from src.scoring.escalation_trigger import EscalationTrigger
        from src.tasks.models import TaskStatus
        trigger = EscalationTrigger(task_repo=None)
        task = self._make_task(score=30.0, status=TaskStatus.ESCALATED)
        record = trigger.check_task(task)
        assert record is None
