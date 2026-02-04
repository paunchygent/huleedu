"""Feature extraction pipeline orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
from spacy.language import Language

from scripts.ml_training.essay_scoring.config import (
    EmbeddingConfig,
    FeatureSet,
    OffloadBackend,
    OffloadConfig,
)
from scripts.ml_training.essay_scoring.dataset import EssayRecord
from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix, combine_features
from scripts.ml_training.essay_scoring.features.protocols import (
    EmbeddingExtractorProtocol,
    Tier1ExtractorProtocol,
    Tier2ExtractorProtocol,
    Tier3ExtractorProtocol,
)
from scripts.ml_training.essay_scoring.features.schema import feature_names_for
from scripts.ml_training.essay_scoring.features.spacy_pipeline import load_spacy_model
from scripts.ml_training.essay_scoring.features.tier1_error_readability import (
    Tier1FeatureExtractor,
)
from scripts.ml_training.essay_scoring.features.tier2_syntactic_cohesion import (
    Tier2FeatureExtractor,
)
from scripts.ml_training.essay_scoring.features.tier3_structure import Tier3FeatureExtractor
from scripts.ml_training.essay_scoring.logging_utils import ProgressLogger
from scripts.ml_training.essay_scoring.offload.metrics import OffloadMetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class FeaturePipeline:
    """Coordinate extraction of embeddings and tiered features."""

    embedding_config: EmbeddingConfig
    offload: OffloadConfig | None = None
    spacy_model: str = "en_core_web_sm"
    nlp: Language | None = None
    nlp_fast: Language | None = None
    embedder: EmbeddingExtractorProtocol | None = None
    remote_extractor: Any | None = None
    tier1_extractor: Tier1ExtractorProtocol | None = None
    tier2_extractor: Tier2ExtractorProtocol | None = None
    tier3_extractor: Tier3ExtractorProtocol | None = None
    offload_metrics: OffloadMetricsCollector | None = None
    last_offload_meta: Any | None = None

    def extract(self, records: list[EssayRecord], feature_set: FeatureSet) -> FeatureMatrix:
        """Extract features for a collection of records."""

        texts = [record.essay for record in records]
        prompts = [record.question for record in records]

        if self.offload and self.offload.backend == OffloadBackend.HEMMA:
            if not self.offload.offload_service_url:
                raise RuntimeError(
                    "backend=hemma requires offload_service_url (single-tunnel mode)."
                )
            if self.offload.embedding_service_url or self.offload.language_tool_service_url:
                raise RuntimeError(
                    "backend=hemma does not allow embedding_service_url or "
                    "language_tool_service_url. Use offload_service_url only (single-tunnel mode)."
                )

            if self.offload_metrics is None:
                self.offload_metrics = OffloadMetricsCollector()

            from scripts.ml_training.essay_scoring.offload.extract_client import (  # noqa: PLC0415
                RemoteExtractClient,
            )

            if self.remote_extractor is None or not isinstance(
                self.remote_extractor, RemoteExtractClient
            ):
                self.remote_extractor = RemoteExtractClient(
                    base_url=self.offload.offload_service_url,
                    embedding_config=self.embedding_config,
                    offload_config=self.offload,
                    metrics=self.offload_metrics,
                )

            result = self.remote_extractor.extract(texts, prompts, feature_set)
            self.last_offload_meta = result.meta

            if feature_set == FeatureSet.EMBEDDINGS:
                if result.embeddings is None:
                    raise RuntimeError(
                        "Offload returned no embeddings for embeddings-only feature set."
                    )
                return FeatureMatrix(
                    matrix=result.embeddings,
                    feature_names=feature_names_for(feature_set, result.embeddings.shape[1]),
                )

            if feature_set == FeatureSet.HANDCRAFTED:
                if result.handcrafted is None:
                    raise RuntimeError("Offload returned no handcrafted features.")
                return FeatureMatrix(
                    matrix=result.handcrafted,
                    feature_names=feature_names_for(feature_set, 0),
                )

            if result.embeddings is None or result.handcrafted is None:
                raise RuntimeError(
                    "Offload returned incomplete feature payload for combined feature set."
                )
            matrix = np.concatenate([result.embeddings, result.handcrafted], axis=1)
            return FeatureMatrix(
                matrix=matrix,
                feature_names=feature_names_for(feature_set, result.embeddings.shape[1]),
            )

        if self.offload and (
            self.offload.embedding_service_url or self.offload.language_tool_service_url
        ):
            if self.offload_metrics is None:
                self.offload_metrics = OffloadMetricsCollector()

        # When offload is configured, prefer reusing the same embedding extractor for:
        # - the main embedding matrix (FeatureSet.EMBEDDINGS / COMBINED)
        # - Tier2 sentence/prompt similarity features (FeatureSet.HANDCRAFTED / COMBINED)
        tier2_embedding_extractor: EmbeddingExtractorProtocol | None = None
        if self.offload and self.offload.embedding_service_url:
            from scripts.ml_training.essay_scoring.offload.embedding_client import (
                RemoteEmbeddingClient,
            )

            if self.embedder is None or not isinstance(self.embedder, RemoteEmbeddingClient):
                self.embedder = RemoteEmbeddingClient(
                    base_url=self.offload.embedding_service_url,
                    embedding_config=self.embedding_config,
                    offload_config=self.offload,
                    metrics=self.offload_metrics,
                )
            tier2_embedding_extractor = self.embedder

        embedding_vectors = None
        if feature_set in {FeatureSet.EMBEDDINGS, FeatureSet.COMBINED}:
            if self.embedder is None:
                if self.offload and self.offload.embedding_service_url:
                    raise RuntimeError("Embedding offload is configured but embedder is missing.")
                else:
                    from scripts.ml_training.essay_scoring.features.embeddings import (  # noqa: PLC0415
                        DebertaEmbedder,
                    )

                    self.embedder = DebertaEmbedder(self.embedding_config)
            start = time.monotonic()
            logger.info("Embedding extraction start (n=%d)", len(texts))
            embedding_vectors = self.embedder.embed(texts)
            elapsed = time.monotonic() - start
            logger.info(
                "Embedding extraction complete (shape=%s) in %.2fs",
                embedding_vectors.shape,
                elapsed,
            )

        tier1_features = None
        tier2_features = None
        tier3_features = None
        if feature_set in {FeatureSet.HANDCRAFTED, FeatureSet.COMBINED}:
            if self.nlp is None and self.tier1_extractor is None:
                self.nlp = load_spacy_model(self.spacy_model, enable_readability=True)
            if self.nlp_fast is None and (
                self.tier2_extractor is None or self.tier3_extractor is None
            ):
                self.nlp_fast = load_spacy_model(self.spacy_model, enable_readability=False)
            if self.tier1_extractor is None:
                self.tier1_extractor = Tier1FeatureExtractor(
                    spacy_model=self.spacy_model,
                    nlp=self.nlp,
                    language_tool_url=self.offload.language_tool_service_url
                    if self.offload
                    else None,
                    request_timeout_s=self.offload.request_timeout_s if self.offload else 60.0,
                    language_tool_cache_dir=(
                        self.offload.language_tool_cache_dir if self.offload else None
                    ),
                    language_tool_max_concurrency=(
                        self.offload.language_tool_max_concurrency if self.offload else 10
                    ),
                    metrics=self.offload_metrics,
                )
            if self.tier2_extractor is None:
                self.tier2_extractor = Tier2FeatureExtractor(
                    spacy_model=self.spacy_model,
                    nlp=self.nlp_fast,
                    embedding_extractor=tier2_embedding_extractor,
                )
            if self.tier3_extractor is None:
                self.tier3_extractor = Tier3FeatureExtractor(
                    spacy_model=self.spacy_model,
                    nlp=self.nlp_fast,
                )

            logger.info("Tier1 extraction start (n=%d)", len(texts))
            tier1_start = time.monotonic()
            tier1_features = self.tier1_extractor.extract_batch(texts)
            logger.info("Tier1 extraction complete in %.2fs", time.monotonic() - tier1_start)

            logger.info("Tier2 extraction start (n=%d)", len(texts))
            tier2_start = time.monotonic()
            tier2_features = self.tier2_extractor.extract_batch(texts, prompts)
            logger.info("Tier2 extraction complete in %.2fs", time.monotonic() - tier2_start)

            tier3_features = []
            logger.info("Tier3 extraction start (n=%d)", len(texts))
            tier3_start = time.monotonic()
            tier3_progress = ProgressLogger(logger, "Tier3", len(texts))
            for index, (text, prompt) in enumerate(zip(texts, prompts, strict=True)):
                logger.info(
                    "Tier3 item %d/%d start (chars=%d, prompt_chars=%d)",
                    index + 1,
                    len(texts),
                    len(text),
                    len(prompt),
                )
                tier3_features.append(self.tier3_extractor.extract(text, prompt))
                tier3_progress.update(index)
            logger.info("Tier3 extraction complete in %.2fs", time.monotonic() - tier3_start)

        return combine_features(
            embedding_vectors=embedding_vectors,
            tier1=tier1_features,
            tier2=tier2_features,
            tier3=tier3_features,
            feature_set=feature_set,
        )
