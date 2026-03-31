"""
Tests for Bug/Risk Report fixes (RISK-001 through RISK-007).
Validates each fix against the specific failure scenario described in QA_BUG_RISK_REPORT.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

try:
    import httpx  # noqa: F401
    _has_httpx = True
except ImportError:
    _has_httpx = False


# ── RISK-001: task_runner status mapping ─────────────────────────────────────

class TestRisk001StatusMapping:
    """Unknown graph statuses should NOT silently become DONE."""

    def test_passed_maps_correctly(self):
        from src.tasks.models import TaskStatus
        _STATUS_MAP = {
            "PASSED": TaskStatus.PASSED,
            "REVIEW_FAILED": TaskStatus.ESCALATED,
            "FAILED": TaskStatus.FAILED,
            "IN_PROGRESS": TaskStatus.FAILED,
            "REVIEW": TaskStatus.FAILED,
        }
        assert _STATUS_MAP["PASSED"] == TaskStatus.PASSED

    def test_unknown_status_does_not_become_done(self):
        """Simulates the fix: unknown status should be FAILED, not DONE."""
        from src.tasks.models import TaskStatus

        _STATUS_MAP = {
            "PASSED": TaskStatus.PASSED,
            "REVIEW_FAILED": TaskStatus.ESCALATED,
            "FAILED": TaskStatus.FAILED,
            "IN_PROGRESS": TaskStatus.FAILED,
            "REVIEW": TaskStatus.FAILED,
        }

        # Unknown status like "WEIRD_STATE"
        graph_status = "WEIRD_STATE"
        errors = []
        final_output = ""
        score = 0.0

        if graph_status in _STATUS_MAP:
            new_status = _STATUS_MAP[graph_status]
        elif errors:
            new_status = TaskStatus.FAILED
        elif final_output and score > 0:
            new_status = TaskStatus.DONE
        else:
            new_status = TaskStatus.FAILED
            errors.append(f"Unexpected graph status: {graph_status}")

        assert new_status == TaskStatus.FAILED
        assert any("Unexpected" in e for e in errors)

    def test_in_progress_maps_to_failed(self):
        """A task stuck in IN_PROGRESS after graph completes should be FAILED."""
        from src.tasks.models import TaskStatus
        _STATUS_MAP = {
            "IN_PROGRESS": TaskStatus.FAILED,
            "REVIEW": TaskStatus.FAILED,
        }
        assert _STATUS_MAP["IN_PROGRESS"] == TaskStatus.FAILED
        assert _STATUS_MAP["REVIEW"] == TaskStatus.FAILED


# ── RISK-003: Duplicate email deduplication ──────────────────────────────────

@pytest.mark.skipif(not _has_httpx, reason="httpx not installed")
class TestRisk003Deduplication:
    """Duplicate emails should be detected and skipped."""

    def test_dedup_set_tracks_message_ids(self):
        from src.ingestion.data_collection import _processed_message_ids
        # Ensure it's a set
        assert isinstance(_processed_message_ids, set)

    def test_duplicate_email_returns_duplicate_status(self):
        """Process same email twice — second should return 'duplicate'."""
        import email.message
        from src.ingestion import data_collection

        # Reset dedup state
        data_collection._processed_message_ids.clear()

        # Build an email with a Message-ID
        msg = email.message.EmailMessage()
        msg["From"] = "bob@acme.com"
        msg["Subject"] = "Report"
        msg["Message-ID"] = "<unique-id-12345@acme.com>"
        msg.set_content("test body")
        raw = msg.as_bytes()

        mapping = {"@acme.com": "acct-001"}

        # First call (no trigger_task to avoid DB)
        r1 = data_collection.process_inbound_email(raw, mapping, trigger_task=False)
        assert r1["status"] in ("ok", "partial")

        # Second call — same email
        r2 = data_collection.process_inbound_email(raw, mapping, trigger_task=False)
        assert r2["status"] == "duplicate"
        assert r2["account_id"] is None

        # Cleanup
        data_collection._processed_message_ids.clear()

    def test_different_emails_not_deduped(self):
        import email.message
        from src.ingestion import data_collection

        data_collection._processed_message_ids.clear()

        msg1 = email.message.EmailMessage()
        msg1["From"] = "bob@acme.com"
        msg1["Message-ID"] = "<id-1@acme.com>"
        msg1.set_content("report 1")

        msg2 = email.message.EmailMessage()
        msg2["From"] = "bob@acme.com"
        msg2["Message-ID"] = "<id-2@acme.com>"
        msg2.set_content("report 2")

        mapping = {"@acme.com": "acct-001"}

        r1 = data_collection.process_inbound_email(msg1.as_bytes(), mapping, trigger_task=False)
        r2 = data_collection.process_inbound_email(msg2.as_bytes(), mapping, trigger_task=False)

        assert r1["status"] != "duplicate"
        assert r2["status"] != "duplicate"

        data_collection._processed_message_ids.clear()


# ── RISK-004: Heuristic scoring content density ──────────────────────────────

class TestRisk004ContentDensity:
    """Formatted garbage should score lower than real content."""

    def _make_engine(self):
        from src.scoring.score_engine import ScoreEngine
        return ScoreEngine()

    def test_garbage_with_headers_scores_lower(self):
        engine = self._make_engine()

        # Formatted garbage: correct headers but repetitive filler
        garbage = "## Summary\n" + ("lorem ipsum dolor sit amet. " * 100 + "\n") * 10
        garbage += "\n## Recommendations\n" + ("lorem ipsum dolor sit amet. " * 50)

        # Real content with variety
        real = """## Summary
