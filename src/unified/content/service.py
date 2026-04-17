"""
Content Service — orchestrates the full content pipeline.

Pipeline:
  1. planner  → plan_day()       → 3 × ContentTopic
  2. generator → generate()     → ContentDraft
  3. validator → validate()      → ValidationResult
  4. service   → save_to_db()   → post + post_version in DB
  5. approval  → approve/reject → status transition in DB
  6. publisher → publish()      → .md file in rawwebsite repo

DB schema: reuses existing posts/post_versions/post_review_actions tables
           from db/schema_posts.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from .models import (
    ContentDraft, ContentTopic, PostStatus, PostType, ValidationResult,
)
from .planner import ContentPlanner
from .generator import ContentGenerator
from .validator import ContentValidator
from .publisher import ContentPublisher
from .policy import ContentPolicy

logger = logging.getLogger("content.service")


class ContentService:
    """
    Main orchestration service for the content pipeline.

    All DB writes go through this service to ensure consistent state
    and complete audit trails.
    """

    def __init__(self, brand: str = "raw"):
        self.brand    = brand
        self.repo     = self._repo()
        self.policy   = ContentPolicy()

    # ── Pipeline ─────────────────────────────────────────────────────────────

    def run_day(self) -> dict:
        """
        Run the complete daily pipeline: plan all 3 + generate all 3 + validate all 3.

        Returns a summary dict of all 3 posts.
        Failures in individual slots do NOT block other slots.
        """
        logger.info("[%s] Running daily pipeline for brand=%s",
                    datetime.now().strftime("%Y-%m-%d"), self.brand)

        planner   = ContentPlanner(brand=self.brand)
        generator = ContentGenerator(brand=self.brand)
        validator = ContentValidator(brand=self.brand)

        plans = planner.plan_day()
        results = []

        for plan in plans:
            try:
                result = self._generate_slot(plan, generator, validator)
                results.append(result)
            except Exception as exc:
                logger.exception("Slot %d failed: %s", plan.slot, exc)
                results.append({
                    "slot": plan.slot,
                    "type": plan.type,
                    "status": "failed",
                    "error": str(exc),
                })

        return {
            "brand":    self.brand,
            "date":     datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "slots":    results,
            "completed": sum(1 for r in results if r.get("status") == "pending_approval"),
            "failed":   sum(1 for r in results if r.get("status") == "failed"),
        }

    def generate_one(self, slot: int | None = None, topic_override: str = "") -> dict:
        """
        Generate and validate a single post.

        Args:
            slot: slot index (0, 1, 2) — uses that day's plan
            topic_override: if provided, replaces the topic text

        Returns the post DB record + validation result.
        """
        planner   = ContentPlanner(brand=self.brand)
        generator = ContentGenerator(brand=self.brand)
        validator = ContentValidator(brand=self.brand)

        plans = planner.plan_day()
        if slot is not None and 0 <= slot <= 2:
            plan = plans[slot]
        else:
            plan = plans[0]

        if topic_override:
            plan.topic = topic_override

        return self._generate_slot(plan, generator, validator)

    def _generate_slot(
        self,
        plan: ContentTopic,
        generator: ContentGenerator,
        validator: ContentValidator,
    ) -> dict:
        """Run generate + validate for one slot and save to DB."""
        # Generate
        draft = generator.generate(plan)

        # Validate
        val_result = validator.validate(draft)

        # Save to DB
        post_record = self._save_post(plan, draft, val_result)

        # Image attachment (Phase 1: just tag reference)
        image_tag = self._image_tag_for_type(plan.type)

        return {
            "slot":       plan.slot,
            "type":       plan.type.value if hasattr(plan.type, "value") else str(plan.type),
            "post_id":    post_record["id"],
            "status":     post_record["status"],
            "title":      draft.title,
            "quality_score": val_result.quality_score,
            "validation_decision": "PASS" if val_result.passed else "FAIL",
            "hard_valid": val_result.hard_valid,
            "issues":     val_result.hard_issues + val_result.quality_issues,
            "image_tag":  image_tag,
            "word_count": draft.word_count,
        }

    # ── Validation ──────────────────────────────────────────────────────────

    def validate_post(self, post_id: str) -> dict:
        """
        Re-validate an existing post (latest version).
        Returns updated validation result.
        """
        detail = self.repo.get_post_detail(post_id)
        if not detail:
            return {"error": f"Post {post_id} not found"}

        versions = detail.get("versions", [])
        version  = versions[-1] if versions else {}

        draft = ContentDraft(
            topic_id=post_id,
            title=version.get("title", detail.get("title", "")),
            slug=version.get("slug", detail.get("slug", "")) or "",
            meta_description=version.get("seo_description", detail.get("seo_description", "")),
            excerpt=version.get("excerpt", detail.get("excerpt", "")),
            body_markdown=version.get("body_markdown", detail.get("body_markdown", "")),
            cta=version.get("cta_text", detail.get("cta_text", "")),
            cta_url=version.get("cta_url", detail.get("cta_url", "")),
            keyword_primary=version.get("focus_keyword", detail.get("focus_keyword", "")),
            type=detail.get("post_type", "viral_attention"),
            target_audience=detail.get("target_audience", ""),
        )

        validator = ContentValidator(brand=self.brand)
        result = validator.validate(draft)

        # Update version review notes
        if versions:
            self.repo.update_version_review_status(
                versions[-1]["id"],
                review_status="PASS" if result.passed else "FAIL",
                notes=result.editor_notes,
            )

        return {
            "post_id": post_id,
            "version_id": versions[-1]["id"] if versions else None,
            "validation": {
                "passed":        result.passed,
                "hard_valid":    result.hard_valid,
                "quality_score": result.quality_score,
                "hard_issues":   result.hard_issues,
                "quality_issues": result.quality_issues,
                "reason":        result.reason,
                "editor_notes":  result.editor_notes,
            },
        }

    # ── Approval actions ──────────────────────────────────────────────────

    def approve(self, post_id: str, reviewer: str, note: str = "",
                schedule_at: str = "") -> dict:
        """
        Approve a post. Transitions: pending_approval → approved (or scheduled).

        Raises ValueError if post is not in pending_approval state.
        """
        post = self.repo.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id} not found")

        if post["status"] != PostStatus.PENDING_APPROVAL.value:
            raise ValueError(
                f"Post is in status '{post['status']}' — must be 'pending_approval' to approve."
            )

        to_status = PostStatus.SCHEDULED.value if schedule_at else PostStatus.APPROVED.value
        extra = {"approved_by": reviewer}
        if schedule_at:
            extra["scheduled_for"] = schedule_at

        self.repo.update_post_status(post_id, to_status, extra=extra)

        versions = self.repo.get_post_detail(post_id).get("versions", [])
        version_id = versions[-1]["id"] if versions else None

        self._add_review_action(
            post_id, version_id, reviewer, "human_reviewer",
            "approve", post["status"], to_status,
            note, {"schedule_at": schedule_at},
        )
        self._add_audit(
            reviewer, f"post_{to_status}", post_id,
            {"note": note}, {"status": post["status"]}, {"status": to_status},
        )

        logger.info("Post %s approved by %s → %s", post_id, reviewer, to_status)
        return self.repo.get_post(post_id) or {"id": post_id, "status": to_status}

    def reject(self, post_id: str, reviewer: str, reason: str) -> dict:
        """Reject a post. Transitions: pending_approval → rejected."""
        post = self.repo.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id} not found")
        if post["status"] != PostStatus.PENDING_APPROVAL.value:
            raise ValueError(f"Post status '{post['status']}' cannot be rejected.")

        self.repo.update_post_status(post_id, PostStatus.REJECTED.value)
        versions = self.repo.get_post_detail(post_id).get("versions", [])
        version_id = versions[-1]["id"] if versions else None

        self._add_review_action(
            post_id, version_id, reviewer, "human_reviewer",
            "reject", post["status"], PostStatus.REJECTED.value,
            reason, {},
        )
        self._add_audit(
            reviewer, "post_rejected", post_id,
            {"reason": reason}, {"status": post["status"]}, {"status": "rejected"},
        )

        logger.info("Post %s rejected by %s: %s", post_id, reviewer, reason)
        return self.repo.get_post(post_id) or {"id": post_id, "status": "rejected"}

    def request_revision(
        self, post_id: str, reviewer: str, feedback: str
    ) -> dict:
        """Request revision. Transitions: pending_approval → draft (re-open)."""
        post = self.repo.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id} not found")
        if post["status"] != PostStatus.PENDING_APPROVAL.value:
            raise ValueError("Can only request revision from pending_approval state.")

        self.repo.update_post_status(post_id, PostStatus.DRAFT.value)
        versions = self.repo.get_post_detail(post_id).get("versions", [])
        version_id = versions[-1]["id"] if versions else None

        self._add_review_action(
            post_id, version_id, reviewer, "human_reviewer",
            "request_revision", post["status"], PostStatus.DRAFT.value,
            feedback, {},
        )
        self._add_audit(
            reviewer, "post_revision_requested", post_id,
            {"feedback": feedback}, {"status": post["status"]}, {"status": "draft"},
        )

        logger.info("Revision requested on post %s by %s", post_id, reviewer)
        return self.repo.get_post(post_id) or {"id": post_id, "status": "draft"}

    # ── Publishing ────────────────────────────────────────────────────────

    def publish(self, post_id: str, author: str = "AgentAI Agency") -> dict:
        """
        Publish an approved post to RawWebsite.

        Transitions: approved/scheduled → published
        Raises ValueError if post is not in an approved state.
        """
        post = self.repo.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id} not found")

        if post["status"] not in (PostStatus.APPROVED.value, PostStatus.SCHEDULED.value, PostStatus.PUBLISHED.value):
            raise ValueError(
                f"Post is in status '{post['status']}' — must be approved to publish."
            )

        # Transition to published
        self.repo.update_post_status(
            post_id, PostStatus.PUBLISHED.value,
            extra={"published_at": datetime.now(timezone.utc).isoformat()},
        )

        detail = self.repo.get_post_detail(post_id)
        versions = detail.get("versions", [])
        version  = versions[-1] if versions else {}

        # Build ContentDraft-like object for publisher
        draft = ContentDraft(
            topic_id=post_id,
            title=version.get("title") or post.get("title", ""),
            slug=version.get("slug") or post.get("slug", ""),
            meta_description=version.get("seo_description") or post.get("seo_description", ""),
            excerpt=version.get("excerpt") or post.get("excerpt", ""),
            body_markdown=version.get("body_markdown") or post.get("body_markdown", ""),
            cta=version.get("cta_text") or post.get("cta_text", ""),
            cta_url=version.get("cta_url") or post.get("cta_url", ""),
            keyword_primary=version.get("focus_keyword") or post.get("focus_keyword", ""),
            type=post.get("post_type", "blog"),
            target_audience=post.get("target_audience", ""),
        )

        publisher = ContentPublisher()
        pub_result = publisher.publish(post_id, draft, author=author)

        # Audit
        self._add_review_action(
            post_id, version.get("id"), "system", "system",
            "publish", post["status"], PostStatus.PUBLISHED.value,
            f"Published via {pub_result.get('mode', 'content_service')}",
            pub_result,
        )
        self._add_audit(
            "system", "post_published", post_id,
            pub_result, {"status": post["status"]}, {"status": "published"},
        )

        logger.info("Post %s published: %s", post_id, pub_result.get("html_url"))
        return pub_result

    # ── Queue ────────────────────────────────────────────────────────────

    def list_posts(
        self,
        status: str | None = None,
        post_type: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """List posts with optional filters."""
        posts = self.repo.list_review_queue(
            status=status,
            channel="rawwebsite",
            brand="Raw Sushi Bar",
            post_type=post_type,
            keyword=q,
            limit=limit,
            offset=offset,
        )
        return {"posts": posts, "count": len(posts)}

    def get_post(self, post_id: str) -> dict | None:
        return self.repo.get_post_detail(post_id)

    def queue_stats(self) -> dict:
        """Return pending/approved/published counts."""
        statuses = ["pending_approval", "approved", "published", "draft", "rejected"]
        return {
            s: self._count_by_status(s)
            for s in statuses
        }

    # ── DB helpers ────────────────────────────────────────────────────────

    def _save_post(
        self,
        plan: ContentTopic,
        draft: ContentDraft,
        val_result: ValidationResult,
    ) -> dict:
        """Create post + version record in DB."""
        post_id   = str(uuid4())
        version_id = str(uuid4())
        now       = datetime.now(timezone.utc).isoformat()

        # Determine status
        if val_result.passed:
            status = PostStatus.PENDING_APPROVAL.value
        else:
            status = PostStatus.DRAFT.value  # failed validation stays as draft

        # Create post
        self.repo.create_post({
            "id":               post_id,
            "brand_name":       "Raw Sushi Bar",
            "channel":          "rawwebsite",
            "title":            draft.title,
            "slug":             draft.slug,
            "excerpt":          draft.excerpt,
            "body_markdown":    draft.body_markdown,
            "cta_text":         draft.cta,
            "cta_url":          draft.cta_url,
            "seo_title":        draft.title,
            "seo_description":  draft.meta_description,
            "focus_keyword":    draft.keyword_primary,
            "post_type":        draft.type.value if hasattr(draft.type, "value") else str(draft.type),
            "target_audience":  draft.target_audience,
            "status":           status,
            "created_by":       "content_service",
            "created_at":       now,
            "updated_at":       now,
        })

        # Create version
        self.repo.create_version({
            "id":                   version_id,
            "post_id":              post_id,
            "version_no":           1,
            "title":                draft.title,
            "excerpt":              draft.excerpt,
            "body_markdown":        draft.body_markdown,
            "cta_text":             draft.cta,
            "cta_url":              draft.cta_url,
            "seo_title":            draft.title,
            "seo_description":      draft.meta_description,
            "focus_keyword":        draft.keyword_primary,
            "featured_image_prompt": draft.image_url or "",
            "featured_image_url":   draft.image_url or "",
            "agent_score":          val_result.quality_score,
            "review_status":        "PASS" if val_result.passed else "FAIL",
            "review_notes":         val_result.editor_notes,
        })

        # Review action
        self._add_review_action(
            post_id, version_id,
            "content_service", "ai_agent",
            "post_generated",
            None, status,
            f"Generated {plan.type.value}. Score: {val_result.quality_score:.1f}. Decision: {val_result.reason}",
            {
                "plan_slot": plan.slot,
                "post_type": plan.type.value if hasattr(plan.type, "value") else str(plan.type),
                "quality_score": val_result.quality_score,
                "hard_valid": val_result.hard_valid,
                "validation_decision": val_result.reason,
            },
        )
        self._add_audit(
            "content_service", "post_generated", post_id,
            {
                "plan_slot": plan.slot,
                "post_type": plan.type.value if hasattr(plan.type, "value") else str(plan.type),
                "validation": val_result.reason,
                "version_id": version_id,
            },
        )

        return {"id": post_id, "status": status, "version_id": version_id}

    def _add_review_action(
        self,
        post_id: str,
        version_id: str | None,
        actor: str,
        actor_type: str,
        action_type: str,
        from_status: str | None,
        to_status: str,
        comment: str,
        payload: dict,
    ) -> None:
        self.repo.add_review_action({
            "post_id":        post_id,
            "post_version_id": version_id,
            "actor":          actor,
            "actor_type":     actor_type,
            "action_type":    action_type,
            "from_status":    from_status,
            "to_status":      to_status,
            "comment":         comment,
            "payload":         payload,
        })

    def _add_audit(
        self,
        actor: str,
        action_type: str,
        entity_id: str,
        details: dict,
        from_state: dict | None = None,
        to_state: dict | None = None,
    ) -> None:
        self.repo.add_audit_entry(
            actor=actor,
            action_type=action_type,
            entity_id=entity_id,
            details=details,
            from_state=from_state,
            to_state=to_state,
        )

    def _count_by_status(self, status: str) -> int:
        conn = self.repo._conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM posts WHERE status = ? AND channel = ?",
                (status, "rawwebsite"),
            ).fetchone()
            return row["cnt"] if row else 0
        finally:
            conn.close()

    @staticmethod
    def _repo():
        from db.post_repository import PostRepository
        return PostRepository()

    @staticmethod
    def _image_tag_for_type(ptype) -> str:
        tags = {
            "viral_attention":   "sushi_roll",
            "conversion_order":  "menu_item",
            "local_discovery":   "interior",
            "tourist_discovery": "storefront",
            "menu_highlight":    "sushi_roll",
        }
        key = ptype.value if hasattr(ptype, "value") else str(ptype)
        return tags.get(key, "dining")
