"""
Marketing Sync — pulls live store data from marketing.bakudanramen.com REST API.

Uses Bearer token auth (same as existing marketing_connector).
No Playwright/browser needed — pure HTTP.

Endpoints used:
  GET /api/branch-state.php  → store-level data with last sync dates
  GET /api/analytics.php     → aggregate metrics across all stores
  POST /api/campaign/sync    → trigger data refresh
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("connectors.marketing_sync")


def _get_config() -> dict:
    """Get marketing API config from environment."""
    return {
        "base_url": os.getenv("GROWTH_BASE_URL", os.getenv("MARKETING_BASE_URL", "https://marketing.bakudanramen.com")),
        "token": os.getenv("GROWTH_API_KEY", os.getenv("MARKETING_API_TOKEN", "")),
        "timeout": int(os.getenv("MARKETING_TIMEOUT", "30")),
    }


def _api_request(endpoint: str, method: str = "GET", data: dict | None = None) -> dict:
    """Make an authenticated API request to the marketing site."""
    cfg = _get_config()
    url = f"{cfg['base_url'].rstrip('/')}/{endpoint.lstrip('/')}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {cfg['token']}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "AgentAI-MarketingSync/1.0")

    try:
        resp = urllib.request.urlopen(req, timeout=cfg["timeout"])
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")[:500]
        logger.warning("Marketing API %s %s → %d: %s", method, endpoint, e.code, body_text)
        return {"error": True, "status_code": e.code, "message": body_text}
    except Exception as exc:
        logger.warning("Marketing API %s %s failed: %s", method, endpoint, exc)
        return {"error": True, "message": str(exc)}


class MarketingSync:
    """Pull store-level data from marketing.bakudanramen.com."""

    def get_all_stores(self) -> dict:
        """Fetch all branch/store data with last sync dates.

        Returns:
            {
                "ok": bool,
                "stores": [
                    {"id": "...", "label": "...", "last_updated": "...", "data": {...}},
                    ...
                ],
                "totals": {...},
            }
        """
        # Try analytics endpoint first (has aggregate data)
        analytics = _api_request("api/analytics.php")
        if analytics.get("error"):
            # Fallback to branch-state
            branch_data = _api_request("api/branch-state.php")
            if branch_data.get("error"):
                return {"ok": False, "stores": [], "error": analytics.get("message", "API unavailable")}
            return self._parse_branch_state(branch_data)

        return self._parse_analytics(analytics)

    def get_store(self, store_id: str) -> dict:
        """Get data for a specific store by ID."""
        all_data = self.get_all_stores()
        if not all_data.get("ok"):
            return all_data

        for store in all_data.get("stores", []):
            if store.get("id") == store_id or store.get("label", "").lower().startswith(store_id.lower()):
                return {"ok": True, "store": store}

        return {"ok": False, "error": f"Store '{store_id}' not found"}

    def trigger_sync(self, store_id: str | None = None) -> dict:
        """Trigger a data sync for all stores or a specific one."""
        payload = {}
        if store_id:
            payload["store_id"] = store_id

        result = _api_request("api/campaign/sync", method="POST", data=payload)
        if result.get("error"):
            return {"ok": False, "error": result.get("message", "Sync failed")}

        return {"ok": True, "message": "Sync triggered", "result": result}

    def get_summary(self) -> dict:
        """Get AI-generated summary of all stores (uses LLM)."""
        stores_data = self.get_all_stores()
        if not stores_data.get("ok"):
            return {"ok": False, "summary": "Could not fetch store data", "error": stores_data.get("error")}

        stores = stores_data.get("stores", [])
        totals = stores_data.get("totals", {})

        # Build summary without LLM (structured)
        lines = ["## Marketing Dashboard Summary", ""]

        if totals:
            lines.append(f"**Total Revenue:** ${totals.get('revenue', 0):,.2f}")
            lines.append(f"**Total Orders:** {totals.get('orders', 0)}")
            lines.append(f"**Total Ad Spend:** ${totals.get('spend', 0):,.2f}")
            roas = totals.get('roas', 0)
            if roas:
                lines.append(f"**ROAS:** {roas:.1f}x")
            lines.append("")

        for store in stores:
            label = store.get("label", "Unknown")
            updated = store.get("last_updated", "unknown")
            lines.append(f"### {label}")
            lines.append(f"- Last data: {updated}")

            data = store.get("data", {})
            if data.get("revenue"):
                lines.append(f"- Revenue: ${data['revenue']:,.2f}")
            if data.get("orders"):
                lines.append(f"- Orders: {data['orders']}")
            lines.append("")

        return {
            "ok": True,
            "summary": "\n".join(lines),
            "store_count": len(stores),
            "totals": totals,
        }

    def health_check(self) -> dict:
        """Quick health check of the marketing API."""
        result = _api_request("api/health")
        if result.get("error"):
            # Try a simpler endpoint
            result2 = _api_request("api/health.php")
            if result2.get("error"):
                return {"ok": False, "message": "Marketing API unreachable"}
            return {"ok": True, "source": "health.php", "data": result2}
        return {"ok": True, "source": "api/health", "data": result}

    # ── Parsers ───────────────────────────────────────────────────────

    def _parse_analytics(self, data: dict) -> dict:
        """Parse analytics.php response."""
        stores = []
        for branch in data.get("branches", []):
            stores.append({
                "id": branch.get("branchId", branch.get("id", "")),
                "label": branch.get("label", "Unknown"),
                "last_updated": branch.get("updatedAt", branch.get("updated_at", "unknown")),
                "data": {
                    "revenue": branch.get("revenue", 0),
                    "orders": branch.get("orders", 0),
                    "units": branch.get("units", 0),
                    "spend": branch.get("spend", 0),
                    "impressions": branch.get("impressions", 0),
                    "clicks": branch.get("clicks", 0),
                    "conversions": branch.get("conversions", 0),
                    "roas": branch.get("roas", 0),
                },
            })

        return {
            "ok": True,
            "stores": stores,
            "totals": data.get("totals", {}),
            "generated_at": data.get("generatedAt", ""),
        }

    def _parse_branch_state(self, data: dict) -> dict:
        """Parse branch-state.php response."""
        if isinstance(data, list):
            branches = data
        elif isinstance(data, dict):
            branches = data.get("branches", data.get("data", []))
        else:
            branches = []

        stores = []
        for branch in branches:
            state = branch.get("state", {})
            sales_rows = state.get("salesRows", [])
            last_revenue = sales_rows[-1] if sales_rows else {}

            stores.append({
                "id": branch.get("branchId", branch.get("id", "")),
                "label": branch.get("label", "Unknown"),
                "last_updated": branch.get("updatedAt", "unknown"),
                "data": {
                    "revenue": last_revenue.get("revenue", 0),
                    "orders": last_revenue.get("orders", 0),
                    "date": last_revenue.get("date", ""),
                },
            })

        return {"ok": True, "stores": stores, "totals": {}}
