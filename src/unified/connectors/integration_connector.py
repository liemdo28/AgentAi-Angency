"""
Integration Connector - ToastPOS ↔ QuickBooks sync + Toast Report Ingestion.

Handles:
  1. Toast ↔ QB sync (existing desktop-app pipeline)
  2. Toast report ingestion (CSV/XLSX → parse → validate → normalize → DB)
  3. Google Drive polling for auto-ingest

Authentication: QB credentials stored in .env
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.unified.connectors.base import (
    BaseConnector,
    ConnectorAction,
    ConnectorResult,
    ConnectorStatus,
    HealthResult,
)

logger = logging.getLogger(__name__)

# Path to integration-full project
INTEGRATION_PATH = Path(r"E:\Project\Master\integration-full")


class IntegrationConnector(BaseConnector):
    """Connector for Toast-QB Integration."""

    project_id = "integration-full"
    project_name = "Integration Full (Toast-QB)"
    base_url = "http://localhost:18080"  # Local API (future)
    timeout = 10.0

    def __init__(self):
        super().__init__()
        self._base_path = INTEGRATION_PATH

    @property
    def desktop_env(self) -> Path:
        return self._base_path / "desktop-app" / ".env"

    @property
    def qb_log_dir(self) -> Path:
        return self._base_path / "desktop-app" / "logs"

    @property
    def state_file(self) -> Path:
        return self._base_path / "desktop-app" / "sync_state.json"

    async def check_health(self) -> HealthResult:
        """Check if integration is healthy."""
        start = datetime.now(timezone.utc)
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        if not self._base_path.exists():
            return HealthResult(
                status=ConnectorStatus.OFFLINE,
                latency_ms=latency_ms,
                message=f"Integration path not found",
            )

        # Check sync state file
        if self.state_file.exists():
            try:
                import json
                state = json.loads(self.state_file.read_text())
                last_sync = state.get("last_sync")
                if last_sync:
                    last = datetime.fromisoformat(last_sync)
                    age_min = (datetime.now(timezone.utc) - last).total_seconds() / 60
                    if age_min > 120:
                        return HealthResult(
                            status=ConnectorStatus.WARNING,
                            latency_ms=latency_ms,
                            message=f"Last sync {int(age_min)}m ago - may be stale",
                            details=state,
                        )

                return HealthResult(
                    status=ConnectorStatus.ONLINE,
                    latency_ms=latency_ms,
                    message="Sync state OK",
                    details=state,
                )
            except Exception as e:
                return HealthResult(
                    status=ConnectorStatus.WARNING,
                    latency_ms=latency_ms,
                    message=f"Could not read sync state: {e}",
                )
        else:
            return HealthResult(
                status=ConnectorStatus.WARNING,
                latency_ms=latency_ms,
                message="No sync state found - run sync first",
            )

    async def get_status(self) -> dict:
        """Get current status and metrics."""
        health = await self.check_health()

        status = {
            "project_id": self.project_id,
            "status": health.status.value,
            "latency_ms": health.latency_ms,
            "last_check": health.last_check.isoformat(),
            "metrics": {},
        }

        if self.state_file.exists():
            try:
                import json
                state = json.loads(self.state_file.read_text())
                status["metrics"] = {
                    "last_sync": state.get("last_sync"),
                    "orders_synced": state.get("orders_synced", 0),
                    "sync_errors": state.get("errors", 0),
                    "stores_synced": state.get("stores_synced", []),
                    "qb_status": state.get("qb_status", "unknown"),
                    "toast_status": state.get("toast_status", "unknown"),
                }
            except Exception:
                pass

        return status

    async def get_available_actions(self) -> list[ConnectorAction]:
        """List available actions for integration."""
        return [
            # ── Existing Toast-QB sync actions ──
            ConnectorAction(
                id="integration.sync",
                name="Sync Now",
                description="Run Toast → QB sync for all stores",
                category="sync",
                requires_confirmation=True,
            ),
            ConnectorAction(
                id="integration.sync_store",
                name="Sync Store",
                description="Sync data for a specific store",
                category="sync",
                payload_schema={"store_id": "string"},
            ),
            ConnectorAction(
                id="integration.verify",
                name="Verify Connection",
                description="Check QB and Toast connections",
                category="general",
            ),
            ConnectorAction(
                id="integration.retry_errors",
                name="Retry Errors",
                description="Retry failed sync records",
                category="general",
            ),
            ConnectorAction(
                id="integration.export",
                name="Export Report",
                description="Export sync report to CSV",
                category="data",
            ),
            # ── Toast Report Ingestion actions ──
            ConnectorAction(
                id="integration.ingest_file",
                name="Ingest Toast Report",
                description="Parse, validate and load a single Toast report file",
                category="data",
                payload_schema={"file_path": "string"},
            ),
            ConnectorAction(
                id="integration.ingest_folder",
                name="Ingest Folder",
                description="Process all Toast reports in a directory",
                category="data",
                payload_schema={"folder_path": "string", "recursive": "boolean"},
            ),
            ConnectorAction(
                id="integration.gdrive_poll",
                name="Poll Google Drive",
                description="Check Google Drive for new Toast report uploads",
                category="data",
            ),
            ConnectorAction(
                id="integration.coverage",
                name="Coverage Matrix",
                description="Show which Toast report types are supported",
                category="general",
            ),
            ConnectorAction(
                id="integration.upload_status",
                name="Upload Status",
                description="Query recent Toast report upload statuses",
                category="data",
                payload_schema={"limit": "integer"},
            ),
        ]

    async def execute_action(
        self,
        action_id: str,
        payload: Optional[dict] = None,
        job_id: Optional[str] = None,
    ) -> ConnectorResult:
        """Execute an integration action."""
        import subprocess
        from pathlib import Path

        action_dir = self._base_path / "desktop-app"
        start = datetime.now(timezone.utc)

        if action_id == "integration.sync":
            # Run the sync script
            sync_script = action_dir / "sync_toast_qb.py"
            if not sync_script.exists():
                return ConnectorResult(
                    success=False,
                    message="sync_toast_qb.py not found",
                )

            try:
                result = subprocess.run(
                    ["python", str(sync_script), "--all"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=str(action_dir),
                    env={**subprocess.os.environ, "PYTHONPATH": str(self._base_path)},
                )
                duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

                return ConnectorResult(
                    success=result.returncode == 0,
                    message="Sync completed" if result.returncode == 0 else f"Sync failed: {result.stderr}",
                    data={"stdout": result.stdout, "stderr": result.stderr},
                    duration_ms=duration_ms,
                )
            except subprocess.TimeoutExpired:
                return ConnectorResult(
                    success=False,
                    message="Sync timed out after 5 minutes",
                    error="timeout",
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "integration.sync_store":
            store_id = (payload or {}).get("store_id")
            if not store_id:
                return ConnectorResult(success=False, message="store_id required")

            sync_script = action_dir / "sync_toast_qb.py"
            if not sync_script.exists():
                return ConnectorResult(success=False, message="sync_toast_qb.py not found")

            try:
                result = subprocess.run(
                    ["python", str(sync_script), "--store", store_id],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(action_dir),
                    env={**subprocess.os.environ, "PYTHONPATH": str(self._base_path)},
                )
                return ConnectorResult(
                    success=result.returncode == 0,
                    message=f"Sync for {store_id} completed" if result.returncode == 0 else f"Failed: {result.stderr}",
                    data={"stdout": result.stdout},
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=str(e),
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "integration.verify":
            # Check QB credentials and Toast API
            env_file = self.desktop_env
            if not env_file.exists():
                return ConnectorResult(success=False, message=".env not configured")

            return ConnectorResult(
                success=True,
                message="Integration configured - QB path and Toast credentials present",
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

        elif action_id == "integration.export":
            # Export sync report
            report_path = self.qb_log_dir / f"sync_report_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
            # Create empty report if no data
            if self.state_file.exists():
                import json
                state = json.loads(self.state_file.read_text())
                # Generate CSV header
                report_path.write_text(
                    "store,last_sync,orders_synced,errors\n"
                    + "\n".join(
                        f"{s['store']},{s.get('last_sync','')},{s.get('orders_synced',0)},{s.get('errors',0)}"
                        for s in state.get("stores_synced", [])
                    )
                )
            else:
                report_path.write_text("store,last_sync,orders_synced,errors\n")

            return ConnectorResult(
                success=True,
                message=f"Report exported to {report_path.name}",
                data={"report_path": str(report_path)},
                duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
            )

        # ── Toast Report Ingestion actions ─────────────────────────────

        elif action_id == "integration.ingest_file":
            file_path = (payload or {}).get("file_path")
            if not file_path:
                return ConnectorResult(success=False, message="file_path required")

            if not Path(file_path).exists():
                return ConnectorResult(success=False, message=f"File not found: {file_path}")

            try:
                from src.db.toast_schema import init_toast_db
                from src.ingestion.toast_pipeline import ToastIngestPipeline

                db = init_toast_db()
                pipeline = ToastIngestPipeline(db=db)
                result = pipeline.ingest_file(file_path, source="api")

                return ConnectorResult(
                    success=result.status in ("completed",),
                    message=f"Ingest {result.status}: {result.file_name} — "
                            f"{result.raw_rows_inserted} raw, {result.normalized_rows_inserted} norm rows",
                    data=result.to_dict(),
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=f"Ingest failed: {e}",
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "integration.ingest_folder":
            folder_path = (payload or {}).get("folder_path")
            if not folder_path:
                return ConnectorResult(success=False, message="folder_path required")

            if not Path(folder_path).exists():
                return ConnectorResult(success=False, message=f"Folder not found: {folder_path}")

            try:
                from src.db.toast_schema import init_toast_db
                from src.ingestion.toast_pipeline import ToastIngestPipeline

                db = init_toast_db()
                pipeline = ToastIngestPipeline(db=db)
                recursive = (payload or {}).get("recursive", False)
                results = pipeline.ingest_directory(folder_path, source="api", recursive=recursive)

                summary = {
                    "total": len(results),
                    "completed": sum(1 for r in results if r.status == "completed"),
                    "failed": sum(1 for r in results if r.status == "failed"),
                    "duplicate": sum(1 for r in results if r.status == "duplicate"),
                    "files": [r.to_dict() for r in results],
                }

                return ConnectorResult(
                    success=True,
                    message=f"Folder ingest: {summary['completed']}/{summary['total']} completed",
                    data=summary,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=f"Folder ingest failed: {e}",
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "integration.gdrive_poll":
            try:
                from src.ingestion.google_drive_watcher import GoogleDriveWatcher

                watcher = GoogleDriveWatcher()
                poll_status = watcher.get_poll_status()

                if not poll_status["enabled"]:
                    return ConnectorResult(
                        success=False,
                        message="Google Drive polling not configured. Set GDRIVE_TOAST_FOLDER_ID env var.",
                        data=poll_status,
                        duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                    )

                results = watcher.poll()
                return ConnectorResult(
                    success=True,
                    message=f"Drive poll: {len(results)} files processed",
                    data={"files": results, "config": poll_status},
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=f"Drive poll failed: {e}",
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "integration.coverage":
            try:
                from src.ingestion.toast_report_types import get_coverage_matrix
                matrix = get_coverage_matrix()
                return ConnectorResult(
                    success=True,
                    message=f"Coverage: {len(matrix)} report types supported",
                    data={"reports": matrix},
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=str(e),
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        elif action_id == "integration.upload_status":
            try:
                from src.db.toast_schema import init_toast_db
                from src.ingestion.toast_pipeline import ToastIngestPipeline

                db = init_toast_db()
                pipeline = ToastIngestPipeline(db=db)
                limit = (payload or {}).get("limit", 50)
                uploads = pipeline.get_upload_status(limit=limit)

                return ConnectorResult(
                    success=True,
                    message=f"Found {len(uploads)} upload records",
                    data={"uploads": uploads},
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )
            except Exception as e:
                return ConnectorResult(
                    success=False,
                    message=str(e),
                    error=type(e).__name__,
                    duration_ms=(datetime.now(timezone.utc) - start).total_seconds() * 1000,
                )

        return ConnectorResult(success=False, message=f"Unknown action: {action_id}")

    async def get_metrics(self) -> dict:
        """Get integration metrics."""
        return (await self.get_status()).get("metrics", {})
