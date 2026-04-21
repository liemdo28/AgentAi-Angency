"""
Social post scheduler.

Generates planned SocialPost stubs for a store's posting schedule,
using the weekly content rotation and goal map.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from .generator import _WEEKLY_ROTATION
from .models import (
    ContentType,
    Platform,
    PostGoal,
    SocialPost,
    SocialPostStatus,
    StoreProfile,
)

logger = logging.getLogger("social.scheduler")

# ── Goal map ───────────────────────────────────────────────────────────────────
_GOAL_MAP: dict[ContentType, PostGoal] = {
    ContentType.FRESHNESS_PUSH: PostGoal.DRIVE_ORDER,
    ContentType.LOCAL_SEO_POST: PostGoal.LOCAL_SEO,
    ContentType.ORDER_CTA_POST: PostGoal.DRIVE_ORDER,
    ContentType.WEEKEND_VIBE:   PostGoal.DRIVE_GROUP_DINING,
    ContentType.SOCIAL_PROOF:   PostGoal.BUILD_TRUST,
    ContentType.MENU_HIGHLIGHT: PostGoal.DRIVE_VISIT,
    ContentType.REVIEW_BASED:   PostGoal.BUILD_TRUST,
    ContentType.SEASONAL:       PostGoal.INCREASE_REACH,
    ContentType.EVENT:          PostGoal.DRIVE_VISIT,
}


class SocialScheduler:
    """Creates planned SocialPost stubs based on store posting schedules."""

    def _make_stub(
        self,
        store: StoreProfile,
        scheduled_at: datetime,
        content_type: ContentType,
    ) -> SocialPost:
        """Create a minimal planned post stub for a single time slot."""
        goal = _GOAL_MAP.get(content_type, PostGoal.DRIVE_VISIT)
        platform = store.platforms[0] if store.platforms else Platform.FACEBOOK

        return SocialPost(
            id=str(uuid.uuid4()),
            store_id=store.store_id,
            platform=platform,
            scheduled_at=scheduled_at,
            content_type=content_type,
            goal=goal,
            status=SocialPostStatus.PLANNED,
        )

    def plan_week(self, store: StoreProfile, start_date: date) -> list[SocialPost]:
        """Return 7 days × len(posting_hours) planned SocialPost stubs.

        Args:
            store: The store profile with timezone and posting_hours.
            start_date: The first day of the week to plan (inclusive).

        Returns:
            A flat list of planned SocialPost stubs, one per (day, hour) slot.
        """
        tz = ZoneInfo(store.timezone)
        posts: list[SocialPost] = []

        for day_offset in range(7):
            current_date = start_date + timedelta(days=day_offset)
            weekday = current_date.weekday()
            content_type = _WEEKLY_ROTATION[weekday]

            for hour_str in store.posting_hours:
                hh, mm = map(int, hour_str.split(":"))
                slot_dt = datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    hh,
                    mm,
                    0,
                    tzinfo=tz,
                )
                posts.append(self._make_stub(store, slot_dt, content_type))

        logger.info(
            "Planned %d slots for store=%s starting %s",
            len(posts),
            store.store_id,
            start_date.isoformat(),
        )
        return posts

    def get_todays_queue(self, store: StoreProfile) -> list[SocialPost]:
        """Return today's post slots as planned stubs.

        Args:
            store: The store profile with timezone and posting_hours.

        Returns:
            A list of SocialPost stubs for each posting slot today.
        """
        tz = ZoneInfo(store.timezone)
        today_local = datetime.now(tz).date()
        weekday = today_local.weekday()
        content_type = _WEEKLY_ROTATION[weekday]

        posts: list[SocialPost] = []
        for hour_str in store.posting_hours:
            hh, mm = map(int, hour_str.split(":"))
            slot_dt = datetime(
                today_local.year,
                today_local.month,
                today_local.day,
                hh,
                mm,
                0,
                tzinfo=tz,
            )
            posts.append(self._make_stub(store, slot_dt, content_type))

        logger.info(
            "Today's queue: %d slots for store=%s date=%s",
            len(posts),
            store.store_id,
            today_local.isoformat(),
        )
        return posts

    def get_next_slot_time(self, store: StoreProfile) -> datetime:
        """Return the next scheduled posting time in the store's local timezone.

        If all slots for today have passed, returns the first slot tomorrow.

        Args:
            store: The store profile with timezone and posting_hours.

        Returns:
            A timezone-aware datetime for the next posting slot.
        """
        tz = ZoneInfo(store.timezone)
        now_local = datetime.now(tz)
        today = now_local.date()

        # Check today's remaining slots
        for hour_str in sorted(store.posting_hours):
            hh, mm = map(int, hour_str.split(":"))
            slot_dt = datetime(today.year, today.month, today.day, hh, mm, 0, tzinfo=tz)
            if slot_dt > now_local:
                logger.debug("Next slot for store=%s is %s", store.store_id, slot_dt.isoformat())
                return slot_dt

        # All slots for today passed — return first slot tomorrow
        tomorrow = today + timedelta(days=1)
        first_hour = sorted(store.posting_hours)[0]
        hh, mm = map(int, first_hour.split(":"))
        next_slot = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hh, mm, 0, tzinfo=tz)
        logger.debug("Next slot for store=%s is tomorrow %s", store.store_id, next_slot.isoformat())
        return next_slot
