"""
Abstract base class for all social media platform publishers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ..models import PublishLog, SocialPost


class BaseSocialPublisher(ABC):
    """Defines the contract for platform-specific social media publishers."""

    @abstractmethod
    def publish_post(self, post: SocialPost) -> PublishLog:
        """Immediately publish a post to the platform.

        Args:
            post: The fully populated SocialPost to publish.

        Returns:
            A PublishLog recording the outcome of the publish attempt.
        """
        ...

    @abstractmethod
    def schedule_post(self, post: SocialPost, publish_at: datetime) -> PublishLog:
        """Schedule a post for future publication on the platform.

        Args:
            post: The fully populated SocialPost to schedule.
            publish_at: The UTC datetime when the post should go live.

        Returns:
            A PublishLog recording the outcome of the scheduling attempt.
        """
        ...

    @abstractmethod
    def validate_media(self, image_url: str) -> bool:
        """Check whether an image URL is accessible and has a valid media type.

        Args:
            image_url: The public URL of the image to validate.

        Returns:
            True if the image is reachable and has an image content-type.
        """
        ...

    @abstractmethod
    def fetch_post_status(self, external_post_id: str) -> dict:
        """Retrieve the current status of a published post from the platform.

        Args:
            external_post_id: The platform-assigned identifier for the post.

        Returns:
            A dict containing the platform's response fields.
        """
        ...
