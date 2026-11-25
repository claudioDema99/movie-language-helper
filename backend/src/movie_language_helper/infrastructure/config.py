"""Typed startup configuration and bounded safety defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated local-MVP settings loaded once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="MLH_",
        env_file=".env",
        extra="ignore",
        frozen=True,
    )

    upload_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    transcript_max_cues: int = Field(default=20_000, ge=1)
    transcript_max_characters_per_cue: int = Field(default=10_000, ge=1)
    transcript_max_total_characters: int = Field(default=2_000_000, ge=1)
    session_ttl_seconds: int = Field(default=30 * 60, ge=1, le=24 * 60 * 60)
    session_capacity: int = Field(default=100, ge=1, le=10_000)
    preview_radius_ms: int = Field(default=15_000, ge=1, le=60_000)
    preview_cue_limit: int = Field(default=20, ge=1, le=100)
    max_sync_offset_ms: int = Field(default=10 * 60 * 1000, ge=0)
    max_analysis_interval_ms: int = Field(default=10 * 60 * 1000, ge=1)
    context_adjacent_cues: int = Field(default=2, ge=0, le=10)
    context_window_ms: int = Field(default=30_000, ge=0, le=120_000)
    default_item_limit: int = Field(default=12, ge=1, le=30)
    max_item_limit: int = Field(default=30, ge=1, le=100)
    analyzer_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    lexicon_analyzer_enabled: bool = False
    openai_enabled: bool = False
    openai_risk_acknowledged: bool = False
    openai_api_key: SecretStr | None = None
    openai_api_key_file: Path | None = None
    openai_model: str | None = None
    openai_max_output_tokens: int = Field(default=2_000, ge=100, le=20_000)
    subdl_enabled: bool = False
    subdl_risk_acknowledged: bool = False
    subdl_api_key: SecretStr | None = None
    subdl_api_key_file: Path | None = None
    subdl_base_url: str = "https://api.subdl.com"
    subdl_allowed_download_hosts: tuple[str, ...] = (
        "api.subdl.com",
        "dl.subdl.com",
    )
    subdl_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    provider_download_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    provider_archive_max_members: int = Field(default=100, ge=1, le=100)
    provider_archive_max_uncompressed_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    provider_archive_max_ratio: int = Field(default=100, ge=1, le=1_000)
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    deployment_profile: Literal["local", "private"] = "local"
    private_access_token: SecretStr | None = None
    private_access_token_file: Path | None = None
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    request_max_bytes: int = Field(default=11 * 1024 * 1024, ge=1)
    rate_limit_requests: int = Field(default=120, ge=1, le=100_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)

    @model_validator(mode="after")
    def validate_related_limits(self) -> Settings:
        """Reject contradictory settings during startup."""
        for secret_field, file_field in (
            ("openai_api_key", "openai_api_key_file"),
            ("subdl_api_key", "subdl_api_key_file"),
            ("private_access_token", "private_access_token_file"),
        ):
            if (
                getattr(self, secret_field) is None
                and (secret_path := getattr(self, file_field)) is not None
            ):
                value = secret_path.read_text(encoding="utf-8").strip()
                if not value:
                    raise ValueError(f"{file_field} must not be empty")
                object.__setattr__(self, secret_field, SecretStr(value))
        if self.default_item_limit > self.max_item_limit:
            raise ValueError("default item limit cannot exceed maximum item limit")
        if not self.cors_origins or any(
            not origin.strip() for origin in self.cors_origins
        ):
            raise ValueError("CORS origins must contain non-blank allowlist entries")
        if "*" in self.cors_origins:
            raise ValueError("wildcard CORS origin is not allowed")
        if self.openai_enabled and (
            not self.openai_risk_acknowledged
            or self.openai_api_key is None
            or not (self.openai_model or "").strip()
        ):
            raise ValueError(
                "OpenAI requires risk acknowledgement, an API key, "
                "and an explicit model"
            )
        if self.subdl_enabled and (
            not self.subdl_risk_acknowledged or self.subdl_api_key is None
        ):
            raise ValueError("SubDL requires risk acknowledgement and an API key")
        if not self.subdl_base_url.startswith("https://"):
            raise ValueError("SubDL base URL must use HTTPS")
        if not self.subdl_allowed_download_hosts or any(
            not host.strip() for host in self.subdl_allowed_download_hosts
        ):
            raise ValueError("SubDL download hosts must be a non-blank allowlist")
        if self.deployment_profile == "private" and (
            self.private_access_token is None
            or len(self.private_access_token.get_secret_value()) < 32
        ):
            raise ValueError("private deployment requires an access token of 32+ chars")
        if (
            not self.trusted_hosts
            or "*" in self.trusted_hosts
            or any(not host.strip() for host in self.trusted_hosts)
        ):
            raise ValueError("trusted hosts must be a non-blank allowlist")
        if self.request_max_bytes < self.upload_max_bytes:
            raise ValueError("request byte limit cannot be below upload byte limit")
        return self
