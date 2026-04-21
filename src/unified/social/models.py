"""
Pydantic v2 data models for the social media automation module.

Covers store profiles, post lifecycle, policy results, publish logs,
and weekly content rotation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class Platform(str, Enum):
    """Supported social media platforms."""
    FACEBOOK  = "facebook"
    INSTAGRAM = "instagram"


class SocialPostStatus(str, Enum):
    """Full lifecycle state machine for a social post."""
    PLANNED          = "planned"
    GENERATED        = "generated"
    POLICY_FAILED    = "policy_failed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED         = "approved"
    REJECTED         = "rejected"
    SCHEDULED        = "scheduled"
    PUBLISHING       = "publishing"
    PUBLISHED        = "published"
    PUBLISH_FAILED   = "publish_failed"


class PostGoal(str, Enum):
    """Business objective for a given social post."""
    DRIVE_ORDER        = "drive_order"
    DRIVE_VISIT        = "drive_visit"
    BUILD_TRUST        = "build_trust"
    LOCAL_SEO          = "local_seo"
    INCREASE_REACH     = "increase_reach"
    DRIVE_GROUP_DINING = "drive_group_dining"


class ContentType(str, Enum):
    """Content format / campaign type."""
    FRESHNESS_PUSH = "freshness_push"
    LOCAL_SEO_POST = "local_seo_post"
    ORDER_CTA_POST = "order_cta_post"
    WEEKEND_VIBE   = "weekend_vibe_post"
    SOCIAL_PROOF   = "social_proof_post"
    MENU_HIGHLIGHT = "menu_highlight"
    SEASONAL       = "seasonal"
    REVIEW_BASED   = "review_based"
    EVENT          = "event"


class ApprovalMode(str, Enum):
    """Controls how posts move from generated to published."""
    FULL_AUTO         = "full_auto"
    APPROVAL_REQUIRED = "approval_required"
    DRAFT_ONLY        = "draft_only"


# ── Sub-models ─────────────────────────────────────────────────────────────────

class ToneProfile(BaseModel):
    """Brand voice configuration for a store location."""

    style: str = Field(..., description="Writing style descriptor, e.g. 'friendly, modern, local'")
    reading_level: str = Field(default="simple", description="Target reading level")
    emoji_level: str = Field(default="light", description="Emoji usage: none | light | moderate | heavy")


# ── Core models ────────────────────────────────────────────────────────────────

class StoreProfile(BaseModel):
    """Complete configuration for a single store location."""

    store_id: str
    store_name: str
    city: str
    state: str
    country: str
    timezone: str
    address: str
    phone: str
    order_url: Optional[str] = None
    menu_url: Optional[str] = None
    location_url: Optional[str] = None
    primary_keywords: list[str] = Field(default_factory=list)
    secondary_keywords: list[str] = Field(default_factory=list)
    tone_profile: ToneProfile = Field(default_factory=lambda: ToneProfile(style="friendly, casual"))
    posting_hours: list[str] = Field(default_factory=list, description="HH:MM strings in store local time")
    platforms: list[Platform] = Field(default_factory=list)
    target_actions: list[str] = Field(default_factory=list, description="e.g. ['visit', 'order', 'reserve']")
    approval_mode: ApprovalMode = ApprovalMode.APPROVAL_REQUIRED
    is_active: bool = True


class SocialPost(BaseModel):
    """A single social media post throughout its full lifecycle."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str
    platform: Platform = Platform.FACEBOOK
    scheduled_at: Optional[datetime] = None
    content_type: ContentType
    goal: PostGoal
    status: SocialPostStatus = SocialPostStatus.PLANNED
    headline: str = ""
    body: str = ""
    cta: str = ""
    hashtags: list[str] = Field(default_factory=list)
    seo_terms: list[str] = Field(default_factory=list)
    image_url: Optional[str] = None
    policy_score: int = 0
    policy_result: dict = Field(default_factory=dict)
    approved_by: Optional[str] = None
    published_at: Optional[datetime] = None
    external_post_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SocialPolicyResult(BaseModel):
    """Result of a content policy check on a social post body."""

    passed: bool
    score: int
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    block_reason: Optional[str] = None


class PublishLog(BaseModel):
    """Record of a single publish attempt for a social post."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    post_id: str
    platform: Platform
    status: str
    external_post_id: Optional[str] = None
    response_json: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# WeeklyRotation: maps lowercase weekday name → ContentType
WeeklyRotation = dict[str, ContentType]
