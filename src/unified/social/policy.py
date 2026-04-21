"""
Content policy engine for social media posts.

Hard checks block the post immediately (score 0, passed=False).
Soft checks accumulate points toward a 0-100 score; posts need >= 60 to pass.
"""

from __future__ import annotations

import logging
import re

from .models import ContentType, SocialPolicyResult, StoreProfile

logger = logging.getLogger("social.policy")

# ── Blocked terms (hate speech / slurs) ───────────────────────────────────────
# Kept as compiled patterns for performance. Extend as needed.
_BLOCKED_TERMS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bn[i1]gg[ae]r\b",
        r"\bf[a@]gg[o0]t\b",
        r"\bch[i1]nk\b",
        r"\bsp[i1]c\b",
        r"\bk[i1]ke\b",
        r"\bwetback\b",
        r"\bcr[a@]cker\b",
        r"\btr[a@]nny\b",
        r"\bretard(ed)?\b",
        r"\bcoon\b",
        r"\bgook\b",
        r"\bslant[-\s]?eye\b",
        r"\bjap\b",
        r"\brag[-\s]?head\b",
        r"\bsand[-\s]?n[i1]gg[ae]r\b",
        r"\bwhite[-\s]?trash\b",
        r"\bh[o0]e\b",
        r"\bslut\b",
        r"\bwh[o0]re\b",
    ]
]

_DECEPTIVE_HEALTH_RE = re.compile(
    r"(?:cure[sd]?|prevent[s]?|treat[s]?)\s+(?:cancer|disease|illness|diabetes)",
    re.IGNORECASE,
)

_ILLEGAL_DRUG_RE = re.compile(
    r"\b(?:weed|marijuana|cannabis|cocaine|drug)\b",
    re.IGNORECASE,
)

_VIOLENT_LANGUAGE_RE = re.compile(
    r"\b(?:kill|murder|shoot|bomb|attack)\b(?!\s+(?:it|the vibe|the look))",
    re.IGNORECASE,
)

# Soft check patterns
_CTA_RE = re.compile(r"(?:order|visit|call|reserve|check|try|book)\b", re.IGNORECASE)
_ALL_CAPS_RE = re.compile(r"(?:[A-Z]{2,}\s+){3,}[A-Z]{2,}")
_FAKE_CLAIMS_RE = re.compile(
    r"\b(?:best in the world|only place|guaranteed)\b",
    re.IGNORECASE,
)


