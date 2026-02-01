"""Tier 2 feature extraction: syntactic complexity, cohesion, prompt relevance."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
import spacy
from sentence_transformers import SentenceTransformer
from spacy.language import Language

from scripts.ml_training.essay_scoring.features.schema import Tier2Features
from scripts.ml_training.essay_scoring.features.utils import (
    cosine_similarity,
    safe_divide,
    split_paragraphs,
    variance,
)

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


@dataclass
class Tier2FeatureExtractor:
    """Extract Tier 2 features using spaCy and sentence-transformers."""

    spacy_model: str = "en_core_web_sm"
    sentence_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    nlp: Language | None = None
    embedder: SentenceTransformer | None = None

    def __post_init__(self) -> None:
        if self.nlp is None:
            try:
                self.nlp = spacy.load(self.spacy_model)
            except OSError as exc:
                raise RuntimeError(
                    "spaCy model not available. Install with: python -m spacy download "
                    f"{self.spacy_model}"
                ) from exc
        if self.embedder is None:
            self.embedder = SentenceTransformer(self.sentence_model)

    def extract(self, text: str, prompt: str) -> Tier2Features:
        """Extract Tier 2 features from essay text and prompt."""

        logger.info("Tier2 spaCy parse start (chars=%d)", len(text))
        start = time.monotonic()
        doc = self.nlp(text)
        sentences = list(doc.sents)
        elapsed = time.monotonic() - start
        logger.info("Tier2 spaCy parse complete (%.2fs, sentences=%d)", elapsed, len(sentences))
        sentence_texts = [sent.text.strip() for sent in sentences if sent.text.strip()]

        logger.info("Tier2 parse depth start (sentences=%d)", len(sentences))
        start = time.monotonic()
        parse_depth = self._average_parse_depth(sentences)
        elapsed = time.monotonic() - start
        logger.info("Tier2 parse depth complete (%.2fs)", elapsed)
        clause_count = float(sum(1 for token in doc if token.dep_ in CLAUSE_DEPS))
        passive_ratio = self._passive_ratio(doc)
        logger.info("Tier2 dependency distance start (tokens=%d)", len(doc))
        start = time.monotonic()
        dep_distance = self._dependency_distance(doc)
        elapsed = time.monotonic() - start
        logger.info("Tier2 dependency distance complete (%.2fs)", elapsed)
        connective_diversity = self._connective_diversity(text)
        sent_similarity_variance = self._sentence_similarity_variance(sentence_texts)

        prompt_similarity, intro_prompt_sim, min_para_relevance = self._prompt_relevance(
            text, prompt
        )

        return Tier2Features(
            parse_tree_depth=parse_depth,
            clause_count=clause_count,
            passive_ratio=passive_ratio,
            dep_distance=dep_distance,
            connective_diversity=connective_diversity,
            sent_similarity_variance=sent_similarity_variance,
            prompt_similarity=prompt_similarity,
            intro_prompt_sim=intro_prompt_sim,
            min_para_relevance=min_para_relevance,
        )

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

    def _sentence_similarity_variance(self, sentences: list[str]) -> float:
        """Compute variance of pairwise sentence similarities."""

        if len(sentences) < 2:
            return 0.0
        logger.info("Tier2 sentence similarity encode start (sentences=%d)", len(sentences))
        start = time.monotonic()
        embeddings = self.embedder.encode(
            sentences,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        elapsed = time.monotonic() - start
        logger.info("Tier2 sentence similarity encode complete (%.2fs)", elapsed)
        similarity_matrix = np.inner(embeddings, embeddings)
        indices = np.triu_indices_from(similarity_matrix, k=1)
        similarities = similarity_matrix[indices]
        return variance(similarities)

    def _prompt_relevance(self, text: str, prompt: str) -> tuple[float, float, float]:
        """Compute prompt relevance features using sentence embeddings."""

        paragraphs = split_paragraphs(text)
        logger.info("Tier2 prompt relevance encode start (essay+prompt)")
        start = time.monotonic()
        essay_embedding = self.embedder.encode(
            [text], convert_to_numpy=True, show_progress_bar=False
        )[0]
        prompt_embedding = self.embedder.encode(
            [prompt], convert_to_numpy=True, show_progress_bar=False
        )[0]
        elapsed = time.monotonic() - start
        logger.info("Tier2 prompt relevance encode complete (essay+prompt) (%.2fs)", elapsed)
        prompt_similarity = cosine_similarity(essay_embedding, prompt_embedding)

        if paragraphs:
            logger.info("Tier2 prompt relevance encode start (intro)")
            start = time.monotonic()
            intro_embedding = self.embedder.encode(
                [paragraphs[0]], convert_to_numpy=True, show_progress_bar=False
            )[0]
            elapsed = time.monotonic() - start
            logger.info("Tier2 prompt relevance encode complete (intro) (%.2fs)", elapsed)
            intro_prompt_sim = cosine_similarity(intro_embedding, prompt_embedding)
            logger.info("Tier2 prompt relevance encode start (paragraphs=%d)", len(paragraphs))
            start = time.monotonic()
            para_embeddings = self.embedder.encode(
                paragraphs, convert_to_numpy=True, show_progress_bar=False
            )
            elapsed = time.monotonic() - start
            logger.info("Tier2 prompt relevance encode complete (paragraphs) (%.2fs)", elapsed)
            para_scores = [
                cosine_similarity(embedding, prompt_embedding) for embedding in para_embeddings
            ]
            min_para_relevance = float(min(para_scores)) if para_scores else 0.0
        else:
            intro_prompt_sim = 0.0
            min_para_relevance = 0.0

        return prompt_similarity, intro_prompt_sim, min_para_relevance
