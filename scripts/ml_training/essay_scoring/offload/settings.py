"""Settings for the Hemma embedding offload server."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OffloadServerSettings(BaseSettings):
    """Settings for the research offload embedding server."""

    model_config = SettingsConfigDict(extra="ignore")

    OFFLOAD_HTTP_HOST: str = Field(default="0.0.0.0")
    OFFLOAD_HTTP_PORT: int = Field(default=9000, ge=1, le=65535)

    OFFLOAD_EMBEDDING_MODEL_NAME: str = Field(default="microsoft/deberta-v3-base")
    OFFLOAD_EMBEDDING_MAX_LENGTH: int = Field(default=512, ge=8, le=4096)
    OFFLOAD_EMBEDDING_BATCH_SIZE: int = Field(default=8, ge=1, le=256)
    OFFLOAD_TORCH_DEVICE: str | None = Field(
        default=None,
        description="Optional torch device override (e.g. 'cuda', 'cpu').",
    )


settings = OffloadServerSettings()
