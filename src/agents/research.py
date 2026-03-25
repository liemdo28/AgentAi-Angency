"""
Research node — web search + data analysis that provides context
to the department specialist.
"""
from __future__ import annotations

import logging
from typing import Any

from src.agents.state import AgenticState
from src.tools.web_search import search_web, SearchResult
from src.tools.data_analysis import DataAnalysisTool

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are the Agency Research Analyst. Given a task description,
required inputs from the policy, and optional existing context, you decide:
1. Should we run a web search? (YES if task involves market, trends, competitors, news)
2. Should we run data analysis? (YES if inputs contain numeric/csv data)
3. Return a brief synthesis of what you found.

Keep your response focused and actionable for the specialist who will use it."""


def _synthesise_with_llm(state: AgenticState, search_results: list[SearchResult]) -> str:
    """Use LLM to synthesise search results into a research summary."""
    from src.llm import get_llm

    task_desc = state.get("task_description", "")
    policy = state.get("policy", {})
    required_inputs = policy.get("required_inputs", [])

    results_text = "\n".join(
        f"- [{r.source}] {r.title}: {r.snippet}" for r in search_results[:5]
    ) if search_results else "(no search results)"

    prompt = f"""Task: {task_desc}
Required inputs: {', '.join(required_inputs)}

Web search results:
{results_text}

Provide a 3-5 bullet synthesis of the most relevant findings for this task.
Format: - Bullet point (source: source_name)"""

    try:
        llm = get_llm()
        return llm.complete(prompt, SYSTEM_PROMPT, temperature=0.3, max_tokens=768)
    except Exception as exc:
        logger.warning(f"Research synthesis LLM failed: {exc}")
        return results_text


def run_research(state: AgenticState) -> AgenticState:
    """
    Research node — runs web search (and optionally data analysis)
    and attaches research_results to the state.
    """
    task_desc = state.get("task_description", "")
    policy = state.get("policy", {})
    required_inputs = policy.get("required_inputs", [])
    research_results: dict[str, Any] = {}

    # Determine if research is needed
    research_keywords = [
        "market", "trend", "competitor", "research", "analysis",
        "landscape", "benchmark", "industry", "audience", "persona",
        "campaign", "strategy", "insight", "data", "report",
    ]
    needs_search = any(kw in task_desc.lower() for kw in research_keywords)

    # ── Web Search ──────────────────────────────────────────────────
    if needs_search and SETTINGS.TAVILY_API_KEY or SETTINGS.SERP_API_KEY:
        try:
            logger.info("Research: running web search")
            results = search_web(
                query=task_desc,
                max_results=SETTINGS.RESEARCH_MAX_RESULTS,
            )
            research_results["search_results"] = [
                {"title": r.title, "snippet": r.snippet, "url": r.url, "source": r.source}
                for r in results
            ]
            research_results["search_synthesis"] = _synthesise_with_llm(state, results)
        except Exception as exc:
            logger.warning(f"Web search failed: {exc}")
            research_results["search_error"] = str(exc)
    else:
        logger.info("Research: skipping web search (no API keys or not needed)")

    # ── Data Analysis ───────────────────────────────────────────────
    # Check if required_inputs contain data-like keywords
    data_keywords = ["metrics", "data", "report", "spend", "revenue", "performance"]
    needs_data_analysis = any(kw in " ".join(required_inputs).lower() for kw in data_keywords)

    if needs_data_analysis and state.get("required_inputs"):
        try:
            logger.info("Research: running data analysis")
            data_tool = DataAnalysisTool()
            # Placeholder: in real usage, required_inputs would contain raw data
            analysis_result = data_tool.analyse(state.get("required_inputs", {}))
            research_results["data_analysis"] = analysis_result
        except Exception as exc:
            logger.warning(f"Data analysis failed: {exc}")
            research_results["data_analysis_error"] = str(exc)

    logger.info(f"Research node complete: {list(research_results.keys())}")

    return {
        **state,
        "research_results": research_results,
    }
