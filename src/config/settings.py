"""ENV variable loader for AI Workers."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


class Settings:
    """Global settings loaded from environment variables."""

    # ── LLM Providers ──────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3")
    OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "ollama")  # no real key needed

    # ── Provider Fallback Order ────────────────────────────────────
    LLM_PROVIDER_ORDER: list[str] = [
        p.strip() for p in os.getenv("LLM_PROVIDER_ORDER", "anthropic,openai,ollama").split(",")
    ]

    # ── Web Search ────────────────────────────────────────────────
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")
    SERP_API_KEY: str = os.getenv("SERP_API_KEY", "")

    # ── Email (SMTP) ──────────────────────────────────────────────
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "agency@example.com")

    # ── SendGrid (alternative) ────────────────────────────────────
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")

    # ── Storage ───────────────────────────────────────────────────
    STORAGE_TYPE: str = os.getenv("STORAGE_TYPE", "local")  # "local" | "s3"
    STORAGE_LOCAL_PATH: str = os.getenv("STORAGE_LOCAL_PATH", "./storage")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "")
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")

    # ── Agent Settings ────────────────────────────────────────────
    DEFAULT_SLA_HOURS: int = 24
    SCORE_THRESHOLD: float = 98.0
    MAX_ROUTE_RETRIES: int = 3
    RESEARCH_MAX_RESULTS: int = 10
    RESEARCH_TIMEOUT_SECONDS: int = 30

    # ── FastAPI ───────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    API_DEBUG: bool = os.getenv("API_DEBUG", "false").lower() == "true"

    @classmethod
    def is_provider_available(cls, provider: str) -> bool:
        """Check if a provider's API key is configured."""
        if provider == "anthropic":
            return bool(cls.ANTHROPIC_API_KEY)
        elif provider == "openai":
            return bool(cls.OPENAI_API_KEY)
        elif provider == "ollama":
            # Ollama is "available" if the base URL is reachable
            return bool(cls.OLLAMA_BASE_URL)
        return False

    @property
    def available_providers(self) -> list[str]:
        """Return list of providers that have API keys configured."""
        return [p for p in self.LLM_PROVIDER_ORDER if self.is_provider_available(p)]


SETTINGS = Settings()
