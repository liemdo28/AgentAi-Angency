"""
CEO Brain — Layer 1 orchestrator.

Wraps the existing LangGraph AgencySupervisor with agency-wide
goal interpretation, task creation, monitoring, and intervention logic.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.ceo.prompts import CEO_SYSTEM_PROMPT, CEO_DECISION_PROMPT
from src.ceo.decisions import CEODecision, CEODecisionEngine
from src.ceo.health import CampaignHealthScorer
from src.agents.supervisor import AgencySupervisor
from src.tasks.models import Task, TaskStatus, now_iso
from src.db.repositories.task_repo import TaskRepository
from src.db.connection import init_db

logger = logging.getLogger(__name__)


class CEOBrain:
    """
    Layer 1: CEO Brain — the agency-wide orchestrator.

    Three operational modes:
    - CREATE_TASK : interpret a goal, create tasks, kick off workflow
    - MONITOR     : scan active tasks, check SLA/KPI/health
    - INTERVENE  : handle escalations, SLA breaches, KPI misses
    """

    def __init__(self) -> None:
        # Ensure DB schema exists
        init_db()

        self._supervisor = AgencySupervisor()
        self._task_repo = TaskRepository()
        self._decision_engine = CEODecisionEngine(self._task_repo)
        self._health_scorer = CampaignHealthScorer(self._task_repo)

    # ── Main entry points ──────────────────────────────────────────────

    def run(self, goal: str, *, mode: str = "CREATE_TASK") -> dict[str, Any]:
        """
        Run the CEO Brain in the specified mode.

        Parameters
        ----------
        goal : Natural-language goal from the operator
        mode : CREATE_TASK | MONITOR | INTERVENE

        Returns
        -------
        dict with keys: action, tasks_affected, decisions, summary
        """
        if mode == "CREATE_TASK":
            return self._run_create_task(goal)
        elif mode == "MONITOR":
            return self._run_monitor()
        elif mode == "INTERVENE":
            return self._run_intervene()
        else:
            return {"action": "unknown_mode", "error": f"Unknown mode: {mode}"}

    # ── CREATE_TASK ────────────────────────────────────────────────────

    def _run_create_task(self, goal: str) -> dict[str, Any]:
        """Interpret goal → create Task in DB → run LangGraph."""
        from src.llm import get_llm
        from src.utils.json_utils import extract_first_json_object

        llm = get_llm()

        # 1. Interpret the goal using LLM
        try:
            response = llm.complete(
                prompt=f"Goal: {goal}\n\nInterpret this goal and return JSON with: "
                       f"goal, task_type, campaign_id, account_id, kpis (dict), deadline, priority.",
                system=CEO_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=1024,
            )
            parsed = extract_first_json_object(response)
        except Exception as exc:
            logger.warning("CEO goal interpretation failed: %s", exc)
            parsed = {}

        # 2. Build Task object
        task = Task(
            goal=goal,
            description=parsed.get("goal", goal),
            task_type=parsed.get("task_type", "ad_hoc"),
            campaign_id=parsed.get("campaign_id", ""),
            account_id=parsed.get("account_id", ""),
            kpis=parsed.get("kpis", {}),
            deadline=parsed.get("deadline", ""),
            sla_deadline=parsed.get("sla_deadline", ""),
            priority=parsed.get("priority", 2),
            planning_mode="ceo_interpreted",
            status=TaskStatus.DRAFT,
        )

        # 3. Persist to DB
        self._task_repo.create(task)
        self._task_repo.add_audit_log(
            actor="ceo",
            action_type="task_created",
            entity_type="task",
            entity_id=task.id,
            details={"goal": goal, "task_type": task.task_type},
        )

        # 4. Run LangGraph workflow
        try:
            result = self._supervisor.run(
                task_description=goal,
                task_id=task.id,
                task_type=task.task_type,
            )
            # Update task status from result (map uppercase graph statuses to lowercase)
            raw_status = result.get("status", "draft").lower()
            task.status = TaskStatus(raw_status)
            task.score = float(result.get("leader_score", 0))
            task.final_output_text = result.get("specialist_output", "")
            self._task_repo.update(task)

            logger.info(
                "CEO Brain: task %s created and executed — status=%s score=%.0f",
                task.id,
                task.status.value,
                task.score,
            )

            return {
                "action": "task_created_and_executed",
                "task_id": task.id,
                "status": task.status.value,
                "score": task.score,
                "result": result,
            }

        except Exception as exc:
            logger.exception("CEO Brain: workflow failed for task %s", task.id)
            return {
                "action": "task_created_but_failed",
                "task_id": task.id,
                "error": str(exc),
            }

    # ── MONITOR ──────────────────────────────────────────────────────

    def _run_monitor(self) -> dict[str, Any]:
        """Scan active tasks, check SLA, KPIs, and health. Return decisions."""
        from src.tasks.sla_tracker import SLATracker

        sla_tracker = SLATracker(self._task_repo)
        active_tasks = self._task_repo.list_active()
        sla_violations = sla_tracker.check_all_sla()
        health_scores = self._health_scorer.score_all_campaigns()

        decisions = self._decision_engine.monitor_decisions(
            active_tasks=active_tasks,
            sla_violations=sla_violations,
            health_scores=health_scores,
        )

        logger.info(
            "CEO Monitor: %d active tasks, %d SLA violations, %d decisions",
            len(active_tasks),
            len(sla_violations),
            len(decisions),
        )

        return {
            "action": "monitor_complete",
            "active_tasks": len(active_tasks),
            "sla_violations": [v.__dict__ for v in sla_violations],
            "campaign_health": health_scores,
            "decisions": [d.__dict__ for d in decisions],
        }

    # ── INTERVENE ────────────────────────────────────────────────────

    def _run_intervene(self) -> dict[str, Any]:
        """Handle SLA breaches, escalations, KPI misses."""
        from src.tasks.sla_tracker import SLATracker

        sla_tracker = SLATracker(self._task_repo)
        violations = sla_tracker.check_all_sla()

        actions_taken = []
        for violation in violations:
            action = self._decision_engine.intervene(violation, sla_tracker)
            actions_taken.append(action)

        return {
            "action": "intervention_complete",
            "violations_handled": len(actions_taken),
            "actions": actions_taken,
        }
