"""
AI-powered social post generator using the Anthropic Claude API.

Uses prompt caching on the system prompt to reduce token costs when
generating multiple posts for the same store in quick succession.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import anthropic

from .models import (
    ContentType,
    Platform,
    PostGoal,
    SocialPost,
    SocialPostStatus,
    StoreProfile,
)

logger = logging.getLogger("social.generator")

# ── Weekly rotation ────────────────────────────────────────────────────────────
# Maps Python weekday integer (Monday=0) → ContentType
_WEEKLY_ROTATION: dict[int, ContentType] = {
    0: ContentType.FRESHNESS_PUSH,   # Monday
    1: ContentType.LOCAL_SEO_POST,   # Tuesday
    2: ContentType.ORDER_CTA_POST,   # Wednesday
    3: ContentType.SOCIAL_PROOF,     # Thursday
    4: ContentType.WEEKEND_VIBE,     # Friday
    5: ContentType.MENU_HIGHLIGHT,   # Saturday
    6: ContentType.REVIEW_BASED,     # Sunday
}


def get_content_type_for_today() -> ContentType:
    """Return the ContentType assigned to today's weekday."""
    weekday = datetime.now(timezone.utc).weekday()
    return _WEEKLY_ROTATION[weekday]


class SocialPostGenerator:
    """Generates social media posts via Claude using store profile context."""

    MODEL = "claude-opus-4-5"
    MAX_TOKENS = 600

    def __init__(self) -> None:
        self._client = anthropic.Anthropic()

    def _build_system_prompt(self, store: StoreProfile) -> str:
        """Build a detailed system prompt embedding the full store context."""
        kw_primary = ", ".join(store.primary_keywords)
        kw_secondary = ", ".join(store.secondary_keywords)
        actions = ", ".join(store.target_actions)

        order_line = (
            f"Online ordering URL: {store.order_url}" if store.order_url else "No online ordering available."
        )
        menu_line = f"Menu URL: {store.menu_url}" if store.menu_url else ""
        location_line = f"Location page: {store.location_url}" if store.location_url else ""

        return f"""You are a social media copywriter for {store.store_name}, a Japanese sushi restaurant in {store.city}, {store.state}.

STORE DETAILS:
- Name: {store.store_name}
- Address: {store.address}
- City: {store.city}, {store.state}
- Phone: {store.phone}
- {order_line}
{menu_line}
{location_line}

BRAND VOICE:
- Tone style: {store.tone_profile.style}
- Reading level: {store.tone_profile.reading_level}
- Emoji usage: {store.tone_profile.emoji_level} (none = no emojis, light = 1-2 per post, moderate = 3-4, heavy = 5+)

SEO KEYWORDS:
- Primary (must use 1-2 naturally): {kw_primary}
- Secondary (use when relevant): {kw_secondary}

TARGET ACTIONS: {actions}

POSTING RULES:
- Always mention {store.city} by name
- Write in a conversational, mobile-first style
- Keep body between 50-150 words
- Never fabricate facts, reviews, or specific prices
- Include a clear, direct call-to-action
- Use natural language — no keyword stuffing
- Match the tone profile exactly
- Output ONLY valid JSON — no markdown fences, no extra commentary"""

    def _build_user_prompt(
        self,
        store: StoreProfile,
        content_type: ContentType,
        goal: PostGoal,
        topic: str | None,
    ) -> str:
        """Build the user-turn prompt specifying the post to generate."""
        topic_line = f"\nFocus topic: {topic}" if topic else ""
        cta_instruction = (
            f"Include the ordering URL in the CTA: {store.order_url}"
            if store.order_url
            else "Use the location URL or menu URL in the CTA."
        )

        return f"""Generate a social media post with the following parameters:

Content type: {content_type.value}
Business goal: {goal.value}{topic_line}

{cta_instruction}

Return ONLY a JSON object with exactly these keys:
{{
  "headline": "Short punchy headline (under 10 words)",
  "body": "Post body text (50-150 words, conversational, includes city name and 1-2 primary keywords naturally)",
  "cta": "Call-to-action sentence with URL",
  "hashtags": ["#tag1", "#tag2", "#tag3"],
  "seo_terms": ["seo term 1", "seo term 2"]
}}

Rules:
- headline: punchy, attention-grabbing, under 10 words
- body: 50-150 words, mention {store.city}, include 1-2 keywords naturally, no fake claims
- cta: one clear action sentence with the appropriate URL
- hashtags: 3-5 relevant hashtags including location tags
- seo_terms: 2-3 keyword phrases from the primary/secondary lists that appear in the body"""

    def generate(
        self,
        store: StoreProfile,
        content_type: ContentType,
        goal: PostGoal,
        topic: str | None = None,
    ) -> SocialPost:
        """Generate a SocialPost for the given store, content type, and goal.

        Uses prompt caching on the system prompt to reduce API costs.

        Args:
            store: The store profile providing context and brand voice.
            content_type: The content category to generate.
            goal: The business objective for the post.
            topic: Optional specific topic or angle to focus on.

        Returns:
            A SocialPost with status=GENERATED and all content fields populated.

        Raises:
            ValueError: If the API response cannot be parsed as valid JSON.
            anthropic.APIError: On API communication failures.
        """
        system_prompt = self._build_system_prompt(store)
        user_prompt = self._build_user_prompt(store, content_type, goal, topic)

        logger.info(
            "Generating post store=%s content_type=%s goal=%s",
            store.store_id,
            content_type.value,
            goal.value,
        )

        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text.strip()

        # Strip markdown code fences if the model adds them despite instructions
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text)
            raw_text = raw_text.strip()

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse generator response as JSON: %s", raw_text[:200])
            raise ValueError(
                f"Generator returned non-JSON response: {raw_text[:200]}"
            ) from exc

        post = SocialPost(
            id=str(uuid.uuid4()),
            store_id=store.store_id,
            platform=store.platforms[0] if store.platforms else Platform.FACEBOOK,
            content_type=content_type,
            goal=goal,
            status=SocialPostStatus.GENERATED,
            headline=data.get("headline", ""),
            body=data.get("body", ""),
            cta=data.get("cta", ""),
            hashtags=data.get("hashtags", []),
            seo_terms=data.get("seo_terms", []),
            created_at=datetime.now(timezone.utc),
        )

        logger.info("Post generated id=%s store=%s", post.id, store.store_id)
        return post


# Lazy import to avoid circular at module level
import re  # noqa: E402  (stdlib, always available)
