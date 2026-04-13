"""
Post Review & Approval API Router.

Mounted at /posts in apps/api/main.py.
All state transitions are validated and logged to both post_review_actions and audit_log.
"""
from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Ensure project root on path (same as main.py)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from db.post_repository import PostRepository

router = APIRouter(tags=["Posts"])


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _repo() -> PostRepository:
    return PostRepository()


def _get_or_404(repo: PostRepository, post_id: str) -> dict:
    post = repo.get_post(post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id!r} not found")
    return post


# State machine: allowed transitions
_VALID_TRANSITIONS: dict[str, list[str]] = {
    "draft":               ["generating"],
    "generating":          ["review_pending", "draft"],
    "review_pending":      ["approved", "rejected", "revision_requested"],
    "revision_requested":  ["generating", "review_pending"],
    "approved":            ["scheduled", "published", "publish_failed"],
    "scheduled":           ["published", "publish_failed", "approved"],
    "rejected":            ["archived"],
    "published":           ["archived"],
    "publish_failed":      ["approved"],
    "archived":            [],
}


def _assert_transition(post: dict, to_status: str) -> None:
    current = post.get("status", "draft")
    allowed = _VALID_TRANSITIONS.get(current, [])
    if to_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition post from '{current}' to '{to_status}'. "
                f"Allowed: {allowed or 'none'}"
            ),
        )


# ── Pydantic request models ────────────────────────────────────────────────────

class GeneratePostRequest(BaseModel):
    account_id: Optional[str] = None
    brand_name: str = "Raw Sushi Bar"
    channel: str = "rawwebsite"
    goal: str
    post_type: str = "blog"  # promo | event | blog | seasonal | landing-content
    campaign_id: Optional[str] = None
    target_audience: Optional[str] = None
    focus_keyword: Optional[str] = None
    cta_url: Optional[str] = None
    tone: Optional[str] = "professional"
    require_human_approval: bool = True


class ApprovePostRequest(BaseModel):
    reviewer: str
    comment: Optional[str] = None
    schedule_at: Optional[str] = None  # ISO-8601; if set → status='scheduled'


class RejectPostRequest(BaseModel):
    reviewer: str
    reason: str


class RevisionRequest(BaseModel):
    reviewer: str
    feedback: str


