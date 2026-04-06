"""
Centralized settings for Unified API and all connectors.

Loads from environment variables (.env file).
All connectors MUST read from this file — no scattered env reads.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, get_origin

try:
    from pydantic_settings import BaseSettings
    _has_pydantic_settings = True
except ImportError:
    from pydantic import BaseModel as _PydanticBase
    _has_pydantic_settings = False

    class BaseSettings(_PydanticBase):
        class Config:
            populate_by_name = True


def _find_env_file() -> Path | None:
    """Find .env starting from project root."""
    # src/unified/settings.py → src/unified → src → project root
    current = Path(__file__).resolve()
    for _ in range(5):
        candidate = current / ".env"
        if candidate.exists():
            return candidate
        current = current.parent
    # Also try relative to working dir
    cwd = Path.cwd()
    env = cwd / ".env"
    if env.exists():
        return env
    return None


class Settings(BaseSettings if _has_pydantic_settings else object):
    """
    Central settings for all connectors and the unified API.
    Reads from .env file automatically.
    """

    # ── Paths ──────────────────────────────────────────────
    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = Path(__file__).parent.parent.parent / "data"
    upload_dir: Path = Path(__file__).parent.parent.parent / "data" / "uploads"

    # ── Agency API ─────────────────────────────────────────
    agency_base_url: str = "http://localhost:8000"
    agency_timeout: int = 10

    # ── Marketing (marketing.bakudanramen.com) ────────────
    marketing_base_url: str = "https://marketing.bakudanramen.com"
    marketing_api_token: str = ""
    marketing_timeout: int = 120

    # ── TaskFlow (dashboard.bakudanramen.com) ──────────────
    taskflow_base_url: str = "https://dashboard.bakudanramen.com"
    taskflow_username: str = ""
    taskflow_password: str = ""
    taskflow_timeout: int = 60

    # ── Growth Dashboard (DreamHost PHP API) ─────────────
    growth_base_url: str = "https://marketing.bakudanramen.com/api"
    growth_api_key: str = ""
    growth_timeout: int = 60

    # ── Review MCP (local) ────────────────────────────────
    review_mcp_path: Path = Path(r"E:\Project\Master\review-management-mcp")

    # ── Integration Full (Toast-QB, local) ────────────────
    integration_path: Path = Path(r"E:\Project\Master\integration-full")
    integration_timeout: int = 300  # 5 minutes for sync

    # ── Job Queue ──────────────────────────────────────────
    job_max_retries: int = 3
    job_backoff_seconds: int = 10
    job_default_timeout: int = 300  # 5 minutes default

    # ── Dashboard Web Server ───────────────────────────────
    dashboard_port: int = 3000
    unified_port: int = 8001

    # ── Security ───────────────────────────────────────────
    secret_key: str = "dev-secret-change-in-production"
    allowed_origins: str = "*"  # Comma-separated in production

    # ── File Upload ────────────────────────────────────────
    max_upload_size_mb: int = 50
    allowed_extensions: list[str] = [
        ".csv", ".xlsx", ".xls", ".txt", ".json",
        ".jpg", ".jpeg", ".png", ".pdf"
    ]

    if _has_pydantic_settings:

        class Config:
            env_file = str(_find_env_file()) if _find_env_file() else ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"  # Ignore unknown env vars

    else:
        # Manual .env loading fallback
        @staticmethod
        def _load_env(path: Path) -> None:
            """Load key=value lines from .env file."""
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key.isupper():
                    os.environ.setdefault(key, value)

        def _apply_env_overrides(self, kwargs: dict[str, object]) -> None:
            """Map UPPERCASE env vars onto lowercase settings fields."""
            for field_name, annotation in self.__annotations__.items():
                if field_name in kwargs:
                    setattr(self, field_name, kwargs[field_name])
                    continue
                env_key = field_name.upper()
                if env_key not in os.environ:
                    continue
                raw = os.environ[env_key]
                setattr(self, field_name, self._coerce_env_value(raw, annotation))

        @staticmethod
        def _coerce_env_value(raw: str, annotation: object) -> object:
            """Coerce env strings into the declared field type."""
            origin = get_origin(annotation)
            if annotation is Path:
                return Path(raw)
            if annotation is int:
                return int(raw)
            if annotation is bool:
                return raw.strip().lower() in {"1", "true", "yes", "on"}
            if origin is list:
                value = raw.strip()
                if value.startswith("[") and value.endswith("]"):
                    items = value.strip("[]")
                    return [item.strip().strip('"').strip("'") for item in items.split(",") if item.strip()]
                return [item.strip() for item in value.split(",") if item.strip()]
            return raw

    def __init__(self, **kwargs):
        if _has_pydantic_settings:
            super().__init__(**kwargs)
        else:
            super().__init__()
            env_path = _find_env_file()
            if env_path and env_path.exists():
                self._load_env(env_path)
            self._apply_env_overrides(kwargs)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    @property
    def allowed_extensions_set(self) -> set[str]:
        return set(ext.lower() for ext in self.allowed_extensions)

    def is_allowed_file(self, filename: str) -> bool:
        ext = Path(filename).suffix.lower()
        return ext in self.allowed_extensions_set

    def validate_upload(self, filename: str, size_bytes: int) -> tuple[bool, str]:
        """Validate file before accepting upload. Returns (ok, message)."""
        if not filename:
            return False, "No filename provided"
        ext = Path(filename).suffix.lower()
        if ext not in self.allowed_extensions_set:
            return False, f"File type {ext} not allowed. Allowed: {', '.join(self.allowed_extensions)}"
        max_bytes = self.max_upload_size_mb * 1024 * 1024
        if size_bytes > max_bytes:
            return False, f"File too large. Max size: {self.max_upload_size_mb}MB"
        if size_bytes == 0:
            return False, "Empty file"
        return True, ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance. Call this, don't instantiate directly."""
    return Settings()


# ── Security Helpers ─────────────────────────────────────────

def mask_secret(value: str | None, keep: int = 4) -> str:
    """Mask a secret token for safe logging. Shows last `keep` chars."""
    if not value:
        return "(not set)"
    if len(value) <= keep:
        return "*" * len(value)
    return "*" * (len(value) - keep) + value[-keep:]


def mask_header(value: str | None) -> str:
    """Mask a full Authorization header value."""
    if not value:
        return "(not set)"
    if value.startswith("Bearer "):
        token = value[7:]
        return f"Bearer {mask_secret(token)}"
    if value.startswith("Basic "):
        return "(Basic auth hidden)"
    return mask_secret(value)


def safe_headers(headers: dict | None) -> dict:
    """Return headers with auth values masked for logging."""
    if not headers:
        return {}
    sensitive = {"authorization", "cookie", "x-api-key", "x-auth-token"}
    result = {}
    for k, v in headers.items():
        if k.lower() in sensitive:
            result[k] = mask_header(v)
        else:
            result[k] = v
    return result