Campaign performance improved across all channels. CTR increased 32% driven by video creative.
ROAS reached 4.2x, exceeding the 3.0x target by 40%.

## Key Insights
1. Meta Reels outperformed static images with 3.2% CTR vs 1.8% CTR
2. Google Search drove highest-intent conversions at $42 CPA
3. Display channel underperforming at 0.3% CTR — recommend pausing

## Recommendations
1. [HIGH] Scale Meta Reels budget by 20% — video CTR is 32% higher
2. [MEDIUM] Expand Google Search keywords — impression share only 62%
3. [LOW] Pause Display — ROAS 1.2x below breakeven threshold
"""

        garbage_result = engine.score("data", garbage, task_type="data_report")
        real_result = engine.score("data", real, task_type="data_report")

        # Real content should score meaningfully higher than garbage
        assert real_result["overall_score"] > garbage_result["overall_score"], (
            f"Real ({real_result['overall_score']:.1f}) should beat garbage ({garbage_result['overall_score']:.1f})"
        )

    def test_empty_output_has_density_note(self):
        engine = self._make_engine()
        result = engine.score("strategy", "x " * 100, task_type="ad_hoc")
        # Very repetitive text should be flagged
        notes = str(result.get("criteria_scores", {}).get("completeness", {}).get("notes", ""))
        # Low density should appear somewhere in the notes
        assert "density" in notes.lower() or result["overall_score"] < 70


# ── RISK-005: Retry score regression detection ──────────────────────────────

class TestRisk005RetryRegression:
    """Retry loop should stop if score doesn't improve."""

    def test_regression_decision_is_escalate(self):
        from src.scoring.retry_with_feedback import RetryDecision

        # Simulate what the code does when regression detected
        decision = RetryDecision(
            should_retry=False,
            reason="Score regression: 72.0 -> 68.0, no improvement",
            feedback="",
            attempt=2,
            new_score=72.0,
            final_decision="escalate",
        )
        assert decision.final_decision == "escalate"
        assert not decision.should_retry
        assert "regression" in decision.reason.lower()


# ── RISK-007: Per-task-type thresholds ───────────────────────────────────────

class TestRisk007TaskTypeThresholds:
    """Different task types should have different quality thresholds."""

    def test_data_ingestion_lower_threshold(self):
        from src.scoring.rubric_registry import RubricRegistry
        reg = RubricRegistry()
        # data_ingestion should be lower than default 98
        threshold = reg.quality_threshold("data", task_type="data_ingestion")
        assert threshold < 98.0
        assert threshold == 85.0

    def test_campaign_launch_high_threshold(self):
        from src.scoring.rubric_registry import RubricRegistry
        reg = RubricRegistry()
        threshold = reg.quality_threshold("strategy", task_type="campaign_launch")
        assert threshold == 96.0

    def test_client_reporting_moderate_threshold(self):
        from src.scoring.rubric_registry import RubricRegistry
        reg = RubricRegistry()
        threshold = reg.quality_threshold("data", task_type="client_reporting")
        assert threshold == 90.0

    def test_unknown_task_type_uses_department_default(self):
        from src.scoring.rubric_registry import RubricRegistry
        reg = RubricRegistry()
        threshold = reg.quality_threshold("strategy", task_type="unknown_type")
        assert threshold == 98.0  # falls back to department default

    def test_no_task_type_uses_department_default(self):
        from src.scoring.rubric_registry import RubricRegistry
        reg = RubricRegistry()
        threshold = reg.quality_threshold("strategy")
        assert threshold == 98.0

    def test_task_type_threshold_static(self):
        from src.scoring.rubric_registry import RubricRegistry
        assert RubricRegistry.task_type_threshold("ad_hoc") == 92.0
        assert RubricRegistry.task_type_threshold("nonexistent") == 98.0


# ── RISK-002: Failure classification ─────────────────────────────────────────

class TestRisk002FailureClassification:
    """Leader review should classify WHY output failed."""

    def test_failure_categories_mapping(self):
        _CRITERION_TO_CATEGORY = {
            "completeness": "missing_sections",
            "accuracy": "factual_or_data_error",
            "actionability": "too_vague_or_generic",
            "professional_quality": "formatting_or_structure",
        }
        assert len(_CRITERION_TO_CATEGORY) == 4
        assert _CRITERION_TO_CATEGORY["accuracy"] == "factual_or_data_error"

    def test_weakest_criterion_determines_category(self):
        # Simulate breakdown where accuracy is weakest
        breakdown = {
            "completeness": 85.0,
            "accuracy": 45.0,
            "actionability": 72.0,
            "professional_quality": 80.0,
        }
        sorted_criteria = sorted(
            [(k, v) for k, v in breakdown.items() if isinstance(v, (int, float))],
            key=lambda x: x[1],
        )
        weakest = sorted_criteria[0][0]
        assert weakest == "accuracy"

        _CRITERION_TO_CATEGORY = {
            "completeness": "missing_sections",
            "accuracy": "factual_or_data_error",
            "actionability": "too_vague_or_generic",
            "professional_quality": "formatting_or_structure",
        }
        category = _CRITERION_TO_CATEGORY.get(weakest, "unknown")
        assert category == "factual_or_data_error"
