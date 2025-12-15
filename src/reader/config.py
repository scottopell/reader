"""Application configuration via environment variables."""

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMBackend(str, Enum):
    """LLM backend for scoring."""

    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="READER_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    db_path: Path = Field(
        default=Path.home() / ".config" / "reader" / "reader.db",
        description="Path to SQLite database file",
    )

    # LLM
    llm_backend: LLMBackend = Field(
        default=LLMBackend.OLLAMA,
        description="LLM backend: 'anthropic' or 'ollama'",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for Claude scoring",
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Anthropic model to use",
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL",
    )
    ollama_model: str = Field(
        default="llama3.2",
        description="Ollama model to use for scoring",
    )

    # Email (IMAP)  # noqa: ERA001
    imap_host: str = Field(default="", description="IMAP server hostname")
    imap_user: str = Field(default="", description="IMAP username")
    imap_pass: str = Field(default="", description="IMAP password")

    # Auth
    api_key: str = Field(
        default="",
        description="API key for iOS Shortcuts. If empty, API endpoints are disabled.",
    )
    dangerous_no_web_auth_mode: bool = Field(
        default=False,
        description="Disable web UI authentication (DANGEROUS, dev only)",
    )

    # Background ingestion (REQ-RC-002)
    rss_check_interval_seconds: int = Field(
        default=7200,  # 2 hours
        description="Interval between RSS feed checks in seconds",
    )
    email_check_interval_seconds: int = Field(
        default=7200,  # 2 hours
        description="Interval between email checks in seconds",
    )
    scoring_delay_seconds: float = Field(
        default=0.0,
        description="Delay between scoring operations (prevents GPU overload)",
    )

    # Server
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")


def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()
