"""
SEO Normalizer — standardizes SEO output fields.

Ensures every draft has clean, complete SEO fields before publishing.
No I/O, no LLM calls — pure data transformations.
"""

from __future__ import annotations

import re


class SEONormalizer:
    """
    Normalizes SEO fields for all generated drafts.

    Applied after generation and before validation / publishing.
    """

    def normalize(self, data: dict) -> dict:
        """
        Apply all normalization rules.
        Returns the data dict with cleaned/updated SEO fields.
        """
        result = dict(data)
        result["title"]           = self._clean_title(result.get("title", ""))
        result["slug"]            = self._slug(result.get("slug", result.get("title", "")))
        result["meta_description"] = self._meta_desc(result.get("meta_description", ""))
        result["keyword_primary"] = self._keyword(result.get("keyword_primary", ""))
        result["keywords_secondary"] = self._keywords(result.get("keywords_secondary") or [])
        result["internal_links"]    = self._links(result.get("internal_links") or [])
        return result

    # ── Title ───────────────────────────────────────────────────────────────

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip markdown, truncate to 70 chars."""
        title = re.sub(r"<[^>]+>", "", title)
        title = re.sub(r"[*_#`>]+", "", title).strip()
        return title[:70]

    # ── Slug ───────────────────────────────────────────────────────────────

    @staticmethod
    def _slug(slug: str) -> str:
        """URL-safe slug, max 60 chars."""
        if not slug:
            return "post"
        slug = slug.lower().strip()
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")[:60]
        return slug or "post"

    # ── Meta description ───────────────────────────────────────────────────

    @staticmethod
    def _meta_desc(meta: str) -> str:
        """Normalize meta description to 120-160 chars."""
        meta = re.sub(r"<[^>]+>", "", meta)
        meta = re.sub(r"\s+", " ", meta).strip()
        if len(meta) > 160:
            meta = meta[:157] + "..."
        if 0 < len(meta) < 80:
            meta = f"{meta} At Raw Sushi Bar, Stockton, CA."
            if len(meta) > 160:
                meta = meta[:157] + "..."
        return meta

    # ── Keywords ───────────────────────────────────────────────────────────

    @staticmethod
    def _keyword(kw: str) -> str:
        return re.sub(r"[^\w\s\-]", "", kw).lower().strip()[:50]

    @staticmethod
    def _keywords(kws: list) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for kw in kws:
            if not kw:
                continue
            clean = re.sub(r"[^\w\s\-]", "", str(kw)).lower().strip()[:50]
            if clean and clean not in seen and len(clean) >= 2:
                seen.add(clean)
                result.append(clean)
        return result[:8]

    # ── Internal links ────────────────────────────────────────────────────

    @staticmethod
    def _links(links: list) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        base = "https://www.rawsushibar.com"
        for link in links:
            if not link:
                continue
            link = str(link).strip()
            if link.startswith("http"):
                url = link
            else:
                url = f"{base}/{link.strip('/')}.html"
            if url not in seen:
                seen.add(url)
                result.append(url)
        return result[:6]