class RegenerateRequest(BaseModel):
    based_on_version_id: Optional[str] = None
    feedback: str = ""


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/generate")
def generate_post(body: GeneratePostRequest):
    """
    Trigger AI generation for a new post.

    Creates post + version 1 in DB, transitions status to review_pending.
    Returns post_id, post_version_id, status, agent_score, preview fields.
    """
    from src.services.post_generation_service import PostGenerationService

    repo = _repo()
    svc = PostGenerationService(post_db=repo)
    try:
        result = svc.generate(body.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Post generation failed: {exc}")
    return result


@router.get("/review-queue")
def list_review_queue(
    status: Optional[str] = "review_pending",
    channel: Optional[str] = None,
    brand: Optional[str] = None,
    post_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    List posts in the review queue.

    Defaults to status=review_pending. Pass status=all to get all statuses.
    """
    repo = _repo()
    effective_status = None if status == "all" else status
    posts = repo.list_review_queue(
        status=effective_status,
        channel=channel,
        brand=brand,
        post_type=post_type,
        keyword=q,
        limit=limit,
        offset=offset,
    )
    return {"posts": posts, "count": len(posts)}


@router.get("/stats")
def get_post_stats():
    """Returns count of posts awaiting review — used for sidebar badge."""
    repo = _repo()
    return {"pending": repo.count_pending()}


@router.get("/{post_id}")
def get_post(post_id: str):
    """Return full post detail: post record + all versions + review timeline."""
    repo = _repo()
    post = repo.get_post_detail(post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post {post_id!r} not found")
    return post


@router.post("/{post_id}/approve")
def approve_post(post_id: str, body: ApprovePostRequest):
    """
    Approve a post.

    Transitions: review_pending → approved (or scheduled if schedule_at provided).
    Requires body: reviewer, optional comment, optional schedule_at (ISO-8601).
    """
    repo = _repo()
    post = _get_or_404(repo, post_id)
    to_status = "scheduled" if body.schedule_at else "approved"
    _assert_transition(post, to_status)

    extra: dict = {"approved_by": body.reviewer}
    if body.schedule_at:
        extra["scheduled_for"] = body.schedule_at

    repo.update_post_status(post_id, to_status, extra=extra)

    latest = repo.get_post(post_id)
    version_id = latest.get("version_id") if latest else None

    repo.add_review_action(
        {
            "post_id": post_id,
            "post_version_id": version_id,
            "actor": body.reviewer,
            "actor_type": "human_reviewer",
            "action_type": "approve",
            "from_status": post["status"],
            "to_status": to_status,
            "comment": body.comment,
            "payload": {"schedule_at": body.schedule_at},
        }
    )
    repo.add_audit_entry(
        actor=body.reviewer,
        action_type="post_approved",
        entity_id=post_id,
        details={"comment": body.comment, "to_status": to_status},
        from_state={"status": post["status"]},
        to_state={"status": to_status},
    )
    return {"post_id": post_id, "status": to_status, "approved_by": body.reviewer}


@router.post("/{post_id}/reject")
def reject_post(post_id: str, body: RejectPostRequest):
    """
    Reject a post.

    Transitions: review_pending → rejected.
    Requires body: reviewer, reason.
    """
    repo = _repo()
    post = _get_or_404(repo, post_id)
    _assert_transition(post, "rejected")

    repo.update_post_status(post_id, "rejected")
    repo.add_review_action(
        {
            "post_id": post_id,
            "actor": body.reviewer,
            "actor_type": "human_reviewer",
            "action_type": "reject",
            "from_status": post["status"],
            "to_status": "rejected",
            "comment": body.reason,
        }
    )
    repo.add_audit_entry(
        actor=body.reviewer,
        action_type="post_rejected",
        entity_id=post_id,
        details={"reason": body.reason},
        from_state={"status": post["status"]},
        to_state={"status": "rejected"},
    )
    return {"post_id": post_id, "status": "rejected"}


@router.post("/{post_id}/request-revision")
def request_revision(post_id: str, body: RevisionRequest):
    """
    Request a revision on a post.

    Transitions: review_pending → revision_requested.
    Requires body: reviewer, feedback.
    """
    repo = _repo()
    post = _get_or_404(repo, post_id)
    _assert_transition(post, "revision_requested")

    repo.update_post_status(post_id, "revision_requested")
    repo.add_review_action(
        {
            "post_id": post_id,
            "actor": body.reviewer,
            "actor_type": "human_reviewer",
            "action_type": "request_revision",
            "from_status": post["status"],
            "to_status": "revision_requested",
            "comment": body.feedback,
        }
    )
    repo.add_audit_entry(
        actor=body.reviewer,
        action_type="post_revision_requested",
        entity_id=post_id,
        details={"feedback": body.feedback},
        from_state={"status": post["status"]},
        to_state={"status": "revision_requested"},
    )
    return {"post_id": post_id, "status": "revision_requested"}


@router.post("/{post_id}/regenerate")
def regenerate_post(post_id: str, body: RegenerateRequest):
    """
    Regenerate content from reviewer feedback, creating a new post_version.

    Can be called when status is revision_requested or review_pending.
    Transitions back to review_pending after generation.
    """
    repo = _repo()
    post = _get_or_404(repo, post_id)

    from src.services.post_generation_service import PostGenerationService
    svc = PostGenerationService(post_db=repo)
    try:
        result = svc.regenerate(post_id=post_id, feedback=body.feedback)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {exc}")
    return result


@router.post("/{post_id}/publish")
def publish_post(post_id: str):
    """
    Publish an approved post via RawWebsitePublisher.

    Post must be in status 'approved' or 'scheduled'.
    On success: transitions to 'published'.
    On failure: transitions to 'publish_failed'.
    """
    repo = _repo()
    post = _get_or_404(repo, post_id)

    if post.get("status") not in ("approved", "scheduled"):
        raise HTTPException(
            status_code=409,
            detail=f"Post must be approved or scheduled to publish (current: {post.get('status')})",
        )

    repo.update_post_status(post_id, "published")
    repo.add_audit_entry(
        actor="system",
        action_type="post_publish_started",
        entity_id=post_id,
        details={},
    )

    try:
        from src.services.rawwebsite_publisher import RawWebsitePublisher
        publisher = RawWebsitePublisher()
        # Fetch the latest version for publish
        detail = repo.get_post_detail(post_id)
        versions = (detail or {}).get("versions", [])
        latest_version = versions[-1] if versions else {}
        pub_result = publisher.publish(post, latest_version)

        repo.update_post_status(
            post_id,
            "published",
            extra={"published_at": _now()},
        )
        repo.add_review_action(
            {
                "post_id": post_id,
                "actor": "system",
                "actor_type": "system",
                "action_type": "publish",
                "from_status": post["status"],
                "to_status": "published",
                "comment": f"Published via {pub_result.get('mode', 'manual_export')}",
                "payload": pub_result,
            }
        )
        repo.add_audit_entry(
            actor="system",
            action_type="post_published",
            entity_id=post_id,
            details=pub_result,
            from_state={"status": post["status"]},
            to_state={"status": "published"},
        )
        return {"post_id": post_id, "status": "published", "result": pub_result}

    except Exception as exc:
        repo.update_post_status(post_id, "publish_failed")
        repo.add_audit_entry(
            actor="system",
            action_type="post_publish_failed",
            entity_id=post_id,
            details={"error": str(exc)},
        )
        raise HTTPException(status_code=500, detail=f"Publish failed: {exc}")


@router.get("/{post_id}/logs")
def get_post_logs(post_id: str):
    """Return the full audit trail for a post (review actions + audit_log entries)."""
    repo = _repo()
    if not repo.get_post(post_id):
        raise HTTPException(status_code=404, detail=f"Post {post_id!r} not found")
    return {"logs": repo.get_post_logs(post_id)}
