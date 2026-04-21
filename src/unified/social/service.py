"""
SocialService — main orchestrator for the social media automation pipeline.

Coordinates generation, policy validation, approval, scheduling, and publishing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .generator import SocialPostGenerator, get_content_type_for_today, _WEEKLY_ROTATION
from .models import (
    ApprovalMode,
    ContentType,
    Platform,
    PostGoal,
    PublishLog,
    SocialPost,
    SocialPostStatus,
    StoreProfile,
)
from .policy import SocialContentPolicy
from .scheduler import SocialScheduler, _GOAL_MAP
from .seed_posts import build_seed_posts
from .services import get_publisher
from .store_profiles import get_store

logger = logging.getLogger("social.service")


class SocialService:
    """Main orchestrator for the social media automation pipeline.

    Ties together generation, policy validation, scheduling, and publishing.
    """

    def __init__(self) -> None:
        self.generator = SocialPostGenerator()
        self.policy = SocialContentPolicy()
        self.scheduler = SocialScheduler()

    # ── Core helpers ───────────────────────────────────────────────────────────

    def _run_policy(self, post: SocialPost, store: StoreProfile) -> SocialPost:
        """Run the content policy check and update post status / score in-place."""
        combined_text = f"{post.headline} {post.body} {post.cta}"
        result = self.policy.validate(combined_text, store, post.content_type)

        post.policy_score = result.score
        post.policy_result = result.model_dump()

        if result.passed:
            post.status = SocialPostStatus.PENDING_APPROVAL
            logger.info("Policy PASSED post_id=%s score=%d", post.id, result.score)
        else:
            post.status = SocialPostStatus.POLICY_FAILED
            logger.warning(
                "Policy FAILED post_id=%s score=%d reason=%s",
                post.id,
                result.score,
                result.block_reason,
            )

        return post

    # ── Public API ─────────────────────────────────────────────────────────────

    def generate_and_validate(
        self,
        store_id: str,
        content_type: ContentType | None = None,
        goal: PostGoal | None = None,
    ) -> SocialPost:
        """Generate a social post for the given store and run policy validation.

        Args:
            store_id: Registered store identifier.
            content_type: Override the weekly-rotation content type. If None,
                          uses the rotation for today's weekday.
            goal: Override the default goal for the content type. If None,
                  uses the goal map.

        Returns:
            A SocialPost with status=PENDING_APPROVAL or POLICY_FAILED.
        """
        store = get_store(store_id)

        if content_type is None:
            content_type = get_content_type_for_today()
        if goal is None:
            goal = _GOAL_MAP.get(content_type, PostGoal.DRIVE_VISIT)

        post = self.generator.generate(store, content_type, goal)
        post = self._run_policy(post, store)
        return post

    def approve_post(self, post: SocialPost, approved_by: str = "system") -> SocialPost:
        """Transition a post from PENDING_APPROVAL to APPROVED.

        Args:
            post: The post to approve. Must be in PENDING_APPROVAL status.
            approved_by: Identifier of the approver (user name, 'system', etc.).

        Returns:
            The updated SocialPost with status=APPROVED.

        Raises:
            ValueError: If the post is not in an approvable state.
        """
        if post.status not in (SocialPostStatus.PENDING_APPROVAL, SocialPostStatus.GENERATED):
            raise ValueError(
                f"Cannot approve post id={post.id} in status={post.status.value}."
            )
        post.status = SocialPostStatus.APPROVED
        post.approved_by = approved_by
        logger.info("Post approved id=%s by=%s", post.id, approved_by)
        return post

    def publish_now(self, post: SocialPost) -> list[PublishLog]:
        """Publish an approved post immediately to all store platforms.

        Args:
            post: A SocialPost in APPROVED or SCHEDULED status.

        Returns:
            A list of PublishLog records, one per platform.

        Raises:
            ValueError: If the post store_id is unknown.
        """
        store = get_store(post.store_id)
        logs: list[PublishLog] = []

        post.status = SocialPostStatus.PUBLISHING
        logger.info("Starting publish post_id=%s platforms=%s", post.id, store.platforms)

        for platform in store.platforms:
            publisher = get_publisher(platform)
            try:
                log = publisher.publish_post(post)
                logs.append(log)
                if log.status == "published":
                    logger.info(
                        "Published post_id=%s platform=%s external_id=%s",
                        post.id,
                        platform.value,
                        log.external_post_id,
                    )
                else:
                    logger.error(
                        "Publish failed post_id=%s platform=%s",
                        post.id,
                        platform.value,
                    )
            except Exception as exc:
                logger.error(
                    "Exception publishing post_id=%s platform=%s: %s",
                    post.id,
                    platform.value,
                    exc,
                )
                logs.append(
                    PublishLog(
                        post_id=post.id,
                        platform=platform,
                        status="failed",
                        response_json={"exception": str(exc)},
                    )
                )

        # Update post status based on whether all publishes succeeded
        all_ok = all(lg.status in ("published", "scheduled") for lg in logs)
        any_ok = any(lg.status in ("published", "scheduled") for lg in logs)

        if all_ok:
            post.status = SocialPostStatus.PUBLISHED
            post.published_at = datetime.now(timezone.utc)
            # Use the first successful external_post_id
            for lg in logs:
                if lg.external_post_id:
                    post.external_post_id = lg.external_post_id
                    break
        elif any_ok:
            post.status = SocialPostStatus.PUBLISHED
            post.published_at = datetime.now(timezone.utc)
        else:
            post.status = SocialPostStatus.PUBLISH_FAILED

        return logs

    def run_daily_pipeline(self, store_id: str) -> list[SocialPost]:
        """Execute the full daily social post pipeline for a store.

        Flow:
          1. Get today's scheduled slots.
          2. For each slot, generate content and validate against policy.
          3. Depending on the store's approval_mode:
             - FULL_AUTO: approve and publish immediately.
             - APPROVAL_REQUIRED: leave in PENDING_APPROVAL for human review.
             - DRAFT_ONLY: generate only, no publishing.

        Args:
            store_id: Registered store identifier.

        Returns:
            A list of SocialPost objects reflecting the pipeline outcome.
        """
        store = get_store(store_id)
        if not store.is_active:
            logger.info("Skipping daily pipeline for inactive store=%s", store_id)
            return []

        stubs = self.scheduler.get_todays_queue(store)
        results: list[SocialPost] = []

        for stub in stubs:
            try:
                post = self.generator.generate(store, stub.content_type, stub.goal)
                post.scheduled_at = stub.scheduled_at
                post = self._run_policy(post, store)

                if store.approval_mode == ApprovalMode.FULL_AUTO:
                    if post.status == SocialPostStatus.PENDING_APPROVAL:
                        post = self.approve_post(post, approved_by="system")
                        self.publish_now(post)
                    else:
                        logger.warning(
                            "Skipping auto-publish due to policy failure post_id=%s", post.id
                        )
                elif store.approval_mode == ApprovalMode.APPROVAL_REQUIRED:
                    # Leave in PENDING_APPROVAL for human review
                    logger.info("Post queued for approval post_id=%s store=%s", post.id, store_id)
                elif store.approval_mode == ApprovalMode.DRAFT_ONLY:
                    logger.info("Draft-only mode: post_id=%s generated but not queued", post.id)

                results.append(post)

            except Exception as exc:
                logger.error(
                    "Pipeline error for store=%s slot=%s: %s",
                    store_id,
                    stub.scheduled_at,
                    exc,
                )

        logger.info(
            "Daily pipeline complete store=%s posts_generated=%d",
            store_id,
            len(results),
        )
        return results

    def seed_posts(self, store_id: str) -> list[SocialPost]:
        """Load, validate, and return the pre-approved seed posts for a store.

        Seed posts bypass generation and go straight through policy validation.
        Those that pass policy are returned with PENDING_APPROVAL status.
        Those that already have APPROVED status in the seed data retain it.

        Args:
            store_id: Registered store identifier.

        Returns:
            A list of SocialPost objects that passed policy validation.
        """
        store = get_store(store_id)
        raw_posts = build_seed_posts(store)
        validated: list[SocialPost] = []

        for post in raw_posts:
            # Seed posts are pre-approved — run policy for logging but keep status
            combined = f"{post.headline} {post.body} {post.cta}"
            result = self.policy.validate(combined, store, post.content_type)
            post.policy_score = result.score
            post.policy_result = result.model_dump()

            if result.passed:
                validated.append(post)
                logger.info(
                    "Seed post validated post_id=%s score=%d status=%s",
                    post.id,
                    result.score,
                    post.status.value,
                )
            else:
                logger.warning(
                    "Seed post FAILED policy post_id=%s score=%d reason=%s",
                    post.id,
                    result.score,
                    result.block_reason,
                )

        logger.info(
            "Seed posts loaded store=%s total=%d passed=%d",
            store_id,
            len(raw_posts),
            len(validated),
        )
        return validated
