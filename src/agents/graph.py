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
    builder.add_node("research", research_node)
    builder.add_node("specialist", specialist_node)
    builder.add_node("leader_review", leader_review_node)
    builder.add_node("task_progress", task_progress_node)
    builder.add_node("email_notification", email_notification_node)

    builder.add_edge(START, "task_planner")
    builder.add_edge("task_planner", "router")

    builder.add_conditional_edges(
        "router",
        route_decision,
        {"valid": "research", "invalid": END},
    )

    builder.add_edge("research", "specialist")
    builder.add_edge("specialist", "leader_review")

    builder.add_conditional_edges(
        "leader_review",
        review_decision,
        {"passed": "task_progress", "failed": "specialist", "escalate": END},
    )

    builder.add_conditional_edges(
        "task_progress",
        progress_decision,
        {"continue": "router", "done": "email_notification"},
    )

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
