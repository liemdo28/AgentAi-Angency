"""
Social media automation module for the AgentAI unified pipeline.

Provides post generation, content policy validation, scheduling, and
multi-platform publishing for Facebook and Instagram.

Public API:
    SocialService        — main orchestrator
    StoreProfile         — store location and brand configuration
    SocialPost           — post lifecycle model
    SocialPostStatus     — post status enum
    SocialPolicyResult   — policy check result model
"""

from __future__ import annotations

from .models import (
    ApprovalMode,
    ContentType,
    Platform,
    PostGoal,
    PublishLog,
    SocialPolicyResult,
    SocialPost,
    SocialPostStatus,
    StoreProfile,
    ToneProfile,
    WeeklyRotation,
)
from .policy import SocialContentPolicy
from .generator import SocialPostGenerator
from .scheduler import SocialScheduler
from .service import SocialService
from .store_profiles import STORE_PROFILES, get_active_stores, get_store

__all__ = [
    # Main service
    "SocialService",
    # Models
    "StoreProfile",
    "SocialPost",
    "SocialPostStatus",
    "SocialPolicyResult",
    "PublishLog",
    "ToneProfile",
    "WeeklyRotation",
    # Enums
    "Platform",
    "PostGoal",
    "ContentType",
    "ApprovalMode",
    # Sub-services
    "SocialContentPolicy",
    "SocialPostGenerator",
    "SocialScheduler",
    # Store helpers
    "STORE_PROFILES",
    "get_store",
    "get_active_stores",
]
