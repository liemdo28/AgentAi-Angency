"""
google_drive_watcher.py — Watch Google Drive folders for new Toast report uploads.

Expected folder structure:
  /ToastUploads/Brand/Store/YYYY/MM/
    2026-04-01_OrderDetails_Store01.csv
    2026-04-01_PaymentDetails_Store01.csv
    ...

Uses Google Drive API via service account (GOOGLE_APPLICATION_CREDENTIALS).
Polls for new files, downloads to temp, feeds into ToastIngestPipeline.
Tracks processed files by google_file_id in upload_files table.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# File naming convention regex
# Example: 2026-04-01_OrderDetails_Store01.csv
_FILE_NAME_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})_(\w+?)_(.+)\.(csv|xlsx|xls|tsv)$",
    re.IGNORECASE,
)


class GoogleDriveWatcher:
    """
    Watches Google Drive folders for new Toast report files.

    Usage:
        watcher = GoogleDriveWatcher(root_folder_id="1abc...")
        results = watcher.poll()  # returns list of IngestResult
    """

    def __init__(
        self,
        root_folder_id: str | None = None,
        credentials_path: str | None = None,
        db_path: str | None = None,
    ):
        """
        Parameters
        ----------
        root_folder_id : Google Drive folder ID for /ToastUploads/
        credentials_path : path to service account JSON key
        db_path : path to Toast DB (default: data/toast.db)
        """
        self._root_folder_id = root_folder_id or os.getenv("GDRIVE_TOAST_FOLDER_ID", "")
        self._credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        self._db_path = db_path
        self._service = None

    def _get_service(self) -> Any:
        """Lazy-init Google Drive API service."""
        if self._service is not None:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            if not self._credentials_path or not Path(self._credentials_path).exists():
                raise FileNotFoundError(
                    f"Google credentials not found at: {self._credentials_path}. "
                    f"Set GOOGLE_APPLICATION_CREDENTIALS env var."
                )

            creds = service_account.Credentials.from_service_account_file(
                self._credentials_path,
                scopes=["https://www.googleapis.com/auth/drive.readonly"],
            )
            self._service = build("drive", "v3", credentials=creds)
            return self._service

        except ImportError:
            raise ImportError(
                "google-api-python-client and google-auth required. "
                "Install with: pip install google-api-python-client google-auth"
            )

    def _list_files_in_folder(self, folder_id: str, recursive: bool = True) -> list[dict]:
        """
        List all files in a Google Drive folder.
        Returns list of {id, name, mimeType, parents, modifiedTime}.
        """
        service = self._get_service()
        all_files: list[dict] = []
        folders_to_scan = [folder_id]

        while folders_to_scan:
            fid = folders_to_scan.pop()
            page_token = None

            while True:
                response = service.files().list(
                    q=f"'{fid}' in parents and trashed = false",
                    fields="nextPageToken, files(id, name, mimeType, parents, modifiedTime, size)",
                    pageSize=100,
                    pageToken=page_token,
                ).execute()

                for f in response.get("files", []):
                    if f["mimeType"] == "application/vnd.google-apps.folder":
                        if recursive:
                            folders_to_scan.append(f["id"])
                    else:
                        all_files.append(f)

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        return all_files

    def _download_file(self, file_id: str, filename: str, dest_dir: str) -> str:
        """Download a file from Google Drive to local path."""
        service = self._get_service()
        from googleapiclient.http import MediaIoBaseDownload
        import io

        request = service.files().get_media(fileId=file_id)
        dest_path = os.path.join(dest_dir, filename)

        with open(dest_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        logger.info("Downloaded: %s -> %s", filename, dest_path)
        return dest_path

    def _is_already_processed(self, google_file_id: str) -> bool:
        """Check if a Google Drive file has already been ingested."""
        from src.db.toast_schema import get_toast_db

        db = get_toast_db(self._db_path)
        row = db.execute(
            "SELECT id, status FROM upload_files WHERE google_file_id = ?",
            (google_file_id,),
        ).fetchone()
        if row and row["status"] in ("completed", "duplicate"):
            return True
        return False

    def _extract_store_hint(self, file_path_parts: list[str]) -> str | None:
        """
        Try to extract store hint from folder structure.
        Expected: /ToastUploads/Brand/Store/YYYY/MM/filename
        """
        # Look for store-like parts in the path
        from src.db.toast_schema import get_toast_db
        db = get_toast_db(self._db_path)

        for part in file_path_parts:
            norm = part.strip().lower()
            row = db.execute(
                "SELECT store_id FROM store_aliases WHERE alias = ?", (norm,)
            ).fetchone()
            if row:
                return row["store_id"]

        return None

    def poll(self) -> list[dict]:
        """
        Poll Google Drive for new files and ingest them.

        Returns list of IngestResult dicts.
        """
        if not self._root_folder_id:
            logger.warning("No GDRIVE_TOAST_FOLDER_ID configured, skipping poll")
            return []

        logger.info("Polling Google Drive folder: %s", self._root_folder_id)

        try:
            files = self._list_files_in_folder(self._root_folder_id)
        except Exception as exc:
            logger.error("Failed to list Drive files: %s", exc)
            return [{"status": "error", "message": str(exc)}]

        results = []
        new_files = []

        for f in files:
            ext = Path(f["name"]).suffix.lower()
            if ext not in (".csv", ".xlsx", ".xls", ".tsv"):
                continue
            if self._is_already_processed(f["id"]):
                continue
            new_files.append(f)

        if not new_files:
            logger.info("No new files found in Google Drive")
            return []

        logger.info("Found %d new files to ingest", len(new_files))

        # Download and ingest each file
        from src.ingestion.toast_pipeline import ToastIngestPipeline
        from src.db.toast_schema import get_toast_db

        db = get_toast_db(self._db_path)
        pipeline = ToastIngestPipeline(db=db)

        with tempfile.TemporaryDirectory(prefix="toast_gdrive_") as tmpdir:
            for f in new_files:
                try:
                    local_path = self._download_file(f["id"], f["name"], tmpdir)

                    # Try to extract store hint from parent folder names
                    parent_names = self._get_parent_names(f.get("parents", []))
                    store_hint = self._extract_store_hint(parent_names)

                    result = pipeline.ingest_file(
                        filepath=local_path,
                        source="gdrive",
                        google_file_id=f["id"],
                        store_hint=store_hint,
                    )
                    results.append(result.to_dict())

                except Exception as exc:
                    logger.error("Failed to process Drive file %s: %s", f["name"], exc)
                    results.append({
                        "file_name": f["name"],
                        "google_file_id": f["id"],
                        "status": "error",
                        "errors": [str(exc)],
                    })

        logger.info(
            "Drive poll complete: %d files processed, %d success",
            len(results),
            sum(1 for r in results if r.get("status") == "completed"),
        )
        return results

    def _get_parent_names(self, parent_ids: list[str]) -> list[str]:
        """Get folder names for parent IDs (for store hint extraction)."""
        if not parent_ids:
            return []
        names = []
        service = self._get_service()
        for pid in parent_ids:
            try:
                folder = service.files().get(fileId=pid, fields="name").execute()
                names.append(folder.get("name", ""))
            except Exception:
                pass
        return names

    def get_poll_status(self) -> dict:
        """Return current status of the Drive watcher."""
        return {
            "root_folder_id": self._root_folder_id,
            "credentials_configured": bool(self._credentials_path and Path(self._credentials_path).exists()),
            "enabled": bool(self._root_folder_id),
        }


def parse_file_name_convention(filename: str) -> dict[str, str] | None:
    """
    Parse a file following the naming convention:
      YYYY-MM-DD_ReportType_StoreName.csv

    Returns dict with date, report_type, store_name, extension
    or None if filename doesn't match.
    """
    match = _FILE_NAME_PATTERN.match(filename)
    if not match:
        return None
    return {
        "date": match.group(1),
        "report_type": match.group(2),
        "store_name": match.group(3),
        "extension": match.group(4),
    }
