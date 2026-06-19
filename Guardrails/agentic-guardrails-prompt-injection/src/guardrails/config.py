"""Runtime-configurable guardrail settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM (Layer 3 guard + intent gap)
    anthropic_api_key: str = Field(default="sk-placeholder")
    guard_model: str = "claude-haiku-4-5-20251001"

    # Database
    database_url: str = "postgresql+asyncpg://guardrails:guardrails@localhost:5438/guardrails"

    # Embeddings (Layer 2)
    embedding_model: str = "all-MiniLM-L6-v2"
    layer2_unsafe_threshold: float = 0.75
    layer2_uncertain_threshold: float = 0.50

    # Layer 3 LLM Guard
    layer3_enabled: bool = True
    layer3_uncertain_only: bool = True

    # Intent gap
    intent_gap_threshold: float = 0.65

    # Sandbox paths (comma-separated)
    allowed_path_prefixes: str = "/home/user/project,/tmp/workspace"
    blocked_path_patterns: str = ".ssh,.aws,.env,/etc/,/root/,/proc/,/sys/"

    # Sandbox network
    allowed_domains: str = "api.github.com,docs.python.org,pypi.org,registry.npmjs.org"

    # Allowed tools for coding assistant scope
    allowed_tools: str = "read_file,write_file,run_code,search_docs,list_directory"

    # Egress
    egress_scan_enabled: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8086
    log_level: str = "INFO"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
