"""
Facebook Graph API publisher for social posts.

Reads FACEBOOK_PAGE_ID and FACEBOOK_ACCESS_TOKEN from the environment.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from ..models import Platform, PublishLog, SocialPost, SocialPostStatus
from .base_publisher import BaseSocialPublisher

logger = logging.getLogger("social.services.facebook")

_GRAPH_BASE = "https://graph.facebook.com/v19.0"


class FacebookPublisher(BaseSocialPublisher):
    """Publishes and schedules posts to a Facebook Page via the Graph API."""

    def __init__(self) -> None:
        self.page_id = os.environ.get("FACEBOOK_PAGE_ID", "")
        self.access_token = os.environ.get("FACEBOOK_ACCESS_TOKEN", "")
        if not self.page_id or not self.access_token:
            logger.warning(
                "FACEBOOK_PAGE_ID or FACEBOOK_ACCESS_TOKEN not set — publish calls will fail."
            )

    def _build_message(self, post: SocialPost) -> str:
        """Compose the full message string from post fields."""
        hashtag_str = " ".join(post.hashtags)
        return f"{post.headline}\n\n{post.body}\n\n{post.cta}\n\n{hashtag_str}"

    def _make_failed_log(
        self,
        post: SocialPost,
        response: requests.Response | None,
        error_msg: str,
    ) -> PublishLog:
        """Create a PublishLog representing a failed publish attempt."""
        resp_json: dict = {}
        if response is not None:
            try:
                resp_json = response.json()
            except Exception:
                resp_json = {"raw": response.text[:500]}
        return PublishLog(
            post_id=post.id,
            platform=Platform.FACEBOOK,
            status="failed",
            external_post_id=None,
            response_json={"error": error_msg, **resp_json},
        )

    def publish_post(self, post: SocialPost) -> PublishLog:
        """Immediately publish a post to the configured Facebook Page.

        Args:
            post: The SocialPost to publish. headline, body, cta, and hashtags
                  are combined into the feed message.

        Returns:
            PublishLog with status='published' on success, 'failed' otherwise.

        Raises:
            requests.HTTPError: On 4xx authentication / authorization errors.
        """
        url = f"{_GRAPH_BASE}/{self.page_id}/feed"
        payload: dict = {
            "message": self._build_message(post),
            "access_token": self.access_token,
        }

        logger.info("Publishing post id=%s to Facebook page=%s", post.id, self.page_id)

        try:
            resp = requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            logger.error("Network error publishing post id=%s: %s", post.id, exc)
            return self._make_failed_log(post, None, str(exc))

        if resp.status_code in (401, 403):
            resp.raise_for_status()

        if not resp.ok:
            logger.error("Facebook API error %d for post id=%s", resp.status_code, post.id)
            return self._make_failed_log(post, resp, f"HTTP {resp.status_code}")

        data = resp.json()
        external_id = data.get("id")
        logger.info("Published to Facebook external_id=%s post_id=%s", external_id, post.id)

        return PublishLog(
            post_id=post.id,
            platform=Platform.FACEBOOK,
            status="published",
            external_post_id=external_id,
            response_json=data,
        )

    def schedule_post(self, post: SocialPost, publish_at: datetime) -> PublishLog:
        """Schedule a post for future publication on Facebook.

        Args:
            post: The SocialPost to schedule.
            publish_at: The datetime when the post should go live (timezone-aware).

        Returns:
            PublishLog with status='scheduled' on success, 'failed' otherwise.

        Raises:
            requests.HTTPError: On 4xx authentication / authorization errors.
        """
        url = f"{_GRAPH_BASE}/{self.page_id}/feed"
        ts = int(publish_at.timestamp())
        payload: dict = {
            "message": self._build_message(post),
            "scheduled_publish_time": ts,
            "published": "false",
            "access_token": self.access_token,
        }

        logger.info(
            "Scheduling post id=%s to Facebook at %s (ts=%d)",
            post.id,
            publish_at.isoformat(),
            ts,
        )

        try:
            resp = requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            logger.error("Network error scheduling post id=%s: %s", post.id, exc)
            return self._make_failed_log(post, None, str(exc))

        if resp.status_code in (401, 403):
            resp.raise_for_status()

        if not resp.ok:
            logger.error("Facebook API error %d scheduling post id=%s", resp.status_code, post.id)
            return self._make_failed_log(post, resp, f"HTTP {resp.status_code}")

        data = resp.json()
        external_id = data.get("id")
        logger.info("Scheduled on Facebook external_id=%s post_id=%s", external_id, post.id)

        return PublishLog(
            post_id=post.id,
            platform=Platform.FACEBOOK,
            status="scheduled",
            external_post_id=external_id,
            response_json=data,
        )

    def validate_media(self, image_url: str) -> bool:
        """Check that an image URL is reachable and has an image content-type.

        Args:
            image_url: The public URL of the image asset to validate.

        Returns:
            True if the URL returns HTTP 200 and an image/* content-type.
        """
        try:
            resp = requests.head(image_url, timeout=10, allow_redirects=True)
            content_type = resp.headers.get("Content-Type", "")
            valid = resp.ok and content_type.startswith("image/")
            logger.debug("validate_media url=%s valid=%s content_type=%s", image_url, valid, content_type)
            return valid
        except requests.RequestException as exc:
            logger.warning("validate_media failed for url=%s: %s", image_url, exc)
            return False

    def fetch_post_status(self, external_post_id: str) -> dict:
        """Retrieve engagement metrics for a published Facebook post.

        Args:
            external_post_id: The Graph API post ID (e.g. '123456_789012').

        Returns:
            A dict with id, message, created_time, likes summary, and
            comments summary fields.
        """
        url = f"{_GRAPH_BASE}/{external_post_id}"
        params = {
            "fields": "id,message,created_time,likes.summary(true),comments.summary(true)",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("fetch_post_status failed for id=%s: %s", external_post_id, exc)
            return {"error": str(exc)}
