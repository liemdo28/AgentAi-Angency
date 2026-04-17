"""
Content Policy — single source of truth for content rules.

Enforced by:
  - generator.py (at generation time)
  - validator.py (before approval queue entry)

Rules enforced here:
  ✓ Correct brand name at all times
  ✓ No fake business data
  ✓ No culturally inappropriate language
  ✓ No spam tone
  ✓ No exaggerated claims
  ✓ No duplicate topics (7-day window)
  ✓ No unverified delivery / service claims
"""

from __future__ import annotations

import re
from typing import Any


class ContentPolicy:
    """
    Central policy enforcement for all content.

    Phase 1: brand-configured rules.
    Phase 2: DB-backed with per-topic overrides.
    """

    @property
    def config(self) -> dict[str, Any]:
        """Per-brand policy configuration."""
        return {
            "brand_name":     "Raw Sushi Bar",
            "brand_short":    "Raw",
            "website_domain": "rawsushibar.com",
            "city":           "Stockton, CA",

            "known_addresses": [
                "10742 Trinity Parkway, Suite D, Stockton, CA",
                "10742 Trinity Pkwy, Stockton, CA",
            ],
            "verified_phones": [
                "(209) 954-9729",
            ],
            "verified_hours": (
                "Mon-Thu 4:30-8:30PM, "
                "Fri 11:30AM-9PM, "
                "Sat 12-9PM, Sun 12-8PM"
            ),
            "verified_prices": [],
            "delivery_verified":  False,
            "takeout_verified":   True,
            "dine_in_verified":   True,
            "catering_verified":  False,

            "order_url": (
                "https://order.toasttab.com/online/raw-sushi-bistro"
                "-10742-trinity-pkwy-ste-d"
            ),
            "menu_url":   "https://www.rawsushibar.com/menu-stockton.html",
            "location_url": (
                "https://www.google.com/maps/search/?api=1"
                "&query=10742+Trinity+Parkway+Stockton+CA"
            ),

            "duplicate_window_days":    7,
            "title_pattern_window_days": 5,
        }

    # ── Menu items ─────────────────────────────────────────────────────────

    def verified_menu_items(self) -> list[str]:
        """Return the verified menu items list from brand config."""
        try:
            from core.content.store_data import get_brand_config
            cfg = get_brand_config("raw")
            return cfg.get("signature_dishes", [])
        except Exception:
            return [
                "Chef's Omakase",
                "Dragon Roll",
                "Fresh Salmon Sashimi",
                "Yellowtail Jalapeño",
                "Baked Lobster Roll",
                "Tuna Tataki",
            ]

    # ── Offensive language ─────────────────────────────────────────────────

    def detect_offensive_language(self, text: str) -> list[str]:
        """
        Scan text for offensive or culturally inappropriate language.
        Returns a list of flagged phrases.
        """
        flags: list[str] = []

        slur_patterns = [
            r"\bjap(?:ie|o)\b",
            r"\bchin(?:k|o)\b",
        ]
        for pattern in slur_patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                flags.append(f"Potential ethnic slur: '{m.group()}'")

        # Tragedy exploitation
        tragedy = [
            r"(?:earthquake|flood|fire|murder|shooting)\s+(?:here|tonight|today)\s+(?:eat|dine|sushi|visit)",
            r"after\s+(?:wildfire|fire|murder|tragedy)\s+(?:you should|try|visit)",
        ]
        for pattern in tragedy:
            if re.search(pattern, text, re.IGNORECASE):
                flags.append("Tragedy-adjacent language — tone-deaf.")

        return flags

    def check_cultural_sensitivity(self, text: str) -> list[str]:
        """Return cultural tone issues found in text."""
        issues: list[str] = []

        stereotypes = [
            r"\b(?:all|every)\s+japanese\s+(?:people|restaurants)\s+(?:love|hate|eat)",
            r"\bjapanese\s+people\s+(?:love|hate|eat)\s+\w+",
        ]
        for pattern in stereotypes:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(f"Stereotype detected: '{pattern}'")

        # Over-emphasis on "authentic" in exclusionary ways
        if re.search(
            r"(?:authentic|real)\s+(?:japanese|sushi)\s+(?:food|cuisine)\s+(?:only|exclusively)",
            text, re.IGNORECASE
        ):
            issues.append("Ethnic authenticity framing may feel exclusionary.")

        return issues

    # ── Spam / exaggeration ────────────────────────────────────────────────

    def detect_spam_patterns(self, text: str) -> bool:
        """Return True if text contains spam patterns."""
        spam = [
            r"click here to (?:buy|order|get)",
            r"(?:only|just)\s+\$[\d]+",
            r"(?:act now|limited time|offer ends|expires today)",
            r"(?:best|top|#1|voted)\s+(?:ever|in the world)",
        ]
        return any(re.search(p, text, re.IGNORECASE) for p in spam)

    def detect_exaggerated_claims(self, text: str) -> list[str]:
        """Return list of exaggerated claim issues."""
        issues: list[str] = []
        patterns = [
            (r"best\s+(?:sushi|restaurant|food)\s+(?:ever|in\s+stockton)", "Avoid 'best ever' superlatives."),
            (r"the\s+only\s+(?:sushi\s+)?place\s+to", "Avoid 'the only place' claims."),
            (r"guaranteed\s+\w+", "Avoid guaranteed outcomes."),
            (r"you\s+will\s+never\s+\w+", "Avoid absolute negative promises."),
            (r"every\s+(?:dish|bite)\s+is\s+(?:perfect|the\s+best)", "Avoid universal superlatives."),
        ]
        for pattern, msg in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(msg)
        return issues

    # ── Tone ──────────────────────────────────────────────────────────────

    def check_tone(self, text: str) -> list[str]:
        """Return tone violations (excessive caps, exclamation marks, etc.)."""
        issues: list[str] = []

        exclaim = text.count("!")
        if exclaim > 4:
            issues.append(f"Too many exclamation marks ({exclaim}).")

        caps_words = re.findall(r"\b[A-Z]{4,}\b", text)
        if len(caps_words) > 3:
            issues.append(f"Excessive ALL CAPS words: {caps_words}.")

        urgency = len(re.findall(
            r"(?:order now|visit today|call now|hurry|limited)", text, re.IGNORECASE
        ))
        if urgency > 2:
            issues.append("Too many urgency phrases — feels pressuring.")

        return issues
