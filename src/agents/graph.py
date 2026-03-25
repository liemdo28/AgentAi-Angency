"""
LangGraph definition for the Agentic Agency workflow.

Graph structure
================

  __start__
     |
     v
  task_planner_node    <- expands one business brief into many handoffs
     |
     v
  router_node          <- determines from/to dept + picks HandoffPolicy
     |
     +-[invalid]---> __end__
     |
     v [valid]
  research_node        <- web search + data analysis (optional per dept)
     |
     v
  specialist_node      <- department specialist generates outputs
     |
     v
  leader_review_node   <- quality gate + feedback loop
     |
     +-[passed]---> task_progress_node
     |
     +-[failed]---> specialist_node  (retry up to MAX_RETRIES)
     |
     +-[escalate]-> __end__
     |
     v
  task_progress_node   <- advances to the next business step
     |
     +-[continue]-> router_node  (loop)
     |
     +-[done]-----> email_notification_node -> __end__
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.agents.state import AgenticState

logger = logging.getLogger(__name__)


def task_planner_node(state: AgenticState) -> AgenticState:
    """Build a business-task plan before routing begins."""
    from src.agents.task_planner import plan_task
    return plan_task(state)


def router_node(state: AgenticState) -> AgenticState:
    """Pick the correct department route based on task description."""
    from src.agents.router import route_task
    return route_task(state)


def memory_context_node(state: AgenticState) -> AgenticState:
    """
    Load account + campaign memory and inject into state.
    Runs between router and research so specialists have full context.
    """
    account_id = state.get("account_id", "")
    campaign_id = state.get("campaign_id", "")

    memory_parts: list[str] = []
    external_parts: list[str] = []

    if account_id:
        try:
            from src.memory.account_memory import AccountMemoryStore
            store = AccountMemoryStore(account_id)
            memories = store.get(limit=5)
            if memories:
                memory_parts.append(f"## Account Memory ({account_id})")
                for m in memories:
                    date = m.get("created_at", "")[:10]
                    mtype = m.get("memory_type", "general")
                    content = m.get("content", "")
                    memory_parts.append(f"[{date}] [{mtype}] {content}")
        except Exception as exc:
            logger.warning("Account memory load failed for %s: %s", account_id, exc)

    if campaign_id:
        try:
            from src.memory.campaign_memory import CampaignMemoryStore
            store = CampaignMemoryStore(campaign_id)
            events = store.get_events(limit=5)
            if events:
                memory_parts.append(f"## Campaign Events ({campaign_id})")
                for e in events:
                    date = e.get("created_at", "")[:10]
                    etype = e.get("event_type", "general")
                    desc = e.get("description", "")
                    memory_parts.append(f"[{date}] [{etype}] {desc}")
        except Exception as exc:
            logger.warning("Campaign memory load failed for %s: %s", campaign_id, exc)

    # Inject external context (weather, market, seasonality) if available
    try:
        from src.context.aggregator import ContextAggregator
        lat = state.get("metadata", {}).get("lat")
        lon = state.get("metadata", {}).get("lon")
        sector = state.get("metadata", {}).get("sector", "retail")
        if lat and lon:
            agg = ContextAggregator()
            ctx = agg.build_context(lat=lat, lon=lon, sector=sector)
            ext = ctx.get("text_block", "")
            if ext:
                external_parts.append(ext)
    except Exception as exc:
        logger.warning("Context aggregator failed: %s", exc)

    return {
        **state,
        "memory_context": "\n".join(memory_parts) if memory_parts else "",
        "external_context": "\n".join(external_parts) if external_parts else "",
    }


def research_node(state: AgenticState) -> AgenticState:
    """Run web search + data analysis and attach results to state."""
    from src.agents.research import run_research
    return run_research(state)


def specialist_node(state: AgenticState) -> AgenticState:
    """Route to the correct department specialist and generate output."""
    from src.agents.specialists import run_specialist
    return run_specialist(state)


def leader_review_node(state: AgenticState) -> AgenticState:
    """Score specialist output; route to pass/fail/escalate."""
    from src.agents.leader_reviewer import review_output
    return review_output(state)


def task_progress_node(state: AgenticState) -> AgenticState:
    """Advance to the next task step or finish the task."""
    from src.agents.task_progress import advance_task
    return advance_task(state)


def email_notification_node(state: AgenticState) -> AgenticState:
    """Send result email to stakeholders (mock: log for now)."""
    from src.agents.notifications import send_notification
    return send_notification(state)


def sla_check_node(state: AgenticState) -> AgenticState:
    """Record SLA deadline after each step completes."""
    from src.tasks.sla_tracker import SLATracker
    from src.db.repositories.task_repo import TaskRepository
    from src.tasks.models import TaskStatus
    task_id = state.get("task_id", "")
    if task_id:
        try:
            repo = TaskRepository()
            task = repo.get(task_id)
            if task and task.status == TaskStatus.IN_PROGRESS:
                tracker = SLATracker(repo)
                tracker.check_task(task)
        except Exception as exc:
            logger.warning("SLA check failed for task %s: %s", task_id, exc)
    return state


def kpi_record_node(state: AgenticState) -> AgenticState:
    """Record KPI metrics after task completion."""
    from src.tasks.kpi_store import KPIStore
    from src.db.repositories.task_repo import TaskRepository
    task_id = state.get("task_id", "")
    campaign_id = state.get("campaign_id", "")
    kpis = state.get("metadata", {}).get("kpis", {})
    if task_id and kpis:
        try:
            repo = TaskRepository()
            store = KPIStore(repo)
            store.record(task_id, campaign_id, kpis)
        except Exception as exc:
            logger.warning("KPI record failed for task %s: %s", task_id, exc)
    return state


def retry_injection_node(state: AgenticState) -> AgenticState:
    """
    Injects retry feedback into the specialist prompt when looping back.
    This node reads leader_feedback and ensures it is prepended to the next
    specialist call. Activates only when next_action == 'failed'.
    """
    feedback = state.get("leader_feedback", "")
    retry_count = state.get("retry_count", 0)
    if feedback and retry_count > 0:
        # Attach retry context to metadata so the specialist can pick it up
        logger.info(
            "Retry injection: attempt %d, feedback length=%d",
            retry_count,
            len(feedback),
        )
    return {
        **state,
        "metadata": {
            **state.get("metadata", {}),
            "retry_attempt": retry_count,
            "retry_feedback": feedback,
        },
    }


def route_decision(state: AgenticState) -> Literal["valid", "invalid"]:
    """After router: proceed if route is valid, else end."""
    return state.get("next_action", "invalid")


def review_decision(state: AgenticState) -> Literal["passed", "failed", "escalate"]:
    """After leader review: route based on score."""
    return state.get("next_action", "escalate")


def progress_decision(state: AgenticState) -> Literal["continue", "done"]:
    """After a successful step: continue to the next step or finish."""
    return state.get("next_action", "done")


def build_graph() -> StateGraph:
    builder = StateGraph(AgenticState)

    builder.add_node("task_planner", task_planner_node)
    builder.add_node("router", router_node)
    builder.add_node("memory_context", memory_context_node)
    builder.add_node("research", research_node)
    builder.add_node("specialist", specialist_node)
    builder.add_node("leader_review", leader_review_node)
    builder.add_node("task_progress", task_progress_node)
    builder.add_node("sla_check", sla_check_node)
    builder.add_node("kpi_record", kpi_record_node)
    builder.add_node("retry_injection", retry_injection_node)
    builder.add_node("email_notification", email_notification_node)

    builder.add_edge(START, "task_planner")
    builder.add_edge("task_planner", "router")

    builder.add_conditional_edges(
        "router",
        route_decision,
        {"valid": "memory_context", "invalid": END},
    )

    builder.add_edge("memory_context", "research")

    builder.add_edge("research", "specialist")
    builder.add_edge("specialist", "leader_review")

    builder.add_conditional_edges(
        "leader_review",
        review_decision,
        {
            "passed": "task_progress",
            "failed": "retry_injection",
            "escalate": END,
        },
    )

    # retry_injection adds feedback to metadata, then loops back to specialist
    builder.add_edge("retry_injection", "specialist")

    builder.add_conditional_edges(
        "task_progress",
        progress_decision,
        {"continue": "router", "done": "sla_check"},
    )

    # After sla_check, record KPIs then send email
    builder.add_edge("sla_check", "kpi_record")
    builder.add_edge("kpi_record", "email_notification")
    builder.add_edge("email_notification", END)

    return builder


def compile_graph() -> StateGraph:
    """Build and compile the LangGraph."""
    compiled = build_graph().compile()
    logger.info("LangGraph compiled successfully")
    return compiled


_compiled_graph = None


def get_graph() -> StateGraph:
    """Return the singleton compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_graph()
    return _compiled_graph
