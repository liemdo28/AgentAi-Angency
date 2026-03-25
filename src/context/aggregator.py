"""
Context Aggregator — pulls together weather, market trends, and seasonality
into a single structured dict for injection into specialist prompts.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from src.context.weather import WeatherService
from src.context.market_trends import MarketTrendsService

logger = logging.getLogger(__name__)


class ContextAggregator:
    """
    Aggregate all external context (weather, market, seasonality)
    into a single prompt-ready text block.

    Usage:
        agg = ContextAggregator()
        ctx = agg.build_context(
            lat=21.0285, lon=105.8542,   # Hanoi
            sector="retail",
            campaign_goal="summer clearance campaign",
        )
        # ctx["text_block"] -> prepend to specialist system prompt
        # ctx["weather"]     -> structured data for KPI modelling
        # ctx["trends"]      -> structured data for strategy
    """

    def __init__(
        self,
        weather: Optional[WeatherService] = None,
        trends: Optional[MarketTrendsService] = None,
    ) -> None:
        self._weather = weather or WeatherService()
        self._trends = trends or MarketTrendsService()

    def build_context(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        sector: Optional[str] = None,
        campaign_goal: Optional[str] = None,
        include_weather: bool = True,
        include_trends: bool = True,
        include_seasonality: bool = True,
    ) -> dict[str, Any]:
        """
        Build a full context package.

        Returns dict with keys:
            text_block  (str)  — formatted string for prompt injection
            weather     (dict) — raw weather data
            trends      (dict) — sector trend data
            seasonality (str)   — seasonality note
            media_recommendations (list[str]) — media channel suggestions
        """
        parts: list[str] = []
        ctx: dict[str, Any] = {
            "weather": {},
            "trends": {},
            "seasonality": "",
            "media_recommendations": [],
            "text_block": "",
        }

        # Weather
        if include_weather and lat is not None and lon is not None:
            try:
                weather = self._weather.get_current(lat, lon)
                forecast = self._weather.get_forecast(lat, lon, days=3)
                ctx["weather"] = {"current": weather, "forecast": forecast.get("daily", [])}

                impact = self._weather.weather_impact_summary(
                    lat, lon,
                    campaign_type=self._infer_campaign_type(campaign_goal or ""),
                )
                parts.append(f"## Weather Context\n{impact}")
            except Exception as exc:
                logger.warning("Weather context skipped: %s", exc)

        # Seasonality
        if include_seasonality:
            try:
                from datetime import datetime as dt
                month = dt.now().month
                seasonality = self._trends.get_seasonality_note(month)
                ctx["seasonality"] = seasonality
                parts.append(f"## Seasonality\n{seasonality}")
            except Exception as exc:
                logger.warning("Seasonality context skipped: %s", exc)

        # Market Trends
        if include_trends and sector:
            try:
                trend = self._trends.get_sector_trend(sector)
                ctx["trends"] = trend
                parts.append(f"## Market Trends ({sector} sector)")
                for t in trend.get("tickers", []):
                    chg = t.get("change_pct", 0)
                    direction = "+" if (chg and chg > 0) else ""
                    parts.append(
                        f"- {t['symbol']}: ${t.get('price', 'N/A')} "
                        f"({direction}{chg:.2f}% today)"
                    )
            except Exception as exc:
                logger.warning("Trends context skipped: %s", exc)

        # Media channel recommendations
        ctx["media_recommendations"] = self._suggest_media_channels(
            sector=sector or "",
            weather=ctx.get("weather", {}),
            seasonality=ctx.get("seasonality", ""),
        )

        if ctx["media_recommendations"]:
            parts.append("## Suggested Media Channels")
            for ch in ctx["media_recommendations"]:
                parts.append(f"- {ch}")

        # Build text block
        if parts:
            ctx["text_block"] = (
                "=== EXTERNAL CONTEXT (do not repeat, use to inform output) ===\n"
                + "\n".join(parts)
                + "\n=== END EXTERNAL CONTEXT ==="
            )
        else:
            ctx["text_block"] = ""

        return ctx

    def _infer_campaign_type(self, goal: str) -> str:
        """Rough inference from campaign goal text."""
        goal_lower = goal.lower()
        if any(w in goal_lower for w in ["rain", "outdoor", "ooh", "billboard"]):
            return "outdoor"
        if any(w in goal_lower for w in ["retail", "store", "shop", "clearance"]):
            return "retail"
        if any(w in goal_lower for w in ["food", "restaurant", "qsr", "burger", "pizza"]):
            return "qsr"
        return "general"

    def _suggest_media_channels(
        self,
        sector: str,
        weather: dict,
        seasonality: str,
    ) -> list[str]:
        """Suggest media channels based on context signals."""
        channels = []

        # Sector defaults
        sector_channels = {
            "retail": ["Social Media (Meta)", "Search (Google)", "In-store POS", "Email CRM"],
            "automotive": ["CTV/OTT", "YouTube", "Display", "Print"],
            "tech": ["Programmatic Display", "LinkedIn", "Tech Publications", "YouTube"],
            "finance": ["LinkedIn", "Financial Press", "CTV", "Search"],
            "healthcare": ["Targeted Display", "Social (Meta)", "Doctor Portals", "Search"],
            "food": ["Social (Meta/TikTok)", "Delivery Apps", "OOH (clear weather)", "Influencer"],
        }

        if sector.lower() in sector_channels:
            channels.extend(sector_channels[sector.lower()])

        # Weather overrides
        current = weather.get("current", {})
        if current.get("precipitation_mm", 0) > 1.0:
            channels = [ch for ch in channels if ch not in ["OOH (clear weather)", "Outdoor"]]
            channels.append("Digital (rain-safe channels)")

        # Seasonality overrides
        month_str = seasonality.lower()
        if "holiday" in month_str or "black friday" in month_str:
            channels = ["Search (Google)", "Social (Meta)", "Email CRM", "Retail Media"] + channels

        # Deduplicate, return top 5
        seen = set()
        unique = []
        for ch in channels:
            if ch not in seen:
                seen.add(ch)
                unique.append(ch)
        return unique[:5]

    def close(self) -> None:
        self._weather.close()
        self._trends.close()

    def __enter__(self) -> "ContextAggregator":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
