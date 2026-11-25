"""Startup configuration, composition, and runtime primitives."""

import asyncio
from datetime import UTC
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from movie_language_helper.infrastructure.config import Settings
from movie_language_helper.infrastructure.container import build_services
from movie_language_helper.infrastructure.runtime import SecureIdGenerator, SystemClock


def test_settings_defaults_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLH_SESSION_CAPACITY", "7")
    settings = Settings()
    assert settings.session_capacity == 7
    assert settings.upload_max_bytes == 2 * 1024 * 1024


@pytest.mark.parametrize(
    "values",
    [
        {"default_item_limit": 2, "max_item_limit": 1},
        {"cors_origins": ()},
        {"cors_origins": ("",)},
        {"cors_origins": ("*",)},
        {"openai_enabled": True},
        {"subdl_enabled": True},
        {"subdl_base_url": "http://api.subdl.test"},
        {"subdl_allowed_download_hosts": ()},
        {"subdl_allowed_download_hosts": ("",)},
        {"deployment_profile": "private"},
        {
            "deployment_profile": "private",
            "private_access_token": SecretStr("too-short"),
        },
        {"trusted_hosts": ()},
        {"trusted_hosts": ("*",)},
        {"request_max_bytes": 1},
    ],
)
def test_settings_reject_unsafe_relationships(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Settings(**values)  # type: ignore[arg-type]


def test_runtime_primitives_produce_utc_and_opaque_ids() -> None:
    now = SystemClock().now()
    first = SecureIdGenerator().new()
    second = SecureIdGenerator().new()
    assert now.tzinfo is UTC
    assert first != second
    assert len(first) >= 20


def test_provider_settings_require_explicit_complete_opt_in() -> None:
    settings = Settings(
        openai_enabled=True,
        openai_risk_acknowledged=True,
        openai_api_key=SecretStr("secret"),
        openai_model="gpt-test-snapshot",
        subdl_enabled=True,
        subdl_risk_acknowledged=True,
        subdl_api_key=SecretStr("secret"),
    )
    assert settings.openai_enabled is True
    assert settings.subdl_enabled is True

    services = build_services(settings)
    assert services.search_movies is not None
    assert services.list_subtitles is not None
    assert services.create_provider_session is not None
    assert len(services.resource_closers) == 2

    async def close() -> None:
        for closer in services.resource_closers:
            await closer()

    asyncio.run(close())


def test_settings_load_private_secret_from_file(tmp_path: Path) -> None:
    path = tmp_path / "access-token"
    path.write_text("file-secret-with-at-least-32-characters\n", encoding="utf-8")
    settings = Settings(
        deployment_profile="private",
        private_access_token_file=path,
    )
    assert settings.private_access_token is not None
    assert settings.private_access_token.get_secret_value() == (
        "file-secret-with-at-least-32-characters"
    )

    path.write_text("", encoding="utf-8")
    with pytest.raises(ValidationError, match="must not be empty"):
        Settings(deployment_profile="private", private_access_token_file=path)
