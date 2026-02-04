"""Request/response models for the Hemma combined extract endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scripts.ml_training.essay_scoring.config import FeatureSet


class ExtractRequest(BaseModel):
    """Batch request for combined feature extraction."""

    model_config = ConfigDict(extra="forbid")

    texts: list[str] = Field(..., min_length=1, description="Essay texts to featurize.")
    prompts: list[str] = Field(..., min_length=1, description="Prompt per essay.")
    feature_set: FeatureSet = Field(..., description="Feature set to return.")

    @model_validator(mode="after")
    def _validate_lengths(self) -> "ExtractRequest":
        if len(self.texts) != len(self.prompts):
            raise ValueError(
                "texts and prompts must have the same length "
                f"texts={len(self.texts)} prompts={len(self.prompts)}"
            )
        return self


class ExtractEmbeddingMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    max_length: int
    pooling: str = Field(default="cls")
    dim: int


class ExtractLanguageToolMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str
    request_options: dict[str, str] = Field(default_factory=dict)
    service_url: str
    jar_version: str


class ExtractFeatureSchemaMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier1: list[str]
    tier2: list[str]
    tier3: list[str]
    combined: list[str]


class ExtractMeta(BaseModel):
    """Metadata describing the extraction runtime and feature ordering."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    server_fingerprint: str
    git_sha: str | None

    versions: dict[str, str]
    embedding: ExtractEmbeddingMeta
    language_tool: ExtractLanguageToolMeta
    feature_schema: ExtractFeatureSchemaMeta


class ExtractError(BaseModel):
    """JSON error shape for non-2xx responses."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int
    error: str
    detail: str
    correlation_id: str
    extra: dict[str, Any] = Field(default_factory=dict)