class SocialContentPolicy:
    """Validates social post body text against brand safety and quality rules."""

    # Minimum score for a post to be considered passing
    PASS_THRESHOLD = 60

    def validate(
        self,
        post_body: str,
        store: StoreProfile,
        content_type: ContentType,
    ) -> SocialPolicyResult:
        """Run all policy checks against a post body.

        Hard failures immediately block the post with score=0.
        Soft checks accumulate up to 100 points.

        Args:
            post_body: The raw text content of the post (headline + body + cta).
            store: The store profile for context (city, keywords, etc.).
            content_type: The content category for this post.

        Returns:
            SocialPolicyResult with passed, score, per-check results, warnings,
            and an optional block_reason.
        """
        checks: dict[str, bool] = {}
        warnings: list[str] = []
        block_reason: str | None = None

        # ── Hard checks ───────────────────────────────────────────────────────

        # 1. Blocked terms
        hate_hit = next(
            (p.pattern for p in _BLOCKED_TERMS_PATTERNS if p.search(post_body)),
            None,
        )
        if hate_hit:
            block_reason = "Post contains a blocked term (hate speech / slur)."
            logger.warning("Policy HARD FAIL [blocked_term] store=%s", store.store_id)
            return SocialPolicyResult(
                passed=False,
                score=0,
                checks={"blocked_terms": False},
                warnings=[block_reason],
                block_reason=block_reason,
            )
        checks["blocked_terms"] = True

        # 2. Deceptive health claims
        if _DECEPTIVE_HEALTH_RE.search(post_body):
            block_reason = "Post contains deceptive health claims."
            logger.warning("Policy HARD FAIL [health_claim] store=%s", store.store_id)
            return SocialPolicyResult(
                passed=False,
                score=0,
                checks={**checks, "no_health_claims": False},
                warnings=[block_reason],
                block_reason=block_reason,
            )
        checks["no_health_claims"] = True

        # 3. Illegal / drug promotion
        if _ILLEGAL_DRUG_RE.search(post_body):
            block_reason = "Post contains illegal or drug-related content."
            logger.warning("Policy HARD FAIL [drug_promo] store=%s", store.store_id)
            return SocialPolicyResult(
                passed=False,
                score=0,
                checks={**checks, "no_drug_promo": False},
                warnings=[block_reason],
                block_reason=block_reason,
            )
        checks["no_drug_promo"] = True

        # 4. Violent language
        if _VIOLENT_LANGUAGE_RE.search(post_body):
            block_reason = "Post contains violent language."
            logger.warning("Policy HARD FAIL [violent_lang] store=%s", store.store_id)
            return SocialPolicyResult(
                passed=False,
                score=0,
                checks={**checks, "no_violent_language": False},
                warnings=[block_reason],
                block_reason=block_reason,
            )
        checks["no_violent_language"] = True

        # ── Soft checks (scoring) ──────────────────────────────────────────────
        score = 0

        # has_location: +20
        city_lower = store.city.lower()
        body_lower = post_body.lower()
        has_location = city_lower in body_lower
        checks["has_location"] = has_location
        if has_location:
            score += 20
        else:
            warnings.append(f"Post does not mention the city '{store.city}'.")

        # has_primary_keyword: +20
        has_primary_kw = any(kw.lower() in body_lower for kw in store.primary_keywords)
        checks["has_primary_keyword"] = has_primary_kw
        if has_primary_kw:
            score += 20
        else:
            warnings.append("Post does not include any primary SEO keyword.")

        # has_cta: +15
        has_cta = bool(_CTA_RE.search(post_body))
        checks["has_cta"] = has_cta
        if has_cta:
            score += 15
        else:
            warnings.append("Post lacks a clear call-to-action verb.")

        # has_readable_length: +10 (50–280 chars for social)
        body_len = len(post_body)
        has_readable_length = 50 <= body_len <= 280
        checks["has_readable_length"] = has_readable_length
        if has_readable_length:
            score += 10
        else:
            warnings.append(
                f"Post length ({body_len} chars) is outside the 50-280 char sweet spot."
            )

        # brand_tone_ok: +15 (no 4+ ALL CAPS word runs, not >3 exclamation marks)
        caps_ok = not bool(_ALL_CAPS_RE.search(post_body))
        excl_ok = post_body.count("!") <= 3
        brand_tone_ok = caps_ok and excl_ok
        checks["brand_tone_ok"] = brand_tone_ok
        if brand_tone_ok:
            score += 15
        else:
            if not caps_ok:
                warnings.append("Post contains ALL-CAPS word stretches (>= 4 words).")
            if not excl_ok:
                warnings.append("Post uses more than 3 exclamation marks.")

        # no_keyword_stuffing: +10 (same keyword not >3x)
        kw_stuffed = False
        for kw in store.primary_keywords + store.secondary_keywords:
            count = body_lower.count(kw.lower())
            if count > 3:
                kw_stuffed = True
                warnings.append(f"Keyword '{kw}' appears {count} times (max 3).")
                break
        checks["no_keyword_stuffing"] = not kw_stuffed
        if not kw_stuffed:
            score += 10

        # no_fake_claims: +10
        has_fake = bool(_FAKE_CLAIMS_RE.search(post_body))
        checks["no_fake_claims"] = not has_fake
        if not has_fake:
            score += 10
        else:
            warnings.append("Post contains unverifiable superlative claims.")

        # Cap score at 100
        score = min(score, 100)
        passed = score >= self.PASS_THRESHOLD

        logger.info(
            "Policy check store=%s content_type=%s score=%d passed=%s",
            store.store_id,
            content_type.value,
            score,
            passed,
        )

        return SocialPolicyResult(
            passed=passed,
            score=score,
            checks=checks,
            warnings=warnings,
            block_reason=None,
        )
