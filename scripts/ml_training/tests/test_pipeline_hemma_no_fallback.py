from __future__ import annotations

import pytest

from scripts.ml_training.essay_scoring.config import (
    EmbeddingConfig,
    FeatureSet,
    OffloadBackend,
    OffloadConfig,
)
from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.pipeline import FeaturePipeline


def test_pipeline_backend_hemma_requires_offload_service_url() -> None:
    pipeline = FeaturePipeline(
        embedding_config=EmbeddingConfig(),
        offload=OffloadConfig(
            backend=OffloadBackend.HEMMA,
            offload_service_url=None,
            embedding_service_url=None,
            language_tool_service_url=None,
        ),
    )

    records = [
        EssayRecord(
            record_id="r1",
            task_type="1",
            question="Prompt",
            essay="Hello world.",
            overall=6.0,
            component_scores={},
        )
    ]

    with pytest.raises(RuntimeError, match="requires offload_service_url"):
        pipeline.extract(records, FeatureSet.COMBINED)
