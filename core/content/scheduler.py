"""
Content Scheduler — creates content generation tasks at scheduled times.
Called from inside the orchestrator's run_cycle().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from db.repository import ControlPlaneDB

from core.content.store_data import BRAND_CONFIG

logger = logging.getLogger("content.scheduler")

# Schedule: 3 slots per day per brand
SCHEDULE = [
    {"slot": "morning", "hour": 8, "content_type": "tourist"},
    {"slot": "noon", "hour": 12, "content_type": "local"},
    {"slot": "evening", "hour": 18, "content_type": "menu"},
]

# Brands to generate content for
ACTIVE_BRANDS = ["bakudan", "raw"]


class ContentScheduler:
    """Time-based content task creation."""

    def __init__(self):
        self._last_check_date: str | None = None

    def check_and_schedule(self, db: ControlPlaneDB) -> list:
        """Check if any content tasks need to be created for today.

        Called every orchestrator cycle (~10s). Uses date + slot
        as idempotency key to avoid duplicate task creation.

        Returns list of created task IDs (empty if nothing new).
        """
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        current_hour = now.hour

        created = []

        for brand in ACTIVE_BRANDS:
            cfg = BRAND_CONFIG.get(brand)
            if not cfg:
                continue

            project_id = cfg.get("project_id", "")

            for slot_def in SCHEDULE:
                slot = slot_def["slot"]
                trigger_hour = slot_def["hour"]
                content_type = slot_def["content_type"]

                # Only trigger if we've reached or passed the scheduled hour
                if current_hour < trigger_hour:
                    continue

                # Check if task already exists for today + brand + slot
                task_key = f"content:{brand}:{today}:{slot}"
                existing = db.list_tasks(status=None, limit=200)
                already_exists = any(
                    t.get("task_type") == "content_generation"
                    and _get_context_field(t, "schedule_key") == task_key
                    for t in existing
                )

                if already_exists:
                    continue

                # Create the content generation task
                task = db.create_task(
                    title=f"[Content] {brand.title()} — {content_type} post ({slot})",
                    assigned_agent_id="content-agent",
                    goal_id="",
                    description=f"Generate a {content_type}-focused blog post for {cfg['brand_name']}. "
                                f"Slot: {slot} ({trigger_hour}:00). Target audience: {content_type}.",
                    task_type="content_generation",
                    priority=2,
                    context_json={
                        "source": "content_scheduler",
                        "brand": brand,
                        "project_id": project_id,
                        "slot": slot,
                        "content_type": content_type,
                        "schedule_date": today,
                        "schedule_key": task_key,
                    },
                )
                created.append(task["id"])
                logger.info("Scheduled content task: %s (%s/%s/%s)", task["id"][:8], brand, slot, content_type)

        return created


def _get_context_field(task: dict, field: str) -> str:
    """Safely extract a field from task context_json."""
    ctx = task.get("context_json", {})
    if isinstance(ctx, str):
        import json
        try:
            ctx = json.loads(ctx)
        except Exception:
            return ""
    return ctx.get(field, "")
