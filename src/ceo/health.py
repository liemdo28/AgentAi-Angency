"""
Campaign Health Scorer — computes a health score (0-100) per campaign
based on active tasks, SLA status, and KPI performance.
"""
from __future__ import annotations

import logging
from typing import Optional

from src.tasks.models import Task, TaskStatus
from src.db.repositories.task_repo import TaskRepository
from src.tasks.kpi_store import KPIStore

logger = logging.getLogger(__name__)


class CampaignHealthScorer:
    """Score each campaign's health across all its active tasks."""

    def __init__(
        self,
        task_repo: Optional[TaskRepository] = None,
        kpi_store: Optional[KPIStore] = None,
    ) -> None:
        self._repo = task_repo or TaskRepository()
        self._kpi = kpi_store or KPIStore(self._repo)

    def score_campaign(self, campaign_id: str) -> float:
        """
        Compute a 0-100 health score for a campaign.
        Factors: task completion rate (40%), average score (40%), SLA compliance (20%).
        """
        tasks = self._repo.list_by_campaign(campaign_id)
        if not tasks:
            return 100.0

        # Task completion rate
        done = sum(1 for t in tasks if t.status in (TaskStatus.PASSED, TaskStatus.DONE))
        completion_rate = done / len(tasks)

        # Average score of completed tasks
        scored = [t.score for t in tasks if t.score > 0]
        avg_score = sum(scored) / len(scored) / 100.0 if scored else 1.0

        # SLA compliance (how many active tasks not overdue)
        overdue = self._repo.get_overdue()
        overdue_ids = {v.task_id for v in overdue}
        active = [t for t in tasks if t.is_active]
        sla_rate = 1.0 - (sum(1 for t in active if t.id in overdue_ids) / max(len(active), 1))

        # KPI score
        kpi_scores = [self._kpi.kpi_score_from_task(t) / 100.0 for t in tasks]
        avg_kpi = sum(kpi_scores) / len(kpi_scores) if kpi_scores else 1.0

        health = round(
            (completion_rate * 0.30)
            + (avg_score * 0.30)
            + (sla_rate * 0.20)
            + (avg_kpi * 0.20)
            * 100,
            1,
        )
        return min(100.0, max(0.0, health))

    def score_all_campaigns(self) -> dict[str, float]:
        """Score all campaigns that have active tasks."""
        active_tasks = self._repo.list_active()
        campaign_ids = {t.campaign_id for t in active_tasks if t.campaign_id}
        return {cid: self.score_campaign(cid) for cid in campaign_ids}
