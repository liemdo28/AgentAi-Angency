"""Web search tools — Tavily (primary), SerpAPI (fallback)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source: str


def _search_tavily(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search using Tavily API."""
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=SETTINGS.TAVILY_API_KEY)
        response = client.search(
            query=query,
            max_results=max_results,
            include_answer=True,
            include_raw_content=False,
        )
        results = []
        for item in response.get("results", [])[:max_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                snippet=item.get("content", "")[:300],
                url=item.get("url", ""),
                source="tavily",
            ))
        logger.info(f"Tavily returned {len(results)} results")
        return results
    except Exception as exc:
        logger.warning(f"Tavily search failed: {exc}")
        return []


def _search_serpapi(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search using SerpAPI (Google)."""
    try:
        import urllib.request
        import urllib.parse
        import json

        params = urllib.parse.urlencode({
            "q": query,
            "api_key": SETTINGS.SERP_API_KEY,
            "num": max_results,
        })
        url = f"https://serpapi.com/search?{params}"

        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("organic_results", [])[:max_results]:
            results.append(SearchResult(
                title=item.get("title", ""),
                snippet=item.get("snippet", "")[:300],
                url=item.get("link", ""),
                source="serpapi",
            ))
        logger.info(f"SerpAPI returned {len(results)} results")
        return results
    except Exception as exc:
        logger.warning(f"SerpAPI search failed: {exc}")
        return []


def search_web(query: str, max_results: int = 10) -> list[SearchResult]:
    """
    Primary web search — tries Tavily first, falls back to SerpAPI.
    Returns a list of SearchResult objects.
    """
    if SETTINGS.TAVILY_API_KEY:
        results = _search_tavily(query, max_results)
        if results:
            return results

    if SETTINGS.SERP_API_KEY:
        results = _search_serpapi(query, max_results)
        if results:
            return results

    logger.info("No web search API keys configured — returning empty results")
    return []
