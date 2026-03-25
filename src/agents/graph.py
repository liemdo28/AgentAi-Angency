"""
LangGraph definition for the Agentic Agency workflow.

Graph structure
================

  __start__
     │
     ▼
  router_node          ←── determines from/to dept + picks HandoffPolicy
     │
     ├─[invalid]──► __end__
     │
     ▼ [valid]
  research_node        ←── web search + data analysis (optional per dept)
     │
     ▼
  specialist_node       ←── department specialist generates outputs
     │
     ▼
  leader_review_node    ←── score ≥ 98% ? PASS : FAIL + feedback
     │
     ├─[passed]──► email_notification_node ──► __end__
     │
     ├─[failed]──► specialist_node (retry up to MAX_ROUTE_RETRIES)
     │
     └─[escalate]──► __end__  (human review needed)
"""
from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.agents.state import AgenticState
from src.config import SETTINGS

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Node signatures (implemented in separate files)
# ─────────────────────────────────────────────────────────────────

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


def email_notification_node(state: AgenticState) -> AgenticState:
    """Send result email to stakeholders (mock: log for now)."""
    from src.agents.notifications import send_notification
    return send_notification(state)


# ─────────────────────────────────────────────────────────────────
# Conditional edge helpers
# ─────────────────────────────────────────────────────────────────

def route_decision(state: AgenticState) -> Literal["valid", "invalid"]:
    """After router: proceed if route is valid, else end."""
    next_action = state.get("next_action", "invalid")
    return next_action


def review_decision(state: AgenticState) -> Literal["passed", "failed", "escalate"]:
    """After leader review: route based on score."""
    next_action = state.get("next_action", "escalate")
    return next_action


# ─────────────────────────────────────────────────────────────────
# Build graph
# ─────────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(AgenticState)

    # ── Nodes ────────────────────────────────────────────────────────
    builder.add_node("router", router_node)
    builder.add_node("research", research_node)
    builder.add_node("specialist", specialist_node)
    builder.add_node("leader_review", leader_review_node)
    builder.add_node("email_notification", email_notification_node)

    # ── Edges ────────────────────────────────────────────────────────
    builder.add_edge(START, "router")

    # Router → research (valid) or END (invalid)
    builder.add_conditional_edges(
        "router",
        route_decision,
        {
            "valid": "research",
            "invalid": END,
        },
    )

    builder.add_edge("research", "specialist")

    # Leader review → email / specialist-retry / END
    builder.add_conditional_edges(
        "leader_review",
        review_decision,
        {
            "passed": "email_notification",
            "failed": "specialist",   # re-runs specialist with feedback
            "escalate": END,          # max retries exceeded → human review
        },
    )

    builder.add_edge("email_notification", END)

    return builder


def compile_graph() -> StateGraph:
    """Build and compile the LangGraph."""
    graph = build_graph()
    compiled = graph.compile()
    logger.info("LangGraph compiled successfully")
    return compiled


# ─────────────────────────────────────────────────────────────────
# Singleton compiled graph
# ─────────────────────────────────────────────────────────────────

_compiled_graph = None


def get_graph() -> StateGraph:
    """Return the singleton compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = compile_graph()
    return _compiled_graph
