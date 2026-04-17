"""
Content Automation — Phase 1 Core (src/unified/content/)

Orchestrates: plan → generate → validate → approve → publish

Architecture:
  AgentAi-Angency = orchestration + content engine
  RawWebsite      = static publishing target

Rules:
  ✗ NO content generated inside rawwebsite
  ✗ NO auto-publish without approval
  ✗ NO ad-hoc HTML pages
  ✓ Content generated in Agency, stored in DB, published after approval
"""

from .models import PostType, PostStatus, ContentTopic, ContentDraft, ValidationResult
from .planner import ContentPlanner
from .generator import ContentGenerator
from .validator import ContentValidator
from .publisher import ContentPublisher
from .policy import ContentPolicy
from .service import ContentService

__all__ = [
    "PostType", "PostStatus",
    "ContentTopic", "ContentDraft", "ValidationResult",
    "ContentPlanner", "ContentGenerator", "ContentValidator",
    "ContentPublisher", "ContentPolicy", "ContentService",
]