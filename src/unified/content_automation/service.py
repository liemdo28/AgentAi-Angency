"""
ContentAutomationService — orchestrates the full content pipeline.

Pipeline flow per post:
  ContentPlanner.plan_day()
    → ContentGenerator.generate(plan)
    → ContentValidator.validate(draft)
    → ApprovalService.create_post_from_plan(plan, draft, passed)

Publish flow (triggered by human approval via API):
  ApprovalService.approve(post_id, reviewer)
  → ApprovalService.begin_publish(post_id)
  → ContentPublisher.publish(post, version)
  → PostRepository.update_post_status(post_id, 'published' | 'publish_failed')

Usage:
    from src.unified.content_automation.service import ContentAutomationService

    svc = ContentAutomationService(brand="raw")
    result = svc.run_daily_job()
    # result = {
    #   "date": "2026-04-17",
    #   "brand": "raw",
    #   "posts": [
    #     {"slot": 0, "post_id": "...", "status": "pending_approval", "agent_score": 82.5, ...},
    #     ...
    #   ],
    #   "errors": [],
    # }
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("content_automation.service")


class ContentAutomationService:
    """
    Top-level orchestrator for the content automation pipeline.

    One instance per brand. Thread-safe for concurrent HTTP requests
    (each call creates fresh sub-service instances backed by SQLite WAL).
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand

    # ── Public API ────────────────────────────────────────────────────────────

    def run_daily_job(self, date_iso: str | None = None) -> dict:
        """
        Run the full daily content pipeline: plan → generate → validate → save.

        Creates exactly 3 posts (one per slot) and saves them to the DB.
        Posts with validation_passed=True → status 'pending_approval'.
        Posts with validation_passed=False → status 'validation_failed'.

        Args:
            date_iso: Optional ISO date string (YYYY-MM-DD). Defaults to today UTC.

        Returns:
            {
                "date": str,
                "brand": str,
                "posts": list[dict],   # one entry per slot
                "errors": list[dict],  # any slot-level errors (slot still counted)
                "summary": dict,       # pending / failed / total counts
            }
        """
        from .planner import ContentPlanner
        from .generator import ContentGenerator
        from .validator import ContentValidator
        from .approval_service import ApprovalService

        date_str = date_iso or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        logger.info("[%s] ContentAutomationService.run_daily_job brand=%s", date_str, self.brand)

        planner   = ContentPlanner(brand=self.brand)
        generator = ContentGenerator(brand=self.brand)
        validator = ContentValidator(brand=self.brand)
        approval  = ApprovalService(brand=self.brand)

        # Step 1: Plan 3 slots
        try:
            plans = planner.plan_day(date_iso=date_str)
        except Exception as exc:
            logger.error("Planner failed for %s on %s: %s", self.brand, date_str, exc)
            return {
                "date": date_str,
                "brand": self.brand,
                "posts": [],
                "errors": [{"phase": "planner", "error": str(exc)}],
                "summary": {"pending": 0, "failed": 0, "total": 0},
            }

        posts: list[dict] = []
        errors: list[dict] = []

        # Step 2–4: Generate + Validate + Save each slot
        for plan in plans:
            slot_result: dict[str, Any] = {
                "slot": plan.slot,
                "post_type": plan.post_type.value,
                "topic": plan.topic,
                "title": plan.title,
                "slug": plan.slug,
            }
            try:
                # Generate
                draft = generator.generate(plan)

                # Validate
                val_result = validator.validate(draft)
                draft.validation_result = val_result
                validation_passed = val_result.passed

                # Save to DB
                saved = approval.create_post_from_plan(plan, draft, validation_passed)

                slot_result.update({
                    "post_id":          saved["post_id"],
                    "version_id":       saved["version_id"],
                    "status":           saved["status"],
                    "agent_score":      saved["agent_score"],
                    "validation_passed": validation_passed,
                    "validation_notes": val_result.editor_notes,
                    "hard_valid":       val_result.hard_valid,
                    "quality_score":    val_result.quality_score,
                    "risk_level":       (val_result.risk_level.value if val_result.risk_level else "low") if hasattr(val_result, "risk_level") and val_result.risk_level else "low",
                })
                logger.info(
                    "[%s] Slot %d saved: post_id=%s status=%s score=%.1f",
                    date_str, plan.slot, saved["post_id"], saved["status"], saved["agent_score"],
                )

            except Exception as exc:
                logger.exception(
                    "[%s] Slot %d failed (type=%s topic=%r): %s",
                    date_str, plan.slot, plan.post_type.value, plan.topic, exc,
                )
                slot_result["status"] = "error"
                slot_result["error"] = str(exc)
                errors.append({
                    "phase": f"slot_{plan.slot}",
                    "post_type": plan.post_type.value,
                    "topic": plan.topic,
                    "error": str(exc),
                })

            posts.append(slot_result)

        pending = sum(1 for p in posts if p.get("status") == "pending_approval")
        failed  = sum(1 for p in posts if p.get("status") in ("validation_failed", "error"))

        return {
            "date": date_str,
            "brand": self.brand,
            "posts": posts,
            "errors": errors,
            "summary": {
                "pending": pending,
                "failed":  failed,
                "total":   len(posts),
            },
        }

    def publish_post(self, post_id: str, reviewer: str = "AgentAI Agency") -> dict:
        """
        Publish an already-approved post to RawWebsite via git.

        Flow:
          approved → publishing → published | publish_failed

        Args:
            post_id: post UUID
            reviewer: name/ID of the actor triggering publish

        Returns:
            PublishResult dict with success flag, url, and details.
        """
        from .approval_service import ApprovalService
        from src.unified.content.publisher import ContentPublisher as MarkdownPublisher
        from db.post_repository import PostRepository

        approval  = ApprovalService(brand=self.brand)
        publisher = MarkdownPublisher()
        repo      = PostRepository()

        # Transition to publishing
        approval.begin_publish(post_id)

        detail = repo.get_post_detail(post_id)
        if not detail:
            raise ValueError(f"Post {post_id!r} not found after status transition")

        post = detail
        # Get latest version (versions are ordered ASC, so last = most recent)
        versions = detail.get("versions") or []
        version  = versions[-1] if versions else None

        # Merge post + version into a single dict for the publisher
        merged = {**post}
        if version:
            merged.update({k: v for k, v in version.items() if v})

        try:
            result = publisher.publish(
                merged, post_id=post_id, author=reviewer
            )
            published_ok = result.get("success", False)
        except Exception as exc:
            logger.error("Publish failed for post %s: %s", post_id, exc)
            published_ok = False
            result = {"success": False, "error": str(exc)}

        # Final state transition
        from .models import PostStatus
        final_status = PostStatus.PUBLISHED if published_ok else PostStatus.PUBLISH_FAILED
        approval.transition(
            post_id, final_status,
            actor=reviewer,
            actor_type="system",
            comment=result.get("error", "Published successfully") if not published_ok
                    else f"Published to {result.get('html_url', 'rawwebsite')}",
        )

        return result

    def get_queue(self, status: str = "pending_approval", limit: int = 50) -> dict:
        """Return the current review queue."""
        from .approval_service import ApprovalService
        return ApprovalService(brand=self.brand).get_review_queue(
            status=status, limit=limit
        )

    def get_queue_stats(self) -> dict:
        """Return counts per status."""
        from .approval_service import ApprovalService
        return ApprovalService(brand=self.brand).get_queue_stats()

    def get_post_detail(self, post_id: str) -> dict | None:
        """Return post + all versions + full review timeline."""
        from .approval_service import ApprovalService
        return ApprovalService(brand=self.brand).get_post_detail(post_id)
