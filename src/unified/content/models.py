"""
Data models for the content automation pipeline (src/unified/content/).

Defines:
  - PostType    : 4 content types for the daily rotation
  - PostStatus  : 5-state approval machine
  - ContentTopic: planner output
  - ContentDraft: generator output (full post)
  - ValidationResult: validator output
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────────────────

class PostType(str, Enum):
    """
    Daily content types. Exactly 3 per day:
      Slot 0: VIRAL_ATTENTION
      Slot 1: CONVERSION_ORDER
      Slot 2: LOCAL_DISCOVERY | TOURIST_DISCOVERY | MENU_HIGHLIGHT
    """
    VIRAL_ATTENTION    = "viral_attention"
    CONVERSION_ORDER   = "conversion_order"
    LOCAL_DISCOVERY    = "local_discovery"
    TOURIST_DISCOVERY  = "tourist_discovery"
    MENU_HIGHLIGHT     = "menu_highlight"


class PostStatus(str, Enum):
    """
    Approval state machine:
      draft → pending_approval → approved → published
                               → rejected
      published → (archived)
    """
    DRAFT             = "draft"
    PENDING_APPROVAL  = "pending_approval"
    APPROVED          = "approved"
    REJECTED          = "rejected"
    PUBLISHED         = "published"


# ── ContentTopic ───────────────────────────────────────────────────────────────

class ContentTopic(BaseModel):
    """
    Planner output: one planned post intent.

    Output shape:
      { type, topic, target_audience }
    Plus slot, slug, and keyword for downstream use.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    slot: int = Field(ge=0, le=2, description="0=morning, 1=midday, 2=evening")
    type: PostType
    topic: str = Field(description="Short 1-2 sentence topic summary")
    target_audience: str
    slug: str = Field(default="", description="URL-safe slug")
    primary_keyword: str = Field(default="")
    secondary_keywords: list[str] = Field(default_factory=list)
    source_notes: str = Field(default="", description="Why this topic was chosen")
    created_at: str = Field(default="")

    class Config:
        use_enum_values = True


# ── ContentDraft ──────────────────────────────────────────────────────────────

class ContentDraft(BaseModel):
    """
    Generator output: a complete post ready for validation.
    All fields required except where noted.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    topic_id: str = Field(default="")
    version: int = Field(default=1, ge=1)

    # Core content
    title: str
    slug: str
    meta_description: str = Field(max_length=160)
    excerpt: str = Field(max_length=300)
    body_markdown: str = Field(min_length=50)
    cta: str = Field(default="Visit Us Tonight")
    cta_url: str = Field(default="https://www.rawsushibar.com")

    # SEO
    keyword_primary: str = Field(default="")
    keywords_secondary: list[str] = Field(default_factory=list)

    # Image
    image_url: Optional[str] = None
    image_tag: Optional[str] = None  # menu_item | interior | sushi_roll | chef | storefront

    # Metadata
    type: PostType
    target_audience: str
    word_count: int = Field(default=0)

    # Source / audit
    source_notes: str = Field(default="")
    generated_at: str = Field(default="")
    validation_result: Optional[ValidationResult] = None

    class Config:
        use_enum_values = True


# ── ValidationResult ──────────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    """
    Validator output — the gate to the approval queue.

    Rules:
      - hard_valid == False  → FAIL → never enters approval queue
      - quality_score < 50  → FAIL → never enters approval queue
      - Otherwise           → PASS → enters approval queue
    """
    passed: bool = False
    hard_valid: bool = True
    quality_score: float = Field(ge=0.0, le=100.0, default=0.0)

    # Issue lists
    hard_issues: list[str] = Field(default_factory=list)
    quality_issues: list[str] = Field(default_factory=list)

    # Specific flags
    fake_data_detected: bool = False
    culturally_inappropriate: bool = False
    keyword_stuffing: bool = False

    reason: str = Field(default="", description="Short human-readable summary")
    editor_notes: str = Field(default="")
