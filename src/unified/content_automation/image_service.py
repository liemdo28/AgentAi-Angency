"""
Image Service — attaches an image to each draft.

Phase 1 strategy (no AI image generation):
  Priority order:
    1. Approved real store images (stored in data/approved_images.json)
    2. Approved internal asset library
    3. Curated stock image fallback (URL)

Rules:
  - Image must match post topic
  - No misleading imagery
  - No low-quality generic stock if real store media exists
  - Image tag system for manual selection: menu_item | interior | sushi_roll |
    dining | chef | storefront | event

Phase 2: add AI image generation via DALL-E or Stable Diffusion.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("content_automation.image_service")

APPROVED_IMAGES_PATH = Path("data/approved_images.json")


# ─────────────────────────────────────────────────────────────────────────────
#  ImageService
# ─────────────────────────────────────────────────────────────────────────────

class ImageService:
    """
    Selects and attaches an image to a ContentDraft.

    Phase 1: rule-based selection from approved image library.
    Image tags drive selection; manual override always possible.
    """

    # Map post_type → primary image tag(s)
    POST_TYPE_TAGS = {
        "viral_attention":    ["sushi_roll", "dining", "interior"],
        "conversion_order":   ["menu_item", "sushi_roll", "chef"],
        "local_discovery":    ["interior", "storefront", "dining"],
        "tourist_discovery":  ["storefront", "interior", "dining"],
        "menu_highlight":     ["menu_item", "sushi_roll", "chef"],
        "seasonal_trend":     ["dining", "interior", "event"],
    }

    def __init__(self, brand: str = "raw"):
        self.brand = brand
        self._library: list[dict] = self._load_library()

    # ── Public API ────────────────────────────────────────────────────────────

    def attach_image(self, post_type: str, topic: str, draft_slug: str) -> dict:
        """
        Select the best image for a post and return image metadata.

        Returns:
            {
                "image_asset_id": "...",
                "image_url": "...",
                "image_prompt": "...",
                "image_tag": "...",
                "source": "approved_library" | "stock_fallback",
                "credit": "...",
            }

        Phase 1: image selection is rule-based from approved library.
        Reviewer can override manually before publish.
        """
        tags = self.POST_TYPE_TAGS.get(post_type, ["sushi_roll", "dining"])

        # 1. Try approved library
        image = self._select_from_library(tags, topic, draft_slug)
        if image:
            logger.info(
                "Image attached: id=%s tag=%s source=approved_library",
                image.get("asset_id"), image.get("tag"),
            )
            return image

        # 2. Fall back to stock image
        stock = self._get_stock_fallback(post_type, topic)
        logger.info(
            "No approved image found — using stock fallback: %s",
            stock.get("image_url"),
        )
        return stock

    def list_approved_images(self, tag: str | None = None) -> list[dict]:
        """Return all approved images, optionally filtered by tag."""
        if tag:
            return [img for img in self._library if tag in img.get("tags", [])]
        return self._library

    def get_image_by_id(self, asset_id: str) -> dict | None:
        return next((img for img in self._library if img.get("asset_id") == asset_id), None)

    # ── Library loading ─────────────────────────────────────────────────────

    def _load_library(self) -> list[dict]:
        """Load the approved image library from disk."""
        if not APPROVED_IMAGES_PATH.exists():
            logger.debug("No approved image library found at %s", APPROVED_IMAGES_PATH)
            return self._default_library()

        try:
            data = json.loads(APPROVED_IMAGES_PATH.read_text())
            brand_images = data.get(self.brand, []) + data.get("shared", [])
            return brand_images
        except Exception as exc:
            logger.warning("Could not load approved images: %s — using defaults", exc)
            return self._default_library()

    def _default_library(self) -> list[dict]:
        """
        Minimal fallback library — no real images, just tags + placeholders.
        Reviewers must manually select images before publishing.
        """
        return [
            {
                "asset_id": "stock_dining_generic",
                "image_url": "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=800",
                "image_prompt": (
                    "Elegant Japanese sushi restaurant interior, warm lighting, "
                    " wooden tables, patrons enjoying fresh sushi and sake"
                ),
                "tag": "dining",
                "tags": ["dining", "interior", "atmosphere"],
                "credit": "Unsplash",
                "alt_text": "Raw Sushi Bar dining room",
                "source": "stock_fallback",
            },
            {
                "asset_id": "stock_sushi_roll",
                "image_url": "https://images.unsplash.com/photo-1553621042-f6e147245254?w=800",
                "image_prompt": (
                    "Freshly prepared dragon roll with avocado, eel, and cucumber "
                    "topped with spicy mayo and unagi sauce"
                ),
                "tag": "sushi_roll",
                "tags": ["sushi_roll", "menu_item"],
                "credit": "Unsplash",
                "alt_text": "Fresh dragon roll at Raw Sushi Bar",
                "source": "stock_fallback",
            },
            {
                "asset_id": "stock_chef",
                "image_url": "https://images.unsplash.com/photo-1514191055-f7cedb8a4f2d?w=800",
                "image_prompt": (
                    "Sushi chef carefully plating an omakase course, "
                    "professional Japanese kitchen, immaculate presentation"
                ),
                "tag": "chef",
                "tags": ["chef", "menu_item", "omakase"],
                "credit": "Unsplash",
                "alt_text": "Raw Sushi Bar sushi chef at work",
                "source": "stock_fallback",
            },
            {
                "asset_id": "stock_storefront",
                "image_url": "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800",
                "image_prompt": (
                    "Japanese restaurant storefront at dusk, warm lighting, "
                    "elegant signage, inviting entrance"
                ),
                "tag": "storefront",
                "tags": ["storefront", "exterior"],
                "credit": "Unsplash",
                "alt_text": "Raw Sushi Bar Stockton exterior",
                "source": "stock_fallback",
            },
            {
                "asset_id": "stock_interior",
                "image_url": "https://images.unsplash.com/photo-1559329007-40df8a9355a6?w=800",
                "image_prompt": (
                    "Cozy Japanese restaurant interior, wooden bar counter, "
                    "ambient lighting, modern and traditional elements"
                ),
                "tag": "interior",
                "tags": ["interior", "dining"],
                "credit": "Unsplash",
                "alt_text": "Inside Raw Sushi Bar",
                "source": "stock_fallback",
            },
            {
                "asset_id": "stock_menu_item",
                "image_url": "https://images.unsplash.com/photo-1582450871972-a5f63d77ce2d?w=800",
                "image_prompt": (
                    "Beautiful plate of assorted sashimi: salmon, tuna, "
                    "yellowtail on a dark ceramic plate, garnished with microgreens"
                ),
                "tag": "menu_item",
                "tags": ["menu_item", "sashimi", "sushi_roll"],
                "credit": "Unsplash",
                "alt_text": "Fresh sashimi platter at Raw Sushi Bar",
                "source": "stock_fallback",
            },
        ]

    # ── Selection logic ─────────────────────────────────────────────────────

    def _select_from_library(
        self, tags: list[str], topic: str, draft_slug: str
    ) -> dict | None:
        """
        Select the best image from the approved library matching the given tags.
        Score by tag relevance, then freshness (unused images score higher).
        """
        scored: list[tuple[int, dict]] = []

        for img in self._library:
            img_tags = set(img.get("tags", []))
            tag_matches = sum(1 for t in tags if t in img_tags)
            if tag_matches == 0:
                continue

            # Penalize recently used images (encourage variety)
            score = tag_matches * 10
            last_used = img.get("last_used_at", "")
            if last_used:
                score -= 5  # Slight penalty for recently used

            scored.append((score, img))

        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            selected = scored[0][1]
            # Mark as used
            selected["last_used_at"] = str(__import__("datetime").datetime.now())
            return self._normalize_output(selected)

        return None

    def _get_stock_fallback(self, post_type: str, topic: str) -> dict:
        """Return a suitable stock image fallback."""
        primary_tag = self.POST_TYPE_TAGS.get(post_type, ["dining"])[0]
        defaults = self._default_library()
        for img in defaults:
            if img.get("tag") == primary_tag:
                return self._normalize_output(img)
        return self._normalize_output(defaults[0])

    @staticmethod
    def _normalize_output(img: dict) -> dict:
        """Ensure image dict has all required fields."""
        return {
            "image_asset_id": img.get("asset_id", ""),
            "image_url":      img.get("image_url", ""),
            "image_prompt":   img.get("image_prompt", ""),
            "image_tag":      img.get("tag", ""),
            "source":         img.get("source", "approved_library"),
            "credit":         img.get("credit", ""),
            "alt_text":       img.get("alt_text", ""),
        }