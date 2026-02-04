"""Settings for the Hemma embedding offload server."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OffloadServerSettings(BaseSettings):
    """Settings for the research offload server."""

    model_config = SettingsConfigDict(extra="ignore")

    OFFLOAD_HTTP_HOST: str = Field(default="0.0.0.0")
    OFFLOAD_HTTP_PORT: int = Field(default=9000, ge=1, le=65535)
    OFFLOAD_HTTP_MAX_WORKERS: int = Field(
        default=1,
        ge=1,
        le=64,
        description="Max concurrent extract computations (ThreadPoolExecutor worker count).",
    )

    OFFLOAD_EMBEDDING_MODEL_NAME: str = Field(default="microsoft/deberta-v3-base")
    OFFLOAD_EMBEDDING_MAX_LENGTH: int = Field(default=512, ge=8, le=4096)
    OFFLOAD_EMBEDDING_BATCH_SIZE: int = Field(default=32, ge=1, le=256)
    OFFLOAD_TORCH_DEVICE: str | None = Field(
        default=None,
        description="Optional torch device override (e.g. 'cuda', 'cpu').",
    )

    OFFLOAD_SPACY_N_PROCESS: int = Field(
        default=1,
        ge=1,
        le=32,
        description=(
            "spaCy n_process for nlp.pipe. Increase to utilize more CPU cores for parsing."
        ),
    )
    OFFLOAD_SPACY_PIPE_BATCH_SIZE: int = Field(
        default=32,
        ge=1,
        le=512,
        description="spaCy pipe batch_size for parsing throughput tuning.",
    )

    OFFLOAD_LANGUAGE_TOOL_URL: str = Field(
        default="http://language_tool_service:8085",
        description="Internal base URL for language_tool_service (Hemma compose DNS).",
    )
    OFFLOAD_LANGUAGE_TOOL_JAR_VERSION: str = Field(
        default="",
        description=(
            "Required input for server_fingerprint cache safety. "
            "Set to the LanguageTool JAR version deployed in language_tool_service "
            "(e.g. '6.3')."
        ),
    )

    OFFLOAD_EXTRACT_SCHEMA_VERSION: int = Field(default=1, ge=1)
    OFFLOAD_EXTRACT_MAX_ITEMS: int = Field(default=64, ge=1, le=512)
    OFFLOAD_EXTRACT_MAX_REQUEST_BYTES: int = Field(default=900_000, ge=10_000, le=50_000_000)
    OFFLOAD_EXTRACT_MAX_RESPONSE_BYTES: int = Field(default=8_000_000, ge=100_000, le=200_000_000)
    OFFLOAD_LANGUAGE_TOOL_MAX_CONCURRENCY: int = Field(default=16, ge=1, le=64)

    OFFLOAD_GIT_SHA: str | None = Field(
        default=None,
        description="Optional git SHA to include in meta.json for traceability.",
    )


settings = OffloadServerSettings()
