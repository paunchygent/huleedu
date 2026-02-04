"""Metadata and fingerprinting for the combined extract endpoint."""

from __future__ import annotations

import hashlib
import json
import platform
from typing import Any

from scripts.ml_training.essay_scoring.features.schema import build_feature_schema
from scripts.ml_training.essay_scoring.offload.extract_models import (
    ExtractEmbeddingMeta,
    ExtractFeatureSchemaMeta,
    ExtractLanguageToolMeta,
    ExtractMeta,
)
from scripts.ml_training.essay_scoring.offload.settings import settings


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gather_versions() -> dict[str, str]:
    from importlib.metadata import version as _dist_version  # noqa: PLC0415

    import numpy as _np  # noqa: PLC0415
    import spacy as _spacy  # noqa: PLC0415
    import textdescriptives as _textdescriptives  # noqa: PLC0415
    import torch as _torch  # noqa: PLC0415
    import transformers as _transformers  # noqa: PLC0415

    versions: dict[str, str] = {
        "python": platform.python_version(),
        "numpy": _np.__version__,
        "torch": _torch.__version__,
        "transformers": _transformers.__version__,
        "spacy": _spacy.__version__,
        "textdescriptives": _textdescriptives.__version__,
    }
    try:
        versions["en_core_web_sm"] = _dist_version("en-core-web-sm")
    except Exception:
        versions["en_core_web_sm"] = "unknown"
    return versions


def server_fingerprint_payload(*, embedding_dim: int) -> dict[str, Any]:
    schema = build_feature_schema(embedding_dim)
    return {
        "schema_version": int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
        "embedding": {
            "model_name": settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            "max_length": int(settings.OFFLOAD_EMBEDDING_MAX_LENGTH),
            "batch_size": int(settings.OFFLOAD_EMBEDDING_BATCH_SIZE),
            "pooling": "cls",
            "dim": int(embedding_dim),
            "torch_device": settings.OFFLOAD_TORCH_DEVICE,
        },
        "language_tool": {
            "language": "en-US",
            "request_options": {},
            "service_url": settings.OFFLOAD_LANGUAGE_TOOL_URL,
            "jar_version": settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION,
        },
        "feature_schema": schema.model_dump(mode="json"),
        "versions": gather_versions(),
    }


def build_meta(*, embedding_dim: int) -> ExtractMeta:
    if not settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION:
        raise RuntimeError(
            "OFFLOAD_LANGUAGE_TOOL_JAR_VERSION is required for cache-safe server_fingerprint."
        )

    fingerprint_payload = server_fingerprint_payload(embedding_dim=embedding_dim)
    fingerprint = sha256_hex(canonical_json_bytes(fingerprint_payload))
    schema = build_feature_schema(embedding_dim)

    return ExtractMeta(
        schema_version=int(settings.OFFLOAD_EXTRACT_SCHEMA_VERSION),
        server_fingerprint=fingerprint,
        git_sha=settings.OFFLOAD_GIT_SHA,
        versions=fingerprint_payload["versions"],
        embedding=ExtractEmbeddingMeta(
            model_name=settings.OFFLOAD_EMBEDDING_MODEL_NAME,
            max_length=int(settings.OFFLOAD_EMBEDDING_MAX_LENGTH),
            pooling="cls",
            dim=int(embedding_dim),
        ),
        language_tool=ExtractLanguageToolMeta(
            language="en-US",
            request_options={},
            service_url=settings.OFFLOAD_LANGUAGE_TOOL_URL,
            jar_version=settings.OFFLOAD_LANGUAGE_TOOL_JAR_VERSION,
        ),
        feature_schema=ExtractFeatureSchemaMeta(
            tier1=list(schema.tier1),
            tier2=list(schema.tier2),
            tier3=list(schema.tier3),
            combined=list(schema.combined),
        ),
    )
