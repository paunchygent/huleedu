"""Tier 2 feature extraction: syntactic complexity, cohesion, prompt relevance.

Tier 2 is the main CPU/GPU-heavy stage in the essay scoring research pipeline:

- CPU: spaCy parsing for dependency features and sentence segmentation
- GPU: DeBERTa embeddings for essay/prompt/sentence/paragraph similarity features

In the Hemma offload server, Tier 2 parsing artifacts (Docs + paragraphs) are
reused by Tier 3 to avoid duplicate spaCy parsing work.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import spacy
from spacy.language import Language
from spacy.tokens import Doc

from scripts.ml_training.essay_scoring.features.protocols import EmbeddingExtractorProtocol
from scripts.ml_training.essay_scoring.features.schema import Tier2Features
from scripts.ml_training.essay_scoring.features.utils import (
    cosine_similarity,
    safe_divide,
    split_paragraphs,
    variance,
)
from scripts.ml_training.essay_scoring.logging_utils import ProgressLogger, ProgressWriter

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

CLAUSE_DEPS = {"ccomp", "xcomp", "advcl", "relcl", "csubj", "csubjpass"}
CONNECTIVES = {
    "however",
    "therefore",
    "moreover",
    "furthermore",
    "nevertheless",
    "thus",
    "hence",
    "consequently",
    "although",
    "because",
    "meanwhile",
    "additionally",
    "finally",
    "in addition",
    "on the other hand",
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tier2BatchResult:
    """Tier 2 batch output plus parse artifacts useful for downstream stages."""

    features: list[Tier2Features]
    docs: list[Doc]
    paragraphs_by_index: list[list[str]]


@dataclass
class Tier2FeatureExtractor:
    """Extract Tier 2 features using spaCy and sentence embeddings."""

    spacy_model: str = "en_core_web_sm"
    nlp: Language | None = None
    spacy_n_process: int = 1
    spacy_pipe_batch_size: int = 32
    embedding_extractor: EmbeddingExtractorProtocol | None = None
    sentence_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    local_embedder: "SentenceTransformer | None" = None
    progress: ProgressWriter | None = None

    def __post_init__(self) -> None:
        if self.nlp is None:
            try:
                self.nlp = spacy.load(self.spacy_model)
            except OSError as exc:
                raise RuntimeError(
                    "spaCy model not available. Install with: python -m spacy download "
                    f"{self.spacy_model}"
                ) from exc
        if self.embedding_extractor is None and self.local_embedder is None:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415

            self.local_embedder = SentenceTransformer(self.sentence_model)

    def extract_batch(self, texts: list[str], prompts: list[str]) -> list[Tier2Features]:
        """Extract Tier 2 features for a batch of essays and prompts.

        If `embedding_extractor` is provided, all sentence/prompt embedding operations are
        executed via that extractor (e.g. Hemma offload) to avoid local torch instability.
        """

        return self.extract_batch_with_artifacts(texts, prompts).features

    def extract_batch_with_artifacts(
        self, texts: list[str], prompts: list[str]
    ) -> Tier2BatchResult:
        """Extract Tier 2 features and return parse artifacts for reuse.

        `docs` and `paragraphs_by_index` enable Tier 3 extraction without re-parsing
        texts, which is important for throughput on Hemma.
        """

        if not texts:
            return Tier2BatchResult(features=[], docs=[], paragraphs_by_index=[])
        if len(texts) != len(prompts):
            raise ValueError(
                "Tier2 extract_batch requires texts and prompts to have the same length "
                f"texts={len(texts)} prompts={len(prompts)}"
            )
        if self.nlp is None:
            raise RuntimeError("spaCy pipeline not initialized for Tier 2 extractor.")

        # Stage 1: parse + deterministic syntactic features.
        stage1_start = time.monotonic()
        stage1_progress = ProgressLogger(logger, "Tier2 stage1", len(texts), every=100)
        syntactic_rows: list[dict[str, float]] = []
        sentence_texts_by_index: list[list[str]] = []
        paragraphs_by_index: list[list[str]] = []
        docs: list[Doc] = []

        logger.info("Tier2 stage1 parse start (n=%d)", len(texts))
        if self.spacy_n_process < 1:
            raise ValueError(f"spacy_n_process must be >= 1, got {self.spacy_n_process}")
        if self.spacy_pipe_batch_size < 1:
            raise ValueError(
                f"spacy_pipe_batch_size must be >= 1, got {self.spacy_pipe_batch_size}"
            )
        for index, (text, prompt, doc) in enumerate(
            zip(
                texts,
                prompts,
                self.nlp.pipe(
                    texts, n_process=self.spacy_n_process, batch_size=self.spacy_pipe_batch_size
                ),
                strict=True,
            )
        ):
            docs.append(doc)
            sentences = list(doc.sents)
            sentence_texts = [sent.text.strip() for sent in sentences if sent.text.strip()]
            sentence_texts_by_index.append(sentence_texts)

            paragraphs = split_paragraphs(text)
            paragraphs_by_index.append(paragraphs)

            parse_depth = self._average_parse_depth(sentences)
            clause_count = float(sum(1 for token in doc if token.dep_ in CLAUSE_DEPS))
            passive_ratio = self._passive_ratio(doc)
            dep_distance = self._dependency_distance(doc)
            connective_diversity = self._connective_diversity(text)

            syntactic_rows.append(
                {
                    "parse_tree_depth": parse_depth,
                    "clause_count": clause_count,
                    "passive_ratio": passive_ratio,
                    "dep_distance": dep_distance,
                    "connective_diversity": connective_diversity,
                    "prompt_len": float(len(prompt)),
                }
            )
            stage1_progress.update(index)
            if self.progress is not None:
                self.progress.update(
                    substage="tier2.stage1_parse",
                    processed=index + 1,
                    total=len(texts),
                    unit="records",
                )

        logger.info("Tier2 stage1 parse complete in %.2fs", time.monotonic() - stage1_start)

        # Stage 2: embed in one (or a few) large batches to avoid thousands of small requests.
        stage2_start = time.monotonic()
        unique_texts: list[str] = []
        index_by_text: dict[str, int] = {}

        def _add(text: str) -> None:
            if text in index_by_text:
                return
            index_by_text[text] = len(unique_texts)
            unique_texts.append(text)

        logger.info("Tier2 stage2 unique text collection start (n=%d)", len(texts))
        for index, (text, prompt, sentence_texts, paragraphs) in enumerate(
            zip(texts, prompts, sentence_texts_by_index, paragraphs_by_index, strict=True)
        ):
            _add(text)
            _add(prompt)
            for sent in sentence_texts:
                _add(sent)
            for para in paragraphs:
                _add(para)
            if (index + 1) % 100 == 0 or index == len(texts) - 1:
                logger.info(
                    "Tier2 stage2 progress %d/%d (unique_texts=%d)",
                    index + 1,
                    len(texts),
                    len(unique_texts),
                )
            if self.progress is not None:
                self.progress.update(
                    substage="tier2.stage2_unique_texts",
                    processed=index + 1,
                    total=len(texts),
                    unit="records",
                    details={"unique_texts": int(len(unique_texts))},
                )

        logger.info(
            "Tier2 stage2 unique text collection complete (unique_texts=%d) in %.2fs",
            len(unique_texts),
            time.monotonic() - stage2_start,
        )

        logger.info("Tier2 embeddings start (unique_texts=%d)", len(unique_texts))
        start = time.monotonic()
        if self.progress is not None:
            self.progress.update(
                substage="tier2.embeddings_unique_texts",
                processed=0,
                total=len(unique_texts),
                unit="texts",
                details={"unique_texts": int(len(unique_texts))},
                force=True,
            )
        embedding_matrix = self._embed_texts(unique_texts, normalize_embeddings=False)
        elapsed = time.monotonic() - start
        if self.progress is not None:
            self.progress.update(
                substage="tier2.embeddings_unique_texts",
                processed=len(unique_texts),
                total=len(unique_texts),
                unit="texts",
                details={"shape": list(embedding_matrix.shape)},
                force=True,
            )
        logger.info(
            "Tier2 embeddings complete (shape=%s) in %.2fs", embedding_matrix.shape, elapsed
        )

        # Stage 3: per-essay embedding-derived features.
        features: list[Tier2Features] = []
        for index, (text, prompt, sentence_texts, paragraphs, row) in enumerate(
            zip(
                texts,
                prompts,
                sentence_texts_by_index,
                paragraphs_by_index,
                syntactic_rows,
                strict=True,
            )
        ):
            sent_similarity_variance = self._sentence_similarity_variance_from_embeddings(
                sentence_texts, embedding_matrix, index_by_text
            )
            prompt_similarity, intro_prompt_sim, min_para_relevance = (
                self._prompt_relevance_from_embeddings(
                    text=text,
                    prompt=prompt,
                    paragraphs=paragraphs,
                    embedding_matrix=embedding_matrix,
                    index_by_text=index_by_text,
                )
            )
            features.append(
                Tier2Features(
                    parse_tree_depth=row["parse_tree_depth"],
                    clause_count=row["clause_count"],
                    passive_ratio=row["passive_ratio"],
                    dep_distance=row["dep_distance"],
                    connective_diversity=row["connective_diversity"],
                    sent_similarity_variance=sent_similarity_variance,
                    prompt_similarity=prompt_similarity,
                    intro_prompt_sim=intro_prompt_sim,
                    min_para_relevance=min_para_relevance,
                )
            )
            if (index + 1) % 100 == 0 or index == len(texts) - 1:
                logger.info("Tier2 progress %d/%d", index + 1, len(texts))
            if self.progress is not None:
                self.progress.update(
                    substage="tier2.stage3_features",
                    processed=index + 1,
                    total=len(texts),
                    unit="records",
                )

        return Tier2BatchResult(
            features=features,
            docs=docs,
            paragraphs_by_index=paragraphs_by_index,
        )

    def extract(self, text: str, prompt: str) -> Tier2Features:
        """Extract Tier 2 features from essay text and prompt."""

        return self.extract_batch([text], [prompt])[0]

    def _average_parse_depth(self, sentences: list[object]) -> float:
        """Compute average maximum dependency depth per sentence."""

        if not sentences:
            return 0.0
        depths = []
        for sentence in sentences:
            depth = 0
            for token in sentence:
                depth = max(depth, self._token_depth(token))
            depths.append(depth)
        return float(np.mean(np.array(depths, dtype=float)))

    @staticmethod
    def _token_depth(token: object) -> int:
        """Compute the depth of a token in the dependency tree."""

        depth = 0
        current = token
        max_depth = len(getattr(token, "doc", []))
        while current.head is not current:
            depth += 1
            if max_depth and depth > max_depth:
                break
            current = current.head
        return depth

    @staticmethod
    def _passive_ratio(doc: object) -> float:
        """Compute ratio of passive constructions to verbs."""

        passive_count = sum(1 for token in doc if token.dep_ == "auxpass")
        verb_count = sum(1 for token in doc if token.pos_ == "VERB")
        return safe_divide(float(passive_count), float(verb_count))

    @staticmethod
    def _dependency_distance(doc: object) -> float:
        """Compute average dependency distance for tokens."""

        distances = [abs(token.i - token.head.i) for token in doc if token.head is not token]
        if not distances:
            return 0.0
        return float(np.mean(np.array(distances, dtype=float)))

    @staticmethod
    def _connective_diversity(text: str) -> float:
        """Compute connective diversity as unique/total ratio."""

        lowered = text.lower()
        found = []
        for connective in CONNECTIVES:
            if connective in lowered:
                found.append(connective)
        if not found:
            return 0.0
        return safe_divide(float(len(set(found))), float(len(found)))

    def _embed_texts(self, texts: list[str], *, normalize_embeddings: bool) -> np.ndarray:
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        embeddings: np.ndarray
        if self.embedding_extractor is not None:
            embeddings = self.embedding_extractor.embed(texts)
        else:
            if self.local_embedder is None:
                raise RuntimeError("Tier2 local embedder not initialized.")
            embeddings = self.local_embedder.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=normalize_embeddings,
                show_progress_bar=False,
            )

        embeddings = embeddings.astype(np.float32, copy=False)

        if normalize_embeddings and self.embedding_extractor is not None:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0.0, 1.0, norms)
            embeddings = embeddings / norms

        return embeddings

    @staticmethod
    def _sentence_similarity_variance_from_embeddings(
        sentences: list[str], embedding_matrix: np.ndarray, index_by_text: dict[str, int]
    ) -> float:
        if len(sentences) < 2:
            return 0.0

        indices = [index_by_text[sent] for sent in sentences]
        embeddings = embedding_matrix[indices]
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0.0, 1.0, norms)
        embeddings = embeddings / norms

        similarity_matrix = np.inner(embeddings, embeddings)
        upper = np.triu_indices_from(similarity_matrix, k=1)
        similarities = similarity_matrix[upper]
        return variance(similarities)

    @staticmethod
    def _prompt_relevance_from_embeddings(
        *,
        text: str,
        prompt: str,
        paragraphs: list[str],
        embedding_matrix: np.ndarray,
        index_by_text: dict[str, int],
    ) -> tuple[float, float, float]:
        essay_embedding = embedding_matrix[index_by_text[text]]
        prompt_embedding = embedding_matrix[index_by_text[prompt]]
        prompt_similarity = cosine_similarity(essay_embedding, prompt_embedding)

        if paragraphs:
            intro_embedding = embedding_matrix[index_by_text[paragraphs[0]]]
            intro_prompt_sim = cosine_similarity(intro_embedding, prompt_embedding)
            para_scores = [
                cosine_similarity(embedding_matrix[index_by_text[para]], prompt_embedding)
                for para in paragraphs
            ]
            min_para_relevance = float(min(para_scores)) if para_scores else 0.0
        else:
            intro_prompt_sim = 0.0
            min_para_relevance = 0.0

        return prompt_similarity, intro_prompt_sim, min_para_relevance
