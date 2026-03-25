"""
Market Trends Service — Yahoo Finance + Google Trends data for media planning.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class MarketTrendsService:
    """
    Fetch market/industry trends to inform campaign planning.

    Uses:
    - Yahoo Finance public API for stock/industry data (no key required)
    - DuckDuckGo HTML scraping for trending topics (lightweight, no key)

    For production: swap to yfinance library or SerpAPI for Google Trends.
    """

    def __init__(self, client: Optional[httpx.Client] = None) -> None:
        self._client = client or httpx.Client(timeout=15.0)

    # ── Stock / Sector Performance ──────────────────────────────────

    def get_stock_info(self, ticker: str) -> dict[str, Any]:
        """
        Fetch basic stock info from Yahoo Finance (no auth required).

        Returns: {symbol, shortName, regularMarketPrice, regularMarketChange,
                  regularMarketChangePercent, fiftyTwoWeekHigh, sector}
        """
        try:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
            r = self._client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                },
                timeout=10.0,
            )
            r.raise_for_status()
            result = r.json()
            quotes = result.get("quoteResponse", {}).get("result", [])
            if not quotes:
                return {"error": f"No data for {ticker}"}
            q = quotes[0]
            return {
                "symbol": q.get("symbol"),
                "short_name": q.get("shortName"),
                "price": q.get("regularMarketPrice"),
                "change": q.get("regularMarketChange"),
                "change_pct": q.get("regularMarketChangePercent"),
                "fifty_two_week_high": q.get("fiftyTwoWeekHigh"),
                "sector": q.get("sector"),
                "industry": q.get("industry"),
            }
        except Exception as exc:
            logger.warning("Stock fetch failed for %s: %s", ticker, exc)
            return {"error": str(exc), "symbol": ticker}

    def get_sector_trend(self, sector: str) -> dict[str, Any]:
        """
        Map a sector name to relevant tickers and return their performance.

        sector: "retail" | "automotive" | "tech" | "finance" | "healthcare" | "food"
        """
        SECTOR_TICKERS = {
            "retail": ["WMT", "TGT", "COST"],
            "automotive": ["TM", "F", "GM"],
            "tech": ["AAPL", "MSFT", "GOOGL"],
            "finance": ["JPM", "BAC", "GS"],
            "healthcare": ["UNH", "JNJ", "PFE"],
            "food": ["MCD", "SBUX", "KO"],
        }
        tickers = SECTOR_TICKERS.get(sector.lower(), ["SPY"])
        results = []
        for t in tickers:
            info = self.get_stock_info(t)
            if "error" not in info:
                results.append(info)
        return {"sector": sector, "tickers": results}

    # ── Industry Keyword Trends ──────────────────────────────────────

    def get_industry_sentiment(self, keyword: str) -> dict[str, Any]:
        """
        Lightweight trend check: search for keyword and return
        a simple sentiment signal based on recent headline count.

        Returns: {keyword, signal: "hot" | "neutral" | "cold", headline_count, note}
        """
        try:
            # Use DuckDuckGo HTML for quick trending (no API key)
            url = "https://duckduckgo.com/html/"
            r = self._client.get(
                url,
                params={"q": keyword},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10.0,
            )
            r.raise_for_status()
            text = r.text
            # Count occurrences as a proxy for volume (very rough)
            count = text.lower().count(keyword.lower())
            if count > 20:
                signal = "hot"
                note = f"High mention volume detected for '{keyword}'."
            elif count > 5:
                signal = "neutral"
                note = f"Moderate mention volume for '{keyword}'."
            else:
                signal = "cold"
                note = f"Low mention volume for '{keyword}'."

            return {
                "keyword": keyword,
                "signal": signal,
                "headline_count_proxy": count,
                "note": note,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.warning("Trend check failed for %s: %s", keyword, exc)
            return {"keyword": keyword, "signal": "neutral", "error": str(exc)}

    # ── Seasonality ──────────────────────────────────────────────────

    def get_seasonality_note(self, month: Optional[int] = None) -> str:
        """
        Return a media planning seasonality note for the given month (1-12).
        If month is None, uses current month.
        """
        if month is None:
            month = datetime.now(timezone.utc).month

        SEASONALITY = {
            1: "Post-holiday clearance. Low consumer intent. Focus on value messaging.",
            2: "Valentine's Day (Feb 14). Gifting categories peak. CRM and social effective.",
            3: "Spring emerging. Retail revival. Outdoor/media spend can increase.",
            4: "Easter window (variable). Travel and family categories active.",
            5: "Pre-summer buildup. Outdoor advertising season begins.",
            6: "Summer starts. Travel, beverage, entertainment peak. Consider OOH.",
            7: "Peak summer. Vacation season. Mid-year budget review. Retargeting effective.",
            8: "Back-to-school season begins. Education, retail campaigns ramp.",
            9: "Back-to-school peak. Q4 planning starts. Budget allocation critical.",
            10: "Pre-holiday planning. Creative production for Q4 campaigns.",
            11: "Black Friday window opens. Retail dominates. Early deals testing.",
            12: "Peak holiday season. Retail, gifting, food. Last-chance messaging.",
        }
        return SEASONALITY.get(month, "Standard media planning month.")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MarketTrendsService":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
