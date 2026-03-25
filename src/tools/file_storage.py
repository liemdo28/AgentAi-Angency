"""
File Storage — Local + S3 driver for creative assets, reports, and data files.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Optional

logger = logging.getLogger(__name__)


@dataclass
class StoredFile:
    path: str  # relative path within storage root
    url: str  # public or signed URL (local: file://, S3: https://)
    size_bytes: int
    content_type: str
    checksum: str  # SHA-256
    stored_at: str


class FileStorage:
    """
    Unified file storage with local filesystem and S3 backends.

    Priority:
    1. S3 (if AWS_ACCESS_KEY_ID + S3_BUCKET set)
    2. Local filesystem (LOCAL_STORAGE_PATH or ./storage)

    Usage:
        storage = FileStorage()
        result = storage.put("campaigns/c001/report.pdf", data, content_type="application/pdf")
        content = storage.get("campaigns/c001/report.pdf")
        url = storage.get_url("campaigns/c001/report.pdf")
    """

    LOCAL_ROOT = "./storage"

    def __init__(
        self,
        local_path: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "",
        aws_access_key: Optional[str] = None,
        aws_secret_key: Optional[str] = None,
        aws_region: str = "us-east-1",
        public_base_url: Optional[str] = None,
    ) -> None:
        self._local_root = Path(local_path or os.getenv("LOCAL_STORAGE_PATH", self.LOCAL_ROOT))
        self._s3_bucket = s3_bucket or os.getenv("S3_BUCKET")
        self._s3_prefix = s3_prefix or os.getenv("S3_PREFIX", "")
        self._aws_access = aws_access_key or os.getenv("AWS_ACCESS_KEY_ID")
        self._aws_secret = aws_secret_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self._aws_region = aws_region
        self._public_base = public_base_url or os.getenv("PUBLIC_FILE_URL", "")

        self._use_s3 = bool(self._s3_bucket and self._aws_access)

        if not self._use_s3:
            self._local_root.mkdir(parents=True, exist_ok=True)
            logger.info("FileStorage: using local path %s", self._local_root)
        else:
            logger.info("FileStorage: using S3 bucket %s", self._s3_bucket)

    # ── Write ───────────────────────────────────────────────────────────

    def put(
        self,
        path: str,
        data: bytes | BinaryIO,
        content_type: str = "application/octet-stream",
        metadata: Optional[dict[str, str]] = None,
    ) -> StoredFile:
        """
        Store a file. Returns StoredFile with path, url, size, checksum.
        """
        if isinstance(data, bytes):
            body = data
        else:
            body = data.read()

        checksum = hashlib.sha256(body).hexdigest()
        size = len(body)
        stored_at = datetime.now(timezone.utc).isoformat()

        if self._use_s3:
            self._put_s3(path, body, content_type, metadata)
        else:
            self._put_local(path, body)

        url = self._build_url(path)
        return StoredFile(
            path=path,
            url=url,
            size_bytes=size,
            content_type=content_type,
            checksum=checksum,
            stored_at=stored_at,
        )

    def _put_local(self, path: str, body: bytes) -> None:
        full = self._local_root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(body)
        logger.debug("Stored file locally: %s", full)

    def _put_s3(
        self,
        path: str,
        body: bytes,
        content_type: str,
        metadata: Optional[dict[str, str]],
    ) -> None:
        try:
            import boto3
        except ImportError:
            logger.error("boto3 not installed. S3 storage unavailable.")
            raise

        s3_key = f"{self._s3_prefix}/{path}".lstrip("/")
        extra: dict[str, Any] = {"ContentType": content_type}
        if metadata:
            extra["Metadata"] = metadata

        client = boto3.client(
            "s3",
            aws_access_key_id=self._aws_access,
            aws_secret_access_key=self._aws_secret,
            region_name=self._aws_region,
        )
        client.put_object(
            Bucket=self._s3_bucket,
            Key=s3_key,
            Body=body,
            **extra,
        )
        logger.debug("Stored file in S3: s3://%s/%s", self._s3_bucket, s3_key)

    # ── Read ────────────────────────────────────────────────────────────

    def get(self, path: str) -> Optional[bytes]:
        """Read a file. Returns None if not found."""
        if self._use_s3:
            return self._get_s3(path)
        else:
            return self._get_local(path)

    def _get_local(self, path: str) -> Optional[bytes]:
        full = self._local_root / path
        if full.exists():
            return full.read_bytes()
        return None

    def _get_s3(self, path: str) -> Optional[bytes]:
        try:
            import boto3
        except ImportError:
            return None

        s3_key = f"{self._s3_prefix}/{path}".lstrip("/")
        client = boto3.client(
            "s3",
            aws_access_key_id=self._aws_access,
            aws_secret_access_key=self._aws_secret,
            region_name=self._aws_region,
        )
        try:
            obj = client.get_object(Bucket=self._s3_bucket, Key=s3_key)
            return obj["Body"].read()
        except Exception:
            return None

    # ── URL ────────────────────────────────────────────────────────────

    def get_url(self, path: str, expires_in: int = 3600) -> str:
        """Get a URL for the file. Local = file://, S3 = signed URL."""
        if self._use_s3:
            return self._s3_presigned_url(path, expires_in)
        else:
            return f"file://{self._local_root / path}"

    def _build_url(self, path: str) -> str:
        if self._public_base:
            return f"{self._public_base.rstrip('/')}/{path}"
        elif self._use_s3:
            s3_key = f"{self._s3_prefix}/{path}".lstrip("/")
            return f"https://{self._s3_bucket}.s3.{self._aws_region}.amazonaws.com/{s3_key}"
        else:
            return f"file://{self._local_root / path}"

    def _s3_presigned_url(self, path: str, expires_in: int) -> str:
        import boto3
        s3_key = f"{self._s3_prefix}/{path}".lstrip("/")
        client = boto3.client(
            "s3",
            aws_access_key_id=self._aws_access,
            aws_secret_access_key=self._aws_secret,
            region_name=self._aws_region,
        )
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._s3_bucket, "Key": s3_key},
            ExpiresIn=expires_in,
        )

    # ── Delete ─────────────────────────────────────────────────────────

    def delete(self, path: str) -> bool:
        """Delete a file. Returns True if deleted."""
        if self._use_s3:
            return self._delete_s3(path)
        else:
            return self._delete_local(path)

    def _delete_local(self, path: str) -> bool:
        full = self._local_root / path
        if full.exists():
            full.unlink()
            return True
        return False

    def _delete_s3(self, path: str) -> bool:
        try:
            import boto3
        except ImportError:
            return False
        s3_key = f"{self._s3_prefix}/{path}".lstrip("/")
        client = boto3.client(
            "s3",
            aws_access_key_id=self._aws_access,
            aws_secret_access_key=self._aws_secret,
            region_name=self._aws_region,
        )
        try:
            client.delete_object(Bucket=self._s3_bucket, Key=s3_key)
            return True
        except Exception:
            return False

    # ── List ────────────────────────────────────────────────────────────

    def list(self, prefix: str = "") -> list[str]:
        """List files under a prefix."""
        if self._use_s3:
            return self._list_s3(prefix)
        else:
            root = self._local_root / prefix
            if not root.exists():
                return []
            return [str(p.relative_to(self._local_root)) for p in root.rglob("*") if p.is_file()]

    def _list_s3(self, prefix: str) -> list[str]:
        try:
            import boto3
        except ImportError:
            return []
        s3_prefix = f"{self._s3_prefix}/{prefix}".lstrip("/")
        client = boto3.client(
            "s3",
            aws_access_key_id=self._aws_access,
            aws_secret_access_key=self._aws_secret,
            region_name=self._aws_region,
        )
        try:
            resp = client.list_objects_v2(Bucket=self._s3_bucket, Prefix=s3_prefix)
            return [obj["Key"] for obj in resp.get("Contents", [])]
        except Exception:
            return []
