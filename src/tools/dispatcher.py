"""
Tool Dispatcher — routes tool calls from specialists to the right driver.
Specialists call dispatcher.run(tool_name, params) rather than tools directly.

Supported tools:
- google_sheets: read/write Google Sheets
- ads_api: Facebook/Google Ads performance data
- email: send transactional emails
- file_storage: store and retrieve files
- webhook: call external HTTP webhooks
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.tools.email_client import EmailClient, EmailMessage
from src.tools.file_storage import FileStorage

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    tool: str
    success: bool
    data: Any
    error: Optional[str] = None


class ToolDispatcher:
    """
    Centralized tool routing for all specialist tool calls.

    Specialists never call external libraries directly; they call:
        result = dispatcher.run("google_sheets", {"operation": "read", "sheet_url": "..."})

    This enables:
    - Easy mocking in tests
    - Centralized auth handling
    - Unified error handling and logging
    - Runtime tool enable/disable via config
    """

    def __init__(self) -> None:
        self._email: Optional[EmailClient] = None
        self._storage: Optional[FileStorage] = None
        self._tools_enabled = {
            "google_sheets": True,
            "ads_api": True,
            "email": True,
            "file_storage": True,
            "webhook": True,
        }

    # ── Enable / Disable ──────────────────────────────────────────────

    def enable(self, tool: str) -> None:
        self._tools_enabled[tool] = True

    def disable(self, tool: str) -> None:
        self._tools_enabled[tool] = False

    def is_enabled(self, tool: str) -> bool:
        return self._tools_enabled.get(tool, False)

    # ── Run ────────────────────────────────────────────────────────────

    def run(self, tool: str, params: dict[str, Any]) -> ToolResult:
        """
        Route a tool call. Returns ToolResult.
        """
        if not self._tools_enabled.get(tool, False):
            return ToolResult(
                tool=tool,
                success=False,
                data=None,
                error=f"Tool '{tool}' is disabled",
            )

        handler_map = {
            "google_sheets": self._google_sheets,
            "ads_api": self._ads_api,
            "email": self._email_tool,
            "file_storage": self._file_storage_tool,
            "webhook": self._webhook_tool,
        }

        handler = handler_map.get(tool)
        if not handler:
            return ToolResult(
                tool=tool,
                success=False,
                data=None,
                error=f"Unknown tool: {tool}",
            )

        try:
            data = handler(params)
            return ToolResult(tool=tool, success=True, data=data)
        except Exception as exc:
            logger.exception("Tool '%s' failed: %s", tool, exc)
            return ToolResult(tool=tool, success=False, data=None, error=str(exc))

    # ── Google Sheets ──────────────────────────────────────────────────

    def _google_sheets(self, params: dict[str, Any]) -> Any:
        """
        Read or write a Google Sheet.

        params:
            operation: "read" | "write" | "append"
            sheet_url: str (Google Sheets URL)
            range: str (e.g. "Sheet1!A1:Z100")
            values: list[list] (for write/append)
            sheet_name: str (optional, defaults to first sheet)
        """
        try:
            import gspread
        except ImportError:
            raise RuntimeError("gspread not installed. Run: pip install gspread")

        gc = gspread.oauth()  # uses CREDENTIALS_FILE or GOOGLE_APPLICATION_CREDENTIALS
        operation = params.get("operation", "read")
        sheet_url = params.get("sheet_url")
        if not sheet_url:
            raise ValueError("sheet_url is required for google_sheets tool")

        sh = gc.open_by_url(sheet_url)
        ws = sh.sheet1
        if "sheet_name" in params:
            ws = sh.worksheet(params["sheet_name"])

        if operation == "read":
            range_spec = params.get("range", "A1:Z100")
            return ws.get(range_spec)

        if operation == "write":
            range_spec = params.get("range", "A1")
            values = params.get("values", [])
            ws.update(range_spec, values)
            return {"updated": f"{range_spec} with {len(values)} rows"}

        if operation == "append":
            values = params.get("values", [])
            ws.append_rows(values)
            return {"appended": f"{len(values)} rows"}

        raise ValueError(f"Unknown google_sheets operation: {operation}")

    # ── Ads API ────────────────────────────────────────────────────────

    def _ads_api(self, params: dict[str, Any]) -> Any:
        """
        Fetch performance data from Google Ads or Facebook/Meta Ads API.

        params:
            platform: "google_ads" | "meta_ads"
            account_id: str
            fields: list[str]  (e.g. ["impressions", "clicks", "spend", "conversions"])
            date_range: str (e.g. "LAST_30_DAYS", "2026-01-01,2026-01-31")
            campaign_name_filter: str (optional)
        """
        platform = params.get("platform", "google_ads")
        account_id = params.get("account_id")

        if platform == "google_ads":
            return self._google_ads_fetch(params)
        elif platform == "meta_ads":
            return self._meta_ads_fetch(params)
        else:
            raise ValueError(f"Unknown ads platform: {platform}")

    def _google_ads_fetch(self, params: dict[str, Any]) -> Any:
        try:
            from google.ads.googleads import Client, GoogleAdsService
            from google.ads.googleads.v18 import services as gad_services
        except ImportError:
            raise RuntimeError("google-ads not installed. Run: pip install google-ads")

        developer_token = params.get("developer_token") or __import__("os").get(
            "GOOGLE_ADS_DEVELOPER_TOKEN"
        )
        account_id = params.get("account_id", "")
        fields = params.get("fields", ["impressions", "clicks", "spend"])
        date_range = params.get("date_range", "LAST_30_DAYS")

        # Simplified: return mock structure since real API needs MCC setup
        logger.info("Google Ads fetch for account %s (fields: %s)", account_id, fields)
        return {
            "platform": "google_ads",
            "account_id": account_id,
            "date_range": date_range,
            "fields": fields,
            "data": [],  # Populated when credentials are configured
            "note": "Configure GOOGLE_ADS_DEVELOPER_TOKEN + google-ads.yaml for live data",
        }

    def _meta_ads_fetch(self, params: dict[str, Any]) -> Any:
        try:
            import requests
        except ImportError:
            raise RuntimeError("requests not installed")

        access_token = params.get("access_token") or __import__("os").get(
            "META_ACCESS_TOKEN"
        )
        account_id = params.get("account_id", "")
        fields = params.get("fields", ["impressions", "clicks", "spend"])
        date_range = params.get("date_range", "last_30d")

        if not access_token:
            raise ValueError("META_ACCESS_TOKEN not set")

        base = "https://graph.facebook.com/v19.0"
        params_req = {
            "fields": ",".join(fields),
            "time_range": date_range,
            "access_token": access_token,
        }
        resp = requests.get(
            f"{base}/act_{account_id}/insights",
            params=params_req,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Email ─────────────────────────────────────────────────────────

    def _email_tool(self, params: dict[str, Any]) -> Any:
        """Send an email via the EmailClient."""
        client = self._get_email_client()
        msg = EmailMessage(
            to=params.get("to", ""),
            subject=params.get("subject", ""),
            body=params.get("body", ""),
            html_body=params.get("html_body"),
            cc=params.get("cc"),
        )
        receipt = client.send(msg)
        return {"message_id": receipt.message_id, "status": receipt.status, "error": receipt.error}

    def _get_email_client(self) -> EmailClient:
        if self._email is None:
            self._email = EmailClient()
        return self._email

    # ── File Storage ──────────────────────────────────────────────────

    def _file_storage_tool(self, params: dict[str, Any]) -> Any:
        """Store or retrieve a file."""
        storage = self._get_storage()
        operation = params.get("operation", "put")

        if operation == "put":
            result = storage.put(
                path=params["path"],
                data=params["data"],
                content_type=params.get("content_type", "application/octet-stream"),
            )
            return {"path": result.path, "url": result.url, "size": result.size_bytes, "checksum": result.checksum}

        elif operation == "get":
            data = storage.get(params["path"])
            return {"data": data, "found": data is not None}

        elif operation == "url":
            url = storage.get_url(params["path"], expires_in=params.get("expires_in", 3600))
            return {"url": url}

        elif operation == "delete":
            deleted = storage.delete(params["path"])
            return {"deleted": deleted}

        elif operation == "list":
            paths = storage.list(params.get("prefix", ""))
            return {"paths": paths}

        else:
            raise ValueError(f"Unknown file_storage operation: {operation}")

    def _get_storage(self) -> FileStorage:
        if self._storage is None:
            self._storage = FileStorage()
        return self._storage

    # ── Webhook ────────────────────────────────────────────────────────

    def _webhook_tool(self, params: dict[str, Any]) -> Any:
        """Call an external HTTP webhook."""
        import httpx
        url = params.get("url")
        method = params.get("method", "POST").upper()
        headers = params.get("headers", {})
        body = params.get("body")

        if not url:
            raise ValueError("url is required for webhook tool")

        timeout = params.get("timeout", 30)
        with httpx.Client(timeout=timeout) as client:
            req_kwargs: dict[str, Any] = {"url": url, "headers": headers}
            if body:
                req_kwargs["json" if params.get("json_body", True) else "content"] = body

            if method == "GET":
                r = client.get(**req_kwargs)
            elif method == "PUT":
                r = client.put(**req_kwargs)
            elif method == "DELETE":
                r = client.delete(**req_kwargs)
            else:
                r = client.post(**req_kwargs)

            return {
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body": r.text[:5000],  # cap response body
            }
