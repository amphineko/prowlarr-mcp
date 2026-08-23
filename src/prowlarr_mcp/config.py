from __future__ import annotations

from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="PROWLARR_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: str = "http://localhost:9696"
    api_key: SecretStr
    timeout_seconds: Annotated[float, Field(gt=0, le=300)] = 60.0
    max_results: Annotated[int, Field(ge=1, le=1000)] = 100

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("PROWLARR_URL must use http:// or https://")
        return normalized
