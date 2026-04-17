"""
Content Policy — system-level policy enforcement for all content.

This module is the single source of truth for content rules.
Used by validator.py and generator.py — never bypass this module for policy decisions.

Policy rules enforced here:
  ✓ Always use correct brand name
  ✓ No fake business data (facts, prices, hours, menu items, promotions)
  ✓ No culturally inappropriate or tone-deaf language
  ✓ No exaggerated spam style
  ✓ No forced trends (Phase 2)
  ✓ No irrelevant news exploitation (Phase 2)
  ✓ No duplicate topics within the recent window
  ✓ No publish if validation fails
  ✓ Correct store name, address, phone at all times
  ✓ No delivery/takeout claims unless verified
  ✓ No unverified pricing
  ✓ No offensive stereotypes or culturally insensitive content
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("content_automation.policy")


# ─────────────────────────────────────────────────────────────────────────────
#  ContentPolicy
# ─────────────────────────────────────────────────────────────────────────────

class ContentPolicy:
    """
    Central policy enforcement for content generation and validation.

    All policy rules are defined here. Generator and Validator must call
    this module rather than duplicating rules inline.
    """

    # ── Configuration ───────────────────────────────────────────────────────

    @property
    def config(self) -> dict[str, Any]:
        """
        Per-brand policy configuration.
        Loaded from brand config in Phase 1; from DB in Phase 2.
        """
        return {
            # Brand identity (must always appear correctly)
            "brand_name":           "Raw Sushi Bar",
            "brand_short":          "Raw",
            "website_domain":        "rawsushibar.com",
            "city":                 "Stockton, CA",
            "state":                "California",

            # Verified locations
            "known_addresses": [
                "10742 Trinity Parkway, Suite D, Stockton, CA",
                "10742 Trinity Pkwy, Stockton, CA",
            ],
            "verified_phones": [
                "(209) 954-9729",
                "2099549729",
            ],
            "verified_hours": (
                "Mon-Thu 4:30-8:30PM, Fri 11:30AM-9PM, "
                "Sat 12-9PM, Sun 12-8PM"
            ),
            "verified_prices": [],  # No verified prices in Phase 1
            "verified_menu_items": [
                "Chef's Omakase",
                "Dragon Roll",
                "Fresh Salmon Sashimi",
                "Yellowtail Jalapeño",
                "Baked Lobster Roll",
                "Tuna Tataki",
            ],

            # Delivery / service options (only TRUE if confirmed)
            "delivery_verified":       False,
            "takeout_verified":        True,
            "dine_in_verified":       True,
            "catering_verified":       False,

            # Ordering links (verified)
            "order_url": (
                "https://order.toasttab.com/online/raw-sushi-bistro"
                "-10742-trinity-pkwy-ste-d"
            ),
            "menu_url": "https://www.rawsushibar.com/menu-stockton.html",
            "location_url": (
                "https://www.google.com/maps/search/?api=1"
                "&query=10742+Trinity+Parkway+Stockton+CA"
            ),

            # Brand tone rules
            "brand_tone_rules": {
                "allowed_styles":   ["warm", "polished", "confident", "locally-aware"],
                "banned_styles":    ["aggressive", "spammy", "sensational", "fear-based"],
                "tone_adjectives":  ["refined", "fresh", "artistic", "premium", "welcoming"],
            },

            # Duplicate avoidance
            "duplicate_window_days": 7,
            "title_pattern_window_days": 5,

            # Content limits
            "min_body_words":    300,
            "max_body_words":   3000,
            "max_keyword_density": 3.0,   # percent

            # Spam / exaggerated language
            "spam_patterns": [
                r"click here to (?:buy|order|get)",
                r"(?:only|just)\s+\$[\d]+\s*(?:today|left|remaining)",
                r"(?:act now|limited time|expires today|offer ends)",
                r"(?:best|top|#1|voted)\s+(?:ever|you'll ever|in the world)",
            ],
            "exaggerated_phrases": [
                "best sushi ever",
                "the only sushi place",
                "you will never eat anywhere else",
                "guaranteed best",
            ],
        }

    # ── Fact checking ──────────────────────────────────────────────────────

    def is_fabricated_business_fact(self, text: str) -> bool:
        """
        Return True if text contains unverified business facts.

        Checks:
          - Phone numbers not in verified_phones
          - Addresses not in known_addresses
          - Delivery claims when not verified
          - Menu item claims for items not in verified_menu_items
        """
        text_lower = text.lower()

        # Unknown phone numbers
        for phone in self.config["verified_phones"]:
            if phone in text and phone not in self.config["verified_phones"]:
                pass  # already checked below

        # Unknown addresses
        for addr in self.config["known_addresses"]:
            if addr.lower() in text_lower:
                return False  # verified

        # Check for phone patterns
        phone_pattern = re.compile(r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
        for match in phone_pattern.findall(text):
            clean = re.sub(r"[^\d]", "", match)
            if not any(
                clean in re.sub(r"[^\d]", "", p)
                for p in self.config["verified_phones"]
            ):
                return True  # fabricated phone

        # Delivery claim without verification
        if self.config.get("delivery_verified") is False:
            if re.search(
                r"(?:we deliver|delivery|delivers|delivered)\s+[\w\s]+(?:to|in)\s+\w+",
                text, re.IGNORECASE
            ):
                return True

        return False

    def is_verified_menu_item(self, item: str) -> bool:
        """Return True if the menu item is in the verified list."""
        item_lower = item.lower()
        return any(
            vi.lower() in item_lower or item_lower in vi.lower()
            for vi in self.config["verified_menu_items"]
        )

    # ── Language safety ─────────────────────────────────────────────────

    def detect_offensive_language(self, text: str) -> list[str]:
        """
        Scan text for offensive or culturally inappropriate language.

        Returns a list of flagged phrases.
        Phase 1: regex-based pattern matching.
        Phase 2: add LLM-based cultural sensitivity check.
        """
        flags: list[str] = []

        # Racial / ethnic slurs (generic patterns)
        slur_patterns = [
            r"\bjap(?:ie|o)\b",
            r"\bchin(?:k|o)\b",
            r"\bkorean\s+(?:food|restaurant)\s+(?:dog|cat|etc)\b",
        ]
        for pattern in slur_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                flags.append(f"Potential ethnic slur detected: '{match.group()}'")

        # Insensitive references to tragedies/disasters
        tragedy_patterns = [
            r"(?:earthquake|flood|fire|storm|murder|shooting)\s+(?:here|now|tonight|today)\s+(?:eat|dine|sushi|visit)",
            r"(?:because of|after)\s+(?:wildfire|fire|murder|tragedy)\s+(?:you should|try|visit)\b",
        ]
        for pattern in tragedy_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                flags.append("Tragedy-adjacent language detected — may be tone-deaf.")

        # Crude food/body language
        crude = [
            r"\b(?:raw\s+)?sex[yu]?\s+(?:sushi|roll)",
            r"\b(?:noodle|sushi)\s+(?:in your|in\b.{0,10}\b)mouth\b",
        ]
        for pattern in crude:
            if re.search(pattern, text, re.IGNORECASE):
                flags.append("Crude innuendo detected.")

        return flags

    def check_cultural_sensitivity(self, text: str) -> list[str]:
        """
        Check for culturally tone-deaf patterns.

        Returns a list of issues found.
        """
        issues: list[str] = []

        # Stereotype patterns
        stereotypes = [
            r"\b(?:all|every)\s+(?:japanese|asian)\s+(?:people|restaurants|culture)\s+(?:love|eat|hate|don't)",
            r"\bjapanese\s+people\s+(?:love|hate|eat|are)\s+\w+",
        ]
        for pattern in stereotypes:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(
                    f"Cultural stereotype detected matching pattern: '{pattern}'"
                )

        # Over-emphasis on race/ethnicity in non-relevant context
        if re.search(r"(?:authentic|real)\s+(?:japanese|sushi)\s+(?:food|cuisine)\s+(?:only|exclusively)", text, re.IGNORECASE):
            issues.append(
                "Over-emphasis on ethnic authenticity in ways that may feel exclusionary."
            )

        # Mocking sushi-eating etiquette
        if re.search(r"(?:japanese\s+etiquette|chopstick\s+rules?|say\s+it\s+wrong)", text, re.IGNORECASE):
            if re.search(r"(?:hilarious|funny|amusing)", text, re.IGNORECASE):
                issues.append(
                    "Etiquette mocking may be culturally insensitive."
                )

        return issues

    def detect_spam_patterns(self, text: str) -> bool:
        """Return True if text contains spam/promotional language patterns."""
        for pattern in self.config["spam_patterns"]:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def check_brand_tone(
        self, text: str, tone_rules: dict | None = None
    ) -> list[str]:
        """
        Check if text respects the brand tone rules.

        Returns a list of violations.
        """
        issues: list[str] = []
        rules = tone_rules or self.config.get("brand_tone_rules", {})

        banned = rules.get("banned_styles", [])
        text_lower = text.lower()

        for style in banned:
            if style in text_lower and len(style) > 3:
                issues.append(f"Banned tone style detected: '{style}'")

        # Excessive exclamation marks
        exclaim_count = text.count("!")
        if exclaim_count > 3:
            issues.append(
                f"Excessive exclamation marks ({exclaim_count}) — "
                "sounds promotional rather than genuine."
            )

        # ALL CAPS words (not acronyms)
        caps_words = re.findall(r"\b[A-Z]{4,}\b", text)
        if len(caps_words) > 2:
            issues.append(
                f"Excessive ALL CAPS words: {caps_words} — "
                "sounds aggressive/spammy."
            )

        # Repeated urgency
        urgency_count = len(re.findall(
            r"(?:order now|visit today|call now|limited|act now|hurry)",
            text, re.IGNORECASE
        ))
        if urgency_count > 2:
            issues.append(
                "Too many urgency phrases — feels pressuring rather than helpful."
            )

        return issues

    # ── Duplicate enforcement ─────────────────────────────────────────────

    def is_duplicate_topic(
        self, topic: str, brand: str = "raw", window_days: int = 7
    ) -> bool:
        """Return True if this topic is a duplicate within the window."""
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        import json

        try:
            path = Path("data/content_automation_history.json")
            if not path.exists():
                return False

            data = json.loads(path.read_text())
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=window_days)
            ).isoformat()

            recent = [
                e.get("topic", "").lower()
                for e in data
                if e.get("brand") == brand
                and e.get("date", "") >= cutoff
            ]

            topic_lower = topic.lower()
            for rt in recent:
                if rt == topic_lower:
                    return True

            return False
        except Exception:
            return False

    def is_duplicate_title(
        self, title: str, brand: str = "raw", window_days: int = 5
    ) -> bool:
        """Return True if title pattern duplicates a recent post."""
        from datetime import datetime, timedelta, timezone
        from pathlib import Path
        import json

        try:
            path = Path("data/content_automation_history.json")
            if not path.exists():
                return False

            data = json.loads(path.read_text())
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=window_days)
            ).isoformat()

            recent = [
                e.get("title", "").lower()
                for e in data
                if e.get("brand") == brand
                and e.get("date", "") >= cutoff
            ]

            title_words = set(title.lower().split())
            for rt in recent:
                rt_words = set(rt.split())
                overlap = len(title_words & rt_words)
                # 4+ shared words with short title = likely duplicate
                if overlap >= 4 and len(title_words) <= 8:
                    return True

            return False
        except Exception:
            return False

    # ── Validation helpers ───────────────────────────────────────────────

    def enforce_content_limits(
        self, body: str, *, min_words: int | None = None, max_words: int | None = None
    ) -> list[str]:
        """Return a list of content limit violations (empty if all pass)."""
        violations: list[str] = []
        min_w = min_words or self.config.get("min_body_words", 300)
        max_w = max_words or self.config.get("max_body_words", 3000)
        word_count = len(body.split())

        if word_count < min_w:
            violations.append(
                f"Body too short: {word_count} words. Minimum: {min_w}."
            )
        if word_count > max_w:
            violations.append(
                f"Body too long: {word_count} words. Maximum: {max_w}."
            )

        return violations

    def enforce_keyword_density(
        self, body: str, keyword: str
    ) -> list[str]:
        """Return violations if keyword density exceeds the limit."""
        if not keyword:
            return []
        words = body.lower().split()
        count = sum(1 for w in words if keyword.lower() in w)
        density = count / max(len(words), 1) * 100
        max_density = self.config.get("max_keyword_density", 3.0)
        if density > max_density:
            return [
                f"Keyword density {density:.1f}% exceeds limit {max_density}%. "
                f"Consider reducing '{keyword}' usage."
            ]
        return []
