"""Tests for offload meta schema alias handling.

Purpose:
    Ensure the Mac-side `RemoteExtractClient` can validate and consume cached offload metadata
    across purely *naming* changes in Tier 1, without forcing expensive recomputation.

Relationships:
    - Validates `scripts.ml_training.essay_scoring.offload.extract_client.RemoteExtractClient`
      schema checks against
      `scripts.ml_training.essay_scoring.features.schema.build_feature_schema`.
"""

from __future__ import annotations

import pytest

from scripts.ml_training.essay_scoring.config import EmbeddingConfig, OffloadBackend, OffloadConfig
from scripts.ml_training.essay_scoring.features.schema import build_feature_schema
from scripts.ml_training.essay_scoring.offload.extract_client import RemoteExtractClient
from scripts.ml_training.essay_scoring.offload.extract_models import (
    ExtractEmbeddingMeta,
    ExtractFeatureSchemaMeta,
    ExtractLanguageToolMeta,
    ExtractMeta,
)


def _client() -> RemoteExtractClient:
    return RemoteExtractClient(
        base_url="http://127.0.0.1:9000",
        embedding_config=EmbeddingConfig(),
        offload_config=OffloadConfig(
            backend=OffloadBackend.HEMMA,
            offload_service_url="http://127.0.0.1:9000",
        ),
    )


def test_validate_meta_accepts_tier1_density_aliases() -> None:
    schema = build_feature_schema(embedding_dim=768)

    legacy_tier1 = [
        "grammar_density",
        "spelling_density",
        "punctuation_density",
        *list(schema.tier1[3:]),
    ]
    legacy_combined = []
    for name in schema.combined:
        if name == "grammar_errors_per_100_words":
            legacy_combined.append("grammar_density")
        elif name == "spelling_errors_per_100_words":
            legacy_combined.append("spelling_density")
        elif name == "punctuation_errors_per_100_words":
            legacy_combined.append("punctuation_density")
        else:
            legacy_combined.append(name)

    meta = ExtractMeta(
        schema_version=1,
        server_fingerprint="test",
        git_sha=None,
        versions={},
        embedding=ExtractEmbeddingMeta(
            model_name="microsoft/deberta-v3-base",
            max_length=512,
            pooling="cls",
            dim=768,
        ),
        language_tool=ExtractLanguageToolMeta(
            language="en-US",
            request_options={},
            service_url="http://language_tool_service:8085",
            jar_version="test",
        ),
        feature_schema=ExtractFeatureSchemaMeta(
            tier1=legacy_tier1,
            tier2=list(schema.tier2),
            tier3=list(schema.tier3),
            combined=legacy_combined,
        ),
    )

    _client()._validate_meta_against_local_schema(meta)


def test_validate_meta_rejects_unknown_tier1_names() -> None:
    schema = build_feature_schema(embedding_dim=768)
    meta = ExtractMeta(
        schema_version=1,
        server_fingerprint="test",
        git_sha=None,
        versions={},
        embedding=ExtractEmbeddingMeta(
            model_name="microsoft/deberta-v3-base",
            max_length=512,
            pooling="cls",
            dim=768,
        ),
        language_tool=ExtractLanguageToolMeta(
            language="en-US",
            request_options={},
            service_url="http://language_tool_service:8085",
            jar_version="test",
        ),
        feature_schema=ExtractFeatureSchemaMeta(
            tier1=["not_a_real_feature", *list(schema.tier1[1:])],
            tier2=list(schema.tier2),
            tier3=list(schema.tier3),
            combined=list(schema.combined),
        ),
    )

    with pytest.raises(RuntimeError, match="tier1 feature schema mismatch"):
        _client()._validate_meta_against_local_schema(meta)
