"""
Instagram publisher via the Facebook Graph API (Instagram Graph API).

Reads INSTAGRAM_ACCOUNT_ID and FACEBOOK_ACCESS_TOKEN from the environment.
Publishing requires a two-step process: create a media container, then publish it.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import requests

from ..models import Platform, PublishLog, SocialPost
from .base_publisher import BaseSocialPublisher

logger = logging.getLogger("social.services.instagram")

_GRAPH_BASE = "https://graph.facebook.com/v19.0"

# Fallback hero image used when the post has no image_url
_FALLBACK_IMAGE_URL = (
    "https://static.wixstatic.com/media/a8971f_1628bca31c244ee2b1db9119146687d9~mv2.jpg"
    "/v1/fill/w_1080,h_1080,al_c,q_90/sushi.jpg"
)


class InstagramPublisher(BaseSocialPublisher):
    """Publishes posts to an Instagram Business account via the Graph API."""

    def __init__(self) -> None:
        self.ig_account_id = os.environ.get("INSTAGRAM_ACCOUNT_ID", "")
        self.access_token = os.environ.get("FACEBOOK_ACCESS_TOKEN", "")
        if not self.ig_account_id or not self.access_token:
            logger.warning(
                "INSTAGRAM_ACCOUNT_ID or FACEBOOK_ACCESS_TOKEN not set — publish calls will fail."
            )

    def _build_caption(self, post: SocialPost) -> str:
        """Compose the Instagram caption from post fields.

        Format: headline, blank line, body, blank line, cta, blank line,
        hashtags (one per line).
        """
        hashtag_block = "\n".join(post.hashtags)
        return f"{post.headline}\n\n{post.body}\n\n{post.cta}\n\n{hashtag_block}"

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
            platform=Platform.INSTAGRAM,
            status="failed",
            external_post_id=None,
            response_json={"error": error_msg, **resp_json},
        )

    def _create_media_container(self, post: SocialPost) -> str | None:
        """Step 1: Create an Instagram media container.

        Args:
            post: The SocialPost containing caption and optional image_url.

        Returns:
            The creation_id string on success, or None on failure.
        """
        image_url = post.image_url or _FALLBACK_IMAGE_URL
        caption = self._build_caption(post)

        url = f"{_GRAPH_BASE}/{self.ig_account_id}/media"
        payload = {
            "image_url": image_url,
            "caption": caption,
            "access_token": self.access_token,
        }

        logger.debug("Creating IG media container for post id=%s", post.id)

        try:
            resp = requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            logger.error("Network error creating IG container post id=%s: %s", post.id, exc)
            return None

        if resp.status_code in (401, 403):
            resp.raise_for_status()

        if not resp.ok:
            logger.error(
                "IG container creation failed HTTP %d post id=%s: %s",
                resp.status_code,
                post.id,
                resp.text[:200],
            )
            return None

        creation_id = resp.json().get("id")
        logger.debug("IG container created creation_id=%s post_id=%s", creation_id, post.id)
        return creation_id

    def _publish_container(self, creation_id: str, post: SocialPost) -> PublishLog:
        """Step 2: Publish a previously created media container.

        Args:
            creation_id: The container ID returned by _create_media_container.
            post: The source SocialPost for logging.

        Returns:
            A PublishLog reflecting the outcome.
        """
        url = f"{_GRAPH_BASE}/{self.ig_account_id}/media_publish"
        payload = {
            "creation_id": creation_id,
            "access_token": self.access_token,
        }

        logger.debug("Publishing IG container creation_id=%s post_id=%s", creation_id, post.id)

        try:
            resp = requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            logger.error("Network error publishing IG container post id=%s: %s", post.id, exc)
            return self._make_failed_log(post, None, str(exc))

        if resp.status_code in (401, 403):
            resp.raise_for_status()

        if not resp.ok:
            logger.error(
                "IG publish failed HTTP %d post id=%s: %s",
                resp.status_code,
                post.id,
                resp.text[:200],
            )
            return self._make_failed_log(post, resp, f"HTTP {resp.status_code}")

        data = resp.json()
        external_id = data.get("id")
        logger.info("Published to Instagram external_id=%s post_id=%s", external_id, post.id)

        return PublishLog(
            post_id=post.id,
            platform=Platform.INSTAGRAM,
            status="published",
            external_post_id=external_id,
            response_json=data,
        )

    def publish_post(self, post: SocialPost) -> PublishLog:
        """Publish a post to Instagram using the two-step container API.

        Step 1: Create a media container with image_url and caption.
        Step 2: Publish the container to make it live.

        Falls back to the default hero image if post.image_url is None.

        Args:
            post: The SocialPost to publish.

        Returns:
            PublishLog with status='published' on success, 'failed' otherwise.

        Raises:
            requests.HTTPError: On 4xx authentication / authorization errors.
        """
        logger.info("Publishing post id=%s to Instagram account=%s", post.id, self.ig_account_id)

        creation_id = self._create_media_container(post)
        if not creation_id:
            return self._make_failed_log(post, None, "Failed to create media container")

        return self._publish_container(creation_id, post)

    def schedule_post(self, post: SocialPost, publish_at: datetime) -> PublishLog:
        """Schedule an Instagram post for future publication.

        Note: Instagram Graph API scheduled publishing requires the media
        container to be created with a publish_at timestamp (Business accounts).

        Args:
            post: The SocialPost to schedule.
            publish_at: The timezone-aware datetime for publication.

        Returns:
            PublishLog with status='scheduled' on success, 'failed' otherwise.
        """
        image_url = post.image_url or _FALLBACK_IMAGE_URL
        caption = self._build_caption(post)
        ts = int(publish_at.timestamp())

        url = f"{_GRAPH_BASE}/{self.ig_account_id}/media"
        payload = {
            "image_url": image_url,
            "caption": caption,
            "scheduled_publish_time": ts,
            "is_carousel_item": "false",
            "access_token": self.access_token,
        }

        logger.info(
            "Scheduling IG post id=%s at %s (ts=%d)",
            post.id,
            publish_at.isoformat(),
            ts,
        )

        try:
            resp = requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            logger.error("Network error scheduling IG post id=%s: %s", post.id, exc)
            return self._make_failed_log(post, None, str(exc))

        if resp.status_code in (401, 403):
            resp.raise_for_status()

        if not resp.ok:
            logger.error("IG schedule failed HTTP %d post id=%s", resp.status_code, post.id)
            return self._make_failed_log(post, resp, f"HTTP {resp.status_code}")

        data = resp.json()
        external_id = data.get("id")
        logger.info("Scheduled on Instagram external_id=%s post_id=%s", external_id, post.id)

        return PublishLog(
            post_id=post.id,
            platform=Platform.INSTAGRAM,
            status="scheduled",
            external_post_id=external_id,
            response_json=data,
        )

    def validate_media(self, image_url: str) -> bool:
        """Check that an image URL is reachable and has a valid image content-type.

        Args:
            image_url: The public URL of the image to validate.

        Returns:
            True if the URL returns HTTP 200 and an image/* content-type.
        """
        try:
            resp = requests.head(image_url, timeout=10, allow_redirects=True)
            content_type = resp.headers.get("Content-Type", "")
            valid = resp.ok and content_type.startswith("image/")
            logger.debug("validate_media url=%s valid=%s", image_url, valid)
            return valid
        except requests.RequestException as exc:
            logger.warning("validate_media failed for url=%s: %s", image_url, exc)
            return False

    def fetch_post_status(self, external_post_id: str) -> dict:
        """Retrieve metrics and details for a published Instagram post.

        Args:
            external_post_id: The Instagram media ID returned after publishing.

        Returns:
            A dict with id, caption, timestamp, like_count, and comments_count.
        """
        url = f"{_GRAPH_BASE}/{external_post_id}"
        params = {
            "fields": "id,caption,timestamp,like_count,comments_count",
            "access_token": self.access_token,
        }
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("fetch_post_status failed for id=%s: %s", external_post_id, exc)
            return {"error": str(exc)}
