"""
Content Automation API Router — /ca

Endpoints:
  POST  /ca/run                           Run today's daily job (plan → generate → validate → save)
  GET   /ca/queue                         List pending-approval posts
  GET   /ca/queue/stats                   Counts per status
  GET   /ca/posts/{post_id}               Full post detail (content + versions + timeline)
  POST  /ca/posts/{post_id}/approve       Approve a post (then optionally publish immediately)
  POST  /ca/posts/{post_id}/reject        Reject a post
  POST  /ca/posts/{post_id}/revise        Request revision
  POST  /ca/posts/{post_id}/publish       Publish an approved post to RawWebsite

Mounted at /ca in apps/api/main.py.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from src.unified.content_automation.service import ContentAutomationService

logger = logging.getLogger("api.content_automation")
router = APIRouter(tags=["Content Automation"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _svc(brand: str = "raw") -> ContentAutomationService:
    return ContentAutomationService(brand=brand)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Request models ─────────────────────────────────────────────────────────────

class RunJobRequest(BaseModel):
    date_iso: Optional[str] = None      # YYYY-MM-DD; defaults to today UTC
    brand: str = "raw"


class ApprovePostRequest(BaseModel):
    reviewer: str = "admin"
    comment: Optional[str] = None
    publish_now: bool = False          # NO auto-publish in Phase 1 — human must approve first
    schedule_at: Optional[str] = None  # ISO-8601 datetime; sets status=scheduled instead


class RejectPostRequest(BaseModel):
    reviewer: str = "admin"
    reason: str


class RevisePostRequest(BaseModel):
    reviewer: str = "admin"
    feedback: str


class PublishPostRequest(BaseModel):
    reviewer: str = "system"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/run")
def run_daily_job(body: RunJobRequest):
    """
    Trigger today's content automation job.

    Plans 3 posts, generates, validates, and saves to the review queue.
    Does NOT publish — human approval required first.

    Returns a summary of the 3 generated posts.
    """
    svc = _svc(brand=body.brand)
    try:
        result = svc.run_daily_job(date_iso=body.date_iso)
    except Exception as exc:
        logger.exception("run_daily_job failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Daily job failed: {exc}")

    return result


@router.get("/queue")
def get_queue(
    status: Optional[str] = "pending_approval",
    limit: int = 50,
    brand: str = "raw",
):
    """
    List posts in the review queue.

    Default status=pending_approval. Pass status=all to see everything.
    """
    svc = _svc(brand=brand)
    try:
        return svc.get_queue(status=status, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/queue/stats")
def get_queue_stats(brand: str = "raw"):
    """Return counts per status for the content dashboard."""
    svc = _svc(brand=brand)
    try:
        return svc.get_queue_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/posts/{post_id}")
def get_post_detail(post_id: str, brand: str = "raw"):
    """
    Return full post detail: content, all versions, and full review timeline.
    """
    svc = _svc(brand=brand)
    detail = svc.get_post_detail(post_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Post {post_id!r} not found")
    return detail


@router.post("/posts/{post_id}/approve")
def approve_post(post_id: str, body: ApprovePostRequest):
    """
    Approve a post.

    If publish_now=True (default), immediately publishes to RawWebsite via git.
    If publish_now=False, transitions to 'approved' and waits for manual /publish call.
    """
    from src.unified.content_automation.approval_service import ApprovalService

    svc = _svc()
    approval = ApprovalService()

    try:
        # Approve (or schedule)
        approval.approve(
            post_id=post_id,
            reviewer=body.reviewer,
            comment=body.comment or "",
            schedule_at=body.schedule_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Approval failed: {exc}")

    # Optionally publish immediately
    publish_result = None
    if body.publish_now and not body.schedule_at:
        try:
            publish_result = svc.publish_post(post_id=post_id, reviewer=body.reviewer)
        except Exception as exc:
            logger.error("Auto-publish after approval failed for %s: %s", post_id, exc)
            publish_result = {"success": False, "error": str(exc)}

    detail = svc.get_post_detail(post_id)
    return {
        "post_id": post_id,
        "status": detail.get("status") if detail else "approved",
        "approved_by": body.reviewer,
        "comment": body.comment,
        "publish_result": publish_result,
        "post": detail,
    }


@router.post("/posts/{post_id}/reject")
def reject_post(post_id: str, body: RejectPostRequest):
    """Reject a pending-approval post."""
    from src.unified.content_automation.approval_service import ApprovalService

    approval = ApprovalService()
    try:
        post = approval.reject(
            post_id=post_id,
            reviewer=body.reviewer,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Rejection failed: {exc}")

    return {"post_id": post_id, "status": post.get("status"), "rejected_by": body.reviewer}


@router.post("/posts/{post_id}/revise")
def request_revision(post_id: str, body: RevisePostRequest):
    """Request a revision on a pending-approval post."""
    from src.unified.content_automation.approval_service import ApprovalService

    approval = ApprovalService()
    try:
        post = approval.request_revision(
            post_id=post_id,
            reviewer=body.reviewer,
            feedback=body.feedback,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Revision request failed: {exc}")

    return {"post_id": post_id, "status": post.get("status"), "feedback": body.feedback}


@router.post("/posts/{post_id}/publish")
def publish_post(post_id: str, body: PublishPostRequest):
    """
    Manually trigger publishing for an already-approved post.

    Writes blog-{slug}.html to RawWebsite, updates sitemap.xml,
    git commits + pushes to GitHub.
    """
    svc = _svc()
    try:
        result = svc.publish_post(post_id=post_id, reviewer=body.reviewer)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        logger.exception("Publish failed for post %s: %s", post_id, exc)
        raise HTTPException(status_code=500, detail=f"Publish failed: {exc}")

    return result
