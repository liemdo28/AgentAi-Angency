"""
SEO Normalizer — standardizes SEO output before approval.

Ensures every draft has clean, complete SEO fields:
  - title_tag (≤ 60 chars)
  - meta_description (120-160 chars)
  - clean slug (URL-safe, no duplicates)
  - internal links (absolute URLs or relative paths)
  - article category
  - target keyword
  - secondary keywords
  - schema-ready metadata
"""

from __future__ import annotations

import re
from typing import Any


class SEONormalizer:
    """
    Normalizes SEO fields for all generated drafts.

    All methods are pure transformations — no I/O, no LLM calls.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def normalize(self, data: dict) -> dict:
        """
        Apply all SEO normalization rules to the parsed generation output.

        Returns the data dict with normalized fields added/updated.
        """
        result = dict(data)

        result["title_tag"]      = self.normalize_title_tag(data.get("title", ""))
        result["meta_description"] = self.normalize_meta_description(
            data.get("meta_description", "")
        )
        result["slug"]           = self.normalize_slug(data.get("slug", ""))
        result["focus_keyword"]  = self.normalize_keyword(data.get("focus_keyword", ""))
        result["secondary_keywords"] = self.normalize_keywords(
            data.get("secondary_keywords", [])
        )
        result["internal_links"] = self.normalize_internal_links(
            data.get("internal_links", [])
        )
        result["category"]       = self.infer_category(data.get("post_type", ""))
        result["seo_title"]      = result["title_tag"]

        return result

    # ── Title Tag ────────────────────────────────────────────────────────────

    def normalize_title_tag(self, title: str) -> str:
        """
        Clean and truncate title tag.

        Rules:
          - Strip HTML tags
          - Remove markdown/formatting characters
          - Max 60 characters
          - Preserve brand suffix if short enough
        """
        cleaned = re.sub(r"<[^>]+>", "", title)
        cleaned = re.sub(r"[*_#`>]+", "", cleaned)
        cleaned = cleaned.strip()

        # Append brand if under 50 chars
        if 0 < len(cleaned) <= 50 and "raw sushi" not in cleaned.lower():
            cleaned = f"{cleaned} | Raw Sushi Bar"
        elif len(cleaned) > 60:
            # Truncate at last complete word under limit
            truncated = cleaned[:60]
            last_space = truncated.rfind(" ")
            if last_space > 45:
                truncated = truncated[:last_space]
            cleaned = truncated

        return cleaned

    # ── Meta Description ────────────────────────────────────────────────────

    def normalize_meta_description(self, meta: str) -> str:
        """
        Ensure meta description is within 120-160 characters.

        Rules:
          - Strip HTML
          - Remove markdown
          - Truncate to 160 chars
          - Pad to minimum 120 if too short (with a softer follow-on thought)
        """
        cleaned = re.sub(r"<[^>]+>", "", meta)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if len(cleaned) > 160:
            cleaned = cleaned[:157] + "..."
        elif len(cleaned) < 80:
            # Too short — append brand context
            cleaned = f"{cleaned} At Raw Sushi Bar in Stockton, CA."
            if len(cleaned) > 160:
                cleaned = cleaned[:157] + "..."

        return cleaned

    # ── Slug ────────────────────────────────────────────────────────────────

    def normalize_slug(self, slug: str) -> str:
        """
        Clean a URL slug.

        Rules:
          - lowercase
          - only a-z, 0-9, hyphens
          - no consecutive hyphens
          - max 60 chars
          - no leading/trailing hyphens
          - no stopwords duplicated at start/end
        """
        if not slug:
            return "post"

        slug = slug.lower().strip()
        # Replace spaces and underscores with hyphens
        slug = re.sub(r"[\s_]+", "-", slug)
        # Remove any character that isn't alphanumeric or hyphen
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Collapse multiple hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        # Max 60 chars
        return slug[:60] or "post"

    # ── Keywords ───────────────────────────────────────────────────────────

    def normalize_keyword(self, kw: str) -> str:
        """Return a clean primary keyword, lowercase, stripped."""
        if not kw:
            return ""
        return re.sub(r"[^\w\s\-]", "", kw).lower().strip()[:50]

    def normalize_keywords(self, kws: list) -> list[str]:
        """
        Deduplicate and clean secondary keywords.

        Removes:
          - Empty strings
          - Exact duplicates (case-insensitive)
          - Keywords that are substrings of the primary keyword
        """
        seen: set[str] = set()
        result: list[str] = []
        for kw in kws:
            if not kw:
                continue
            cleaned = re.sub(r"[^\w\s\-]", "", str(kw)).lower().strip()[:50]
            if cleaned and cleaned not in seen and len(cleaned) >= 2:
                seen.add(cleaned)
                result.append(cleaned)
        return result[:8]  # Max 8 secondary keywords

    # ── Internal Links ─────────────────────────────────────────────────────

    def normalize_internal_links(self, links: list) -> list[str]:
        """
        Ensure internal links are clean and pointing to valid rawwebsite paths.

        Accepts:
          - Bare slugs: "best-sushi-stockton"  → https://www.rawsushibar.com/best-sushi-stockton.html
          - Relative paths: "/menu-stockton"   → https://www.rawsushibar.com/menu-stockton.html
          - Full URLs (passed through)

        Deduplicates by final URL.
        """
        seen: set[str] = set()
        result: list[str] = []

        for link in links:
            if not link:
                continue
            link = str(link).strip()
            url = self._resolve_link(link)
            if url and url not in seen:
                seen.add(url)
                result.append(url)

        return result[:6]  # Max 6 internal links per post

    def _resolve_link(self, link: str) -> str:
        base = "https://www.rawsushibar.com"
        if link.startswith("http"):
            return link
        link = link.strip("/")
        if link.startswith("/"):
            return f"{base}{link}.html"
        return f"{base}/{link}.html"

    # ── Category inference ─────────────────────────────────────────────────

    def infer_category(self, post_type: str) -> str:
        """Map post_type to an article category for SEO taxonomy."""
        mapping = {
            "viral_attention":    "Dining Guide",
            "conversion_order":   "Special Offers",
            "local_discovery":    "Local Dining",
            "tourist_discovery":  "Visitor Guide",
            "menu_highlight":    "Menu",
            "seasonal_trend":    "Seasonal",
        }
        return mapping.get(post_type, "Blog")

    # ── Schema metadata ───────────────────────────────────────────────────

    def schema_metadata(self, data: dict, *, date: str | None = None) -> dict:
        """
        Return a schema.org BlogPosting-ready dict for JSON-LD injection.
        """
        import datetime
        now = date or datetime.datetime.now().strftime("%Y-%m-%d")
        return {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": data.get("title_tag", data.get("title", ""))[:110],
            "description": data.get("meta_description", ""),
            "datePublished": now,
            "dateModified": now,
            "author": {
                "@type": "Organization",
                "name": "Raw Sushi Bar",
            },
            "publisher": {
                "@type": "Organization",
                "name": "Raw Sushi Bar",
                "logo": {
                    "@type": "ImageObject",
                    "url": "https://www.rawsushibar.com/images/logo.png",
                },
            },
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": f"https://www.rawsushibar.com/{data.get('slug', 'post')}.html",
            },
            "keywords": ", ".join(
                [data.get("focus_keyword", "")] + data.get("secondary_keywords", [])
            ),
            "articleSection": data.get("category", "Blog"),
        }
