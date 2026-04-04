"""
Review Management Connector - review-management-mcp

Authentication: Local file system / MCP protocol
API Endpoints:
- Review MCP runs as a subprocess, communicates via files
- reviews/pending_reviews.md  - List of pending reviews
- logs/last-run.txt          - Last check timestamp
- reviews/responses/          - Sent responses
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.unified.connectors.base import (
    BaseConnector,
    ConnectorAction,
    ConnectorResult,
    ConnectorStatus,
    HealthResult,
)

logger = logging.getLogger(__name__)

# Path to review-management-mcp project (relative to Master)
REVIEW_MCP_PATH = Path(r"E:\Project\Master\review-management-mcp")


class ReviewConnector(BaseConnector):
    """Connector for Review Management MCP."""

    project_id = "review-management"
    project_name = "Review Management MCP"
    base_url = ""  # Local file-based
    timeout = 5.0

    def __init__(self):
        super().__init__()
        self._base_path = REVIEW_MCP_PATH

    @property
    def pending_reviews_file(self) -> Path:
        return self._base_path / "reviews" / "pending_reviews.md"

    @property
    def last_run_file(self) -> Path:
        return self._base_path / "logs" / "last-run.txt"

    @property
    def responses_dir(self) -> Path:
        return self._base_path / "reviews" / "responses"

    async def check_health(self) -> HealthResult:
        """Check if Review MCP is installed and recent."""
        start = datetime.now(timezone.utc)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        if not self._base_path.exists():
            return HealthResult(
                status=ConnectorStatus.OFFLINE,
                latency_ms=latency_ms,
                message=f"Review MCP not found at {self._base_path}",
            )

        # Check if pending reviews file exists
        if not self.pending_reviews_file.exists():
            return HealthResult(
                status=ConnectorStatus.WARNING,
                latency_ms=latency_ms,
                message="Pending reviews file not found",
            )

        # Check last run time
        last_run = None
        if self.last_run_file.exists():
            try:
                content = self.last_run_file.read_text().strip()
                last_run = datetime.fromisoformat(content)
                age_minutes = (datetime.now(timezone.utc) - last_run).total_seconds() / 60
                if age_minutes > 60:
                    return HealthResult(
                        status=ConnectorStatus.WARNING,
                        latency_ms=latency_ms,
                        message=f"Last run {int(age_minutes)}m ago - may need refresh",
                        details={"last_run": content},
                    )
            except Exception:
                pass

        return HealthResult(
            status=ConnectorStatus.ONLINE,
            latency_ms=latency_ms,
            message="Review MCP is healthy",
            details={"last_run": last_run.isoformat() if last_run else None},
        )

    async def get_status(self) -> dict:
        """Get current status and metrics."""
        health = await self.check_health()

        status = {
            "project_id": self.project_id,
            "status": health.status.value,
            "latency_ms": health.latency_ms,
            "last_check": health.last_check.isoformat(),
            "metrics": {},
        }

        if health.status != ConnectorStatus.OFFLINE:
            # Parse pending reviews
            pending = self._parse_pending_reviews()
            responses = self._count_responses()

            google_count = sum(1 for p in pending if "Google" in p.get("source", ""))
            yelp_count = sum(1 for p in pending if "Yelp" in p.get("source", ""))

            last_run = None
            if self.last_run_file.exists():
                try:
                    last_run = self.last_run_file.read_text().strip()
                except Exception:
                    pass

            status["metrics"] = {
                "pending_google": google_count,
                "pending_yelp": yelp_count,
                "total_pending": len(pending),
                "responses_sent": responses,
                "last_run": last_run,
            }

        return status

    def _parse_pending_reviews(self) -> list[dict]:
        """Parse pending reviews from markdown file."""
        if not self.pending_reviews_file.exists():
            return []

        try:
            content = self.pending_reviews_file.read_text(encoding="utf-8")
            reviews = []
            current = {}

            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("## "):
                    if current:
                        reviews.append(current)
                    current = {"title": line[3:].strip()}
                elif ": " in line and current:
                    key, _, value = line.partition(": ")
                    current[key.strip().lower().replace(" ", "_")] = value.strip()

            if current:
                reviews.append(current)

            return reviews
        except Exception as e:
            logger.warning(f"Failed to parse pending reviews: {e}")
            return []

    def _count_responses(self) -> int:
        """Count number of response files."""
        if not self.responses_dir.exists():
            return 0
        try:
            return len(list(self.responses_dir.glob("*.md")))
        except Exception:
            return 0

    async def get_available_actions(self) -> list[ConnectorAction]:
        """List available actions for Review MCP."""
        return [
            ConnectorAction(
                id="reviews.refresh",
                name="Check Reviews",
                description="Run MCP to check for new reviews",
                category="sync",
            ),
            ConnectorAction(
                id="reviews.list_pending",
                name="List Pending",
                description="Get list of pending reviews needing response",
                category="sync",
            ),
            ConnectorAction(
                id="reviews.responses",
                name="View Responses",
                description="View recent auto-generated responses",
                category="sync",
            ),
        ]

    async def execute_action(
        self,
        action_id: str,
        payload: Optional[dict] = None,
        job_id: Optional[str] = None,
    ) -> ConnectorResult:
        """Execute a Review MCP action."""
        start = datetime.now(timezone.utc)

        if action_id == "reviews.refresh":
            # Run the MCP check script
            import subprocess

            check_script = self._base_path / "check_reviews.py"
            if not check_script.exists():
                return ConnectorResult(
                    success=False,
                    message="check_reviews.py not found",
                )

            try:
                result = subprocess.run(
                    ["python", str(check_script)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(self._base_path),
                )
                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                if result.returncode == 0:
                    return ConnectorResult(
                        success=True,
                        message="Review check completed",
                        data={"output": result.stdout},
                        duration_ms=duration_ms,
                    )
                else:
                    return ConnectorResult(
                        success=False,
                        message=f"Review check failed: {result.stderr}",
                        error=result.stderr,
                        duration_ms=duration_ms,
                    )
            except subprocess.TimeoutExpired:
                return ConnectorResult(
                    success=False,
                    message="Review check timed out after 30s",
                    error="timeout",
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=str(e),
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "reviews.list_pending":
            pending = self._parse_pending_reviews()
            return ConnectorResult(
                success=True,
                message=f"Found {len(pending)} pending reviews",
                data={"reviews": pending},
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

        elif action_id == "reviews.responses":
            responses = []
            if self.responses_dir.exists():
                for f in sorted(self.responses_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]:
                    responses.append({
                        "file": f.name,
                        "content": f.read_text(encoding="utf-8")[:500],
                    })
            return ConnectorResult(
                success=True,
                message=f"Found {len(responses)} responses",
                data={"responses": responses},
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

        return ConnectorResult(
            success=False,
            message=f"Unknown action: {action_id}",
        )

    async def get_metrics(self) -> dict:
        """Get review metrics."""
        return (await self.get_status()).get("metrics", {})
