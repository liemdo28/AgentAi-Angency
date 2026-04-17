"""
Approval Service — manages the post review queue and state machine.

States:
  planned → researching → drafted → validation_failed → pending_approval
  → approved → rejected → revision_requested → publishing → published
  → publish_failed

All state transitions are validated and logged to both:
  - post_review_actions table
  - audit_log table

No auto-publish in Phase 1 — human approval always required.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from .models import ApprovalAction, ContentDraft, ContentPlan, PostStatus, PublishResult

logger = logging.getLogger("content_automation.approval_service")

# Valid state transitions
_VALID_TRANSITIONS: dict[PostStatus, list[PostStatus]] = {
    PostStatus.PLANNED:             [PostStatus.RESEARCHING],
    PostStatus.RESEARCHING:         [PostStatus.DRAFTED, PostStatus.PLANNED],
    PostStatus.DRAFTED:             [PostStatus.PENDING_APPROVAL, PostStatus.VALIDATION_FAILED],
    PostStatus.VALIDATION_FAILED:  [PostStatus.PLANNED, PostStatus.PENDING_APPROVAL],
    PostStatus.PENDING_APPROVAL:    [PostStatus.APPROVED, PostStatus.REJECTED, PostStatus.REVISION_REQUESTED],
    PostStatus.REVISION_REQUESTED: [PostStatus.RESEARCHING, PostStatus.DRAFTED, PostStatus.PENDING_APPROVAL],
    PostStatus.APPROVED:            [PostStatus.PUBLISHING],
    PostStatus.PUBLISHING:          [PostStatus.PUBLISHED, PostStatus.PUBLISH_FAILED],
    PostStatus.REJECTED:            [],  # terminal (archived manually)
    PostStatus.PUBLISHED:           [],
    PostStatus.PUBLISH_FAILED:      [PostStatus.APPROVED],
}


# ─────────────────────────────────────────────────────────────────────────────
#  ApprovalService
# ─────────────────────────────────────────────────────────────────────────────

class ApprovalService:
    """
    Manages the post review queue, state machine, and audit trail.

    Uses the existing PostRepository from db/post_repository.py.
    Also writes to the new content_automation_jobs table for job tracking.
    """

    def __init__(self, brand: str = "raw"):
        self.brand = brand

    # ── State Machine ─────────────────────────────────────────────────────────

    def transition(
        self,
        post_id: str,
        to_status: PostStatus,
        actor: str = "system",
        actor_type: str = "ai_agent",
        comment: str = "",
        extra: dict | None = None,
    ) -> dict:
        """
        Validate and execute a state transition on a post.

        Returns dict with post record after transition.
        Raises ValueError if transition is not allowed.
        """
        repo = self._repo()
        post = repo.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id!r} not found")

        from_status = PostStatus(post["status"])
        if to_status not in _VALID_TRANSITIONS.get(from_status, []):
            raise ValueError(
                f"Cannot transition post from {from_status.value!r} to {to_status.value!r}. "
                f"Allowed: {[s.value for s in _VALID_TRANSITIONS.get(from_status, [])]}"
            )

        # Execute transition
        repo.update_post_status(post_id, to_status.value, extra=extra)

        # Audit log
        repo.add_review_action({
            "post_id": post_id,
            "actor": actor,
            "actor_type": actor_type,
            "action_type": f"ca_{to_status.value}",
            "from_status": from_status.value,
            "to_status": to_status.value,
            "comment": comment,
        })
        repo.add_audit_entry(
            actor=actor,
            action_type=f"post_{to_status.value}",
            entity_id=post_id,
            details={"comment": comment},
            from_state={"status": from_status.value},
            to_state={"status": to_status.value},
        )

        logger.info(
            "Post %s: %s → %s (actor=%s)",
            post_id, from_status.value, to_status.value, actor,
        )
        return repo.get_post(post_id) or {"id": post_id, "status": to_status.value}

    def approve(
        self, post_id: str, reviewer: str, comment: str = "", schedule_at: str | None = None
    ) -> dict:
        """
        Human approval: pending_approval → approved (or scheduled).

        Args:
            reviewer: name/ID of the reviewer
            comment: optional review note
            schedule_at: optional ISO-8601 datetime to transition to 'scheduled' instead
        """
        to_status = PostStatus.SCHEDULED if schedule_at else PostStatus.APPROVED
        extra: dict[str, Any] = {"approved_by": reviewer}
        if schedule_at:
            extra["scheduled_for"] = schedule_at

        return self.transition(
            post_id, to_status, actor=reviewer, actor_type="human_reviewer",
            comment=comment, extra=extra,
        )

    def reject(self, post_id: str, reviewer: str, reason: str) -> dict:
        """Human rejection: pending_approval → rejected."""
        return self.transition(
            post_id, PostStatus.REJECTED,
            actor=reviewer, actor_type="human_reviewer",
            comment=f"Rejected: {reason}",
        )

    def request_revision(
        self, post_id: str, reviewer: str, feedback: str
    ) -> dict:
        """Human revision request: pending_approval → revision_requested."""
        return self.transition(
            post_id, PostStatus.REVISION_REQUESTED,
            actor=reviewer, actor_type="human_reviewer",
            comment=f"Revision requested: {feedback}",
        )

    def submit_for_approval(
        self, post_id: str, version_id: str, score: float, notes: str = ""
    ) -> dict:
        """
        System transition: drafted → pending_approval after successful generation.

        Called by the pipeline when a draft passes validation.
        """
        return self.transition(
            post_id, PostStatus.PENDING_APPROVAL,
            actor="content_automation",
            actor_type="ai_agent",
            comment=f"Submitted for review. Score: {score:.1f}. Notes: {notes}",
            extra={"version_id": version_id},
        )

    def mark_validation_failed(
        self, post_id: str, reason: str, version_id: str | None = None
    ) -> dict:
        """System transition: drafted → validation_failed."""
        return self.transition(
            post_id, PostStatus.VALIDATION_FAILED,
            actor="content_automation",
            actor_type="ai_agent",
            comment=f"Validation failed: {reason}",
            extra={"version_id": version_id} if version_id else None,
        )

    def begin_publish(self, post_id: str) -> dict:
        """System transition: approved → publishing."""
        return self.transition(
            post_id, PostStatus.PUBLISHING,
            actor="content_automation",
            actor_type="system",
            comment="Publish job started.",
        )

    # ── Queue management ──────────────────────────────────────────────────────

    def get_review_queue(
        self,
        status: str | None = "pending_approval",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Return posts in the review queue.

        Default: status='pending_approval' (posts awaiting human review).
        Pass status='all' to get all statuses.
        """
        repo = self._repo()
        effective_status = None if status == "all" else status
        posts = repo.list_review_queue(
            status=effective_status,
            channel="rawwebsite",
            brand="Raw Sushi Bar",
            limit=limit,
            offset=offset,
        )
        return {"posts": posts, "count": len(posts), "status_filter": status}

    def get_post_detail(self, post_id: str) -> dict | None:
        """Return post + all versions + full review timeline."""
        repo = self._repo()
        return repo.get_post_detail(post_id)

    def get_queue_stats(self) -> dict:
        """Return counts per status for the content dashboard."""
        repo = self._repo()
        total_pending = repo.count_pending()
        return {
            "pending_review": total_pending,
            "approved":       self._count_by_status(PostStatus.APPROVED.value),
            "published":      self._count_by_status(PostStatus.PUBLISHED.value),
            "rejected":       self._count_by_status(PostStatus.REJECTED.value),
            "drafting":       self._count_by_status(PostStatus.DRAFTED.value),
        }

    # ── Pipeline integration ─────────────────────────────────────────────────

    def create_post_from_plan(
        self, plan: ContentPlan, draft: ContentDraft, validation_passed: bool
    ) -> dict:
        """
        Create a post record from a ContentPlan + ContentDraft + validation result.

        This is the entry point from the pipeline:
          1. Create post record (status=drafted or validation_failed)
          2. Create post_version
          3. Write audit entries
          4. Return the created post
        """
        post_id = str(uuid4())
        version_id = str(uuid4())
        now = self._now()

        # Validation result for version
        val_result = draft.validation_result
        publish_decision = val_result.publish_decision if val_result else "FAIL"
        agent_score = val_result.quality_score if val_result else 0.0

        # Determine initial status
        if validation_passed:
            initial_status = "pending_approval"
        else:
            initial_status = "validation_failed"

        # Create post
        repo = self._repo()
        post = repo.create_post({
            "id": post_id,
            "brand_name": "Raw Sushi Bar",
            "channel": "rawwebsite",
            "title": draft.title,
            "slug": draft.slug,
            "excerpt": draft.excerpt,
            "body_markdown": draft.body_markdown,
            "cta_text": draft.cta_text,
            "cta_url": draft.cta_url,
            "seo_title": draft.seo_title or draft.title,
            "seo_description": draft.meta_description,
            "focus_keyword": draft.focus_keyword,
            "post_type": draft.post_type,
            "target_audience": draft.target_audience,
            "status": initial_status,
            "created_by": "content_automation",
            "created_at": now,
            "updated_at": now,
        })

        # Create version
        repo.create_version({
            "id": version_id,
            "post_id": post_id,
            "version_no": 1,
            "generation_prompt": plan.topic[:500],
            "model_provider": "anthropic",
            "model_name": "claude",
            "title": draft.title,
            "excerpt": draft.excerpt,
            "body_markdown": draft.body_markdown,
            "cta_text": draft.cta_text,
            "cta_url": draft.cta_url,
            "seo_title": draft.seo_title,
            "seo_description": draft.meta_description,
            "focus_keyword": draft.focus_keyword,
            "featured_image_prompt": draft.image_prompt,
            "featured_image_url": draft.image_url,
            "agent_score": agent_score,
            "review_status": "pending",
            "review_notes": publish_decision,
        })

        # Audit entry
        repo.add_review_action({
            "post_id": post_id,
            "post_version_id": version_id,
            "actor": "content_automation",
            "actor_type": "ai_agent",
            "action_type": "post_generated",
            "from_status": None,
            "to_status": initial_status,
            "comment": (
                f"ContentDraft created from plan_id={plan.id}. "
                f"Type: {plan.post_type.value}. "
                f"Validation: {publish_decision}. Score: {agent_score:.1f}."
            ),
            "payload": {
                "plan_id": plan.id,
                "post_type": plan.post_type.value,
                "validation_decision": publish_decision,
                "quality_score": agent_score,
                "hard_valid": (val_result.hard_valid if val_result else False),
            },
        })

        repo.add_audit_entry(
            actor="content_automation",
            action_type="post_generated",
            entity_id=post_id,
            details={
                "plan_id": plan.id,
                "post_type": plan.post_type.value,
                "validation_decision": publish_decision,
                "agent_score": agent_score,
                "version_id": version_id,
            },
        )

        logger.info(
            "Post created: id=%s status=%s plan_id=%s type=%s",
            post_id, initial_status, plan.id, plan.post_type.value,
        )
        return {
            "post_id": post_id,
            "version_id": version_id,
            "status": initial_status,
            "agent_score": agent_score,
        }

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _repo(self):
        from db.post_repository import PostRepository
        return PostRepository()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _count_by_status(self, status: str) -> int:
        repo = self._repo()
        conn = repo._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM posts WHERE status = ? AND channel = ?",
                (status, "rawwebsite"),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()