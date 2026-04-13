"""
PostGenerationService — bridges API requests to CreativeSpecialist for rawwebsite posts.

Handles:
  - Creating the post record (status=generating)
  - Calling CreativeSpecialist with channel metadata
  - Parsing structured JSON output
  - Saving post version
  - Transitioning post status to review_pending
  - Writing audit trail
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = {
    "title", "slug", "excerpt", "body_markdown",
    "seo_title", "seo_description", "focus_keyword",
    "cta_text", "cta_url", "featured_image_prompt", "tags",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compute_agent_score(fields: dict) -> float:
    """Score content completeness (0-100). Each present non-empty field adds points."""
    present = sum(
        1 for f in _REQUIRED_FIELDS
        if fields.get(f) and str(fields[f]).strip()
    )
    score = (present / len(_REQUIRED_FIELDS)) * 100
    # Bonus: body_markdown length
    body = fields.get("body_markdown", "")
    if len(body) > 800:
        score = min(100.0, score + 5.0)
    return round(score, 1)


def _slugify(text: str) -> str:
    """Convert title to URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text[:60].strip("-")


class PostGenerationService:
    """Generates a post via CreativeSpecialist and persists it to the DB."""

    def __init__(self, post_db=None):
        if post_db is None:
            from db.post_repository import PostRepository
            post_db = PostRepository()
        self.post_db = post_db

    def generate(self, params: dict) -> dict:
        """
        Full generation cycle:
          1. Create post (status=generating)
          2. Call CreativeSpecialist with rawwebsite metadata
          3. Parse output → fields
          4. Compute agent_score
          5. Save post_version
          6. Update post status → review_pending
          7. Write audit entries
          8. Return {post, version, status}
        """
        post_id = str(uuid4())
        version_id = str(uuid4())
        channel = params.get("channel", "rawwebsite")
        brand_name = params.get("brand_name", "Raw Sushi Bar")
        now = _now()

        # ── 1. Create post record (status=generating) ──────────────────
        post = self.post_db.create_post(
            {
                "id": post_id,
                "account_id": params.get("account_id"),
                "brand_name": brand_name,
                "channel": channel,
                "campaign_id": params.get("campaign_id"),
                "post_type": params.get("post_type", "blog"),
                "target_audience": params.get("target_audience"),
                "focus_keyword": params.get("focus_keyword"),
                "cta_url": params.get("cta_url"),
                "status": "generating",
                "created_by": "post_generation_service",
                "created_at": now,
                "updated_at": now,
            }
        )

        # ── 2. Log generate_started ────────────────────────────────────
        self.post_db.add_review_action(
            {
                "post_id": post_id,
                "actor": "post_generation_service",
                "actor_type": "ai_agent",
                "action_type": "post_generate_started",
                "from_status": None,
                "to_status": "generating",
                "comment": f"Generating post for goal: {params.get('goal', '')[:200]}",
            }
        )
        self.post_db.add_audit_entry(
            actor="post_generation_service",
            action_type="post_generate_started",
            entity_id=post_id,
            details={"channel": channel, "goal": params.get("goal", "")[:200]},
        )

        # ── 3. Call CreativeSpecialist ─────────────────────────────────
        fields = self._call_specialist(params)

        # ── 4. Compute agent_score ─────────────────────────────────────
        agent_score = _compute_agent_score(fields)

        # ── 5. Ensure slug ─────────────────────────────────────────────
        if not fields.get("slug") and fields.get("title"):
            fields["slug"] = _slugify(fields["title"])

        # ── 6. Save post_version ───────────────────────────────────────
        goal_text = params.get("goal", "")
        version = self.post_db.create_version(
            {
                "id": version_id,
                "post_id": post_id,
                "version_no": 1,
                "generation_prompt": goal_text[:2000],
                "model_provider": "anthropic",
                "model_name": "claude",
                "title": fields.get("title"),
                "excerpt": fields.get("excerpt"),
                "body_markdown": fields.get("body_markdown"),
                "body_html": fields.get("body_html"),
                "cta_text": fields.get("cta_text"),
                "cta_url": fields.get("cta_url") or params.get("cta_url"),
                "seo_title": fields.get("seo_title"),
                "seo_description": fields.get("seo_description"),
                "focus_keyword": fields.get("focus_keyword") or params.get("focus_keyword"),
                "featured_image_prompt": fields.get("featured_image_prompt"),
                "featured_image_url": fields.get("featured_image_url"),
                "agent_score": agent_score,
                "review_status": "pending",
            }
        )

        # ── 7. Update post to review_pending with content fields ───────
        target_status = (
            "review_pending"
            if params.get("require_human_approval", True)
            else "approved"
        )
        self.post_db.update_post_status(
            post_id,
            target_status,
            extra={
                "title": fields.get("title"),
                "slug": fields.get("slug"),
                "excerpt": fields.get("excerpt"),
                "body_markdown": fields.get("body_markdown"),
                "cta_text": fields.get("cta_text"),
                "cta_url": fields.get("cta_url") or params.get("cta_url"),
                "seo_title": fields.get("seo_title"),
                "seo_description": fields.get("seo_description"),
                "focus_keyword": fields.get("focus_keyword") or params.get("focus_keyword"),
            },
        )

        # ── 8. Write completion audit entries ──────────────────────────
        self.post_db.add_review_action(
            {
                "post_id": post_id,
                "post_version_id": version_id,
                "actor": "post_generation_service",
                "actor_type": "ai_agent",
                "action_type": "post_generated",
                "from_status": "generating",
                "to_status": target_status,
                "comment": f"Version 1 generated. Score: {agent_score}",
                "payload": {"agent_score": agent_score, "version_no": 1},
            }
        )
        self.post_db.add_audit_entry(
            actor="post_generation_service",
            action_type="post_generated",
            entity_id=post_id,
            details={
                "version_id": version_id,
                "agent_score": agent_score,
                "channel": channel,
            },
            to_state={"status": target_status},
        )

        # Return full detail for API response
        return {
            "post_id": post_id,
            "post_version_id": version_id,
            "status": target_status,
            "agent_score": agent_score,
            "preview": {
                "title": fields.get("title"),
                "slug": fields.get("slug"),
                "excerpt": fields.get("excerpt"),
                "seo_title": fields.get("seo_title"),
                "seo_description": fields.get("seo_description"),
                "focus_keyword": fields.get("focus_keyword"),
                "cta_text": fields.get("cta_text"),
                "cta_url": fields.get("cta_url"),
                "featured_image_prompt": fields.get("featured_image_prompt"),
                "tags": fields.get("tags", []),
            },
        }

    def regenerate(self, post_id: str, feedback: str) -> dict:
        """
        Regenerate content for an existing post from reviewer feedback.
        Creates a new post_version, increments version_no.
        """
        post = self.post_db.get_post(post_id)
        if not post:
            raise ValueError(f"Post {post_id} not found")

        version_id = str(uuid4())
        now = _now()

        params = {
            "channel": post.get("channel", "rawwebsite"),
            "brand_name": post.get("brand_name", "Raw Sushi Bar"),
            "goal": feedback,
            "post_type": post.get("post_type", "blog"),
            "target_audience": post.get("target_audience"),
            "focus_keyword": post.get("focus_keyword"),
            "cta_url": post.get("cta_url"),
        }
        fields = self._call_specialist(params)
        agent_score = _compute_agent_score(fields)

        next_version_no = self.post_db.get_next_version_no(post_id)
        version = self.post_db.create_version(
            {
                "id": version_id,
                "post_id": post_id,
                "version_no": next_version_no,
                "generation_prompt": feedback[:2000],
                "model_provider": "anthropic",
                "model_name": "claude",
                "title": fields.get("title"),
                "excerpt": fields.get("excerpt"),
                "body_markdown": fields.get("body_markdown"),
                "body_html": fields.get("body_html"),
                "cta_text": fields.get("cta_text"),
                "cta_url": fields.get("cta_url") or post.get("cta_url"),
                "seo_title": fields.get("seo_title"),
                "seo_description": fields.get("seo_description"),
                "focus_keyword": fields.get("focus_keyword") or post.get("focus_keyword"),
                "featured_image_prompt": fields.get("featured_image_prompt"),
                "agent_score": agent_score,
                "review_status": "pending",
            }
        )

        self.post_db.update_post_status(
            post_id,
            "review_pending",
            extra={
                "title": fields.get("title"),
                "slug": fields.get("slug") or _slugify(fields.get("title", "")),
                "excerpt": fields.get("excerpt"),
            },
        )
        self.post_db.add_review_action(
            {
                "post_id": post_id,
                "post_version_id": version_id,
                "actor": "post_generation_service",
                "actor_type": "ai_agent",
                "action_type": "post_regenerated",
                "from_status": post.get("status"),
                "to_status": "review_pending",
                "comment": f"Regenerated v{next_version_no} based on feedback. Score: {agent_score}",
                "payload": {"agent_score": agent_score, "version_no": next_version_no},
            }
        )
        self.post_db.add_audit_entry(
            actor="post_generation_service",
            action_type="post_regenerated",
            entity_id=post_id,
            details={"version_id": version_id, "version_no": next_version_no, "agent_score": agent_score},
        )

        return {
            "post_id": post_id,
            "post_version_id": version_id,
            "version_no": next_version_no,
            "status": "review_pending",
            "agent_score": agent_score,
        }

    def _call_specialist(self, params: dict) -> dict:
        """Call CreativeSpecialist and return parsed field dict."""
        try:
            from src.agents.specialists.creative import CreativeSpecialist
            specialist = CreativeSpecialist()
            state = {
                "task_description": params.get("goal", ""),
                "metadata": {
                    "channel": params.get("channel", "rawwebsite"),
                    "brand_name": params.get("brand_name", "Raw Sushi Bar"),
                    "post_type": params.get("post_type", "blog"),
                    "focus_keyword": params.get("focus_keyword", ""),
                    "cta_url": params.get("cta_url", ""),
                    "tone": params.get("tone", "professional"),
                    "target_audience": params.get("target_audience", ""),
                },
                "policy": {},
                "research_results": {},
            }
            result = specialist.generate(state)
            # For rawwebsite, `generated_outputs` is the parsed JSON dict
            fields = result.get("generated_outputs") or {}
            if isinstance(fields, dict) and fields:
                return fields
            # Fallback: try parsing specialist_output directly
            raw = result.get("specialist_output", "")
            return self._parse_output(raw, params.get("channel", "rawwebsite"))
        except Exception as exc:
            logger.warning("CreativeSpecialist call failed: %s", exc)
            return {}

    @staticmethod
    def _parse_output(raw: str, channel: str) -> dict:
        """Parse specialist output into structured fields."""
        if not raw:
            return {}
        cleaned = raw.strip()
        # Strip markdown fences
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        else:
            brace = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if brace:
                cleaned = brace.group(0)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # For non-rawwebsite channels, extract key fields heuristically
        lines = raw.splitlines()
        title = next(
            (l.lstrip("# ").strip() for l in lines if l.strip() and not l.startswith("#")),
            "Untitled"
        )
        return {"title": title[:70], "body_markdown": raw, "excerpt": raw[:160]}
