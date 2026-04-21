"""
Social media publisher service implementations.

Exposes platform-specific publishers and a factory function.
"""

from __future__ import annotations

from ..models import Platform
from .base_publisher import BaseSocialPublisher
from .facebook_publisher import FacebookPublisher
from .instagram_publisher import InstagramPublisher

__all__ = [
    "BaseSocialPublisher",
    "FacebookPublisher",
    "InstagramPublisher",
    "get_publisher",
]


def get_publisher(platform: Platform) -> BaseSocialPublisher:
    """Factory: return the appropriate publisher for a given platform.

    Args:
        platform: The target Platform enum value.

    Returns:
        A concrete BaseSocialPublisher instance for the platform.

    Raises:
        ValueError: If no publisher is registered for the given platform.
    """
    _registry: dict[Platform, type[BaseSocialPublisher]] = {
        Platform.FACEBOOK: FacebookPublisher,
        Platform.INSTAGRAM: InstagramPublisher,
    }
    cls = _registry.get(platform)
    if cls is None:
        raise ValueError(f"No publisher registered for platform: {platform!r}")
    return cls()
