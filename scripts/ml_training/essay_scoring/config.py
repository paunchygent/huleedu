"""Configuration models for the essay scoring research pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FeatureSet(str, Enum):
    """Feature set choices for ablation and training."""

    HANDCRAFTED = "handcrafted"
    EMBEDDINGS = "embeddings"
    COMBINED = "combined"


class DatasetKind(str, Enum):
    """Dataset source choices for the research pipeline."""

    IELTS = "ielts"
    ELLIPSE = "ellipse"


class EmbeddingConfig(BaseModel):
    """Configuration for embedding extraction."""

    model_config = ConfigDict(extra="forbid")

    model_name: str = "microsoft/deberta-v3-base"
    max_length: int = 512
    batch_size: int = 8
    device: str | None = None


class TrainingConfig(BaseModel):
    """Configuration for XGBoost training."""

    model_config = ConfigDict(extra="forbid")

    random_seed: int = 42
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    test_ratio: float = 0.15
    num_boost_round: int = 1500
    early_stopping_rounds: int = 100
    params: dict[str, int | float | str | bool] = Field(
        default_factory=lambda: {
            "objective": "reg:squarederror",
            "max_depth": 6,
            "learning_rate": 0.03,
            "min_child_weight": 5,
            "reg_lambda": 2.0,
            "colsample_bytree": 0.6,
            "subsample": 0.8,
        }
    )


class OutputConfig(BaseModel):
    """Configuration for output artifacts."""

    model_config = ConfigDict(extra="forbid")

    base_dir: Path = Path("output/essay_scoring")
    run_name: str | None = None

    def resolve_run_dir(self) -> Path:
        """Create a unique run directory path."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = self.run_name or "run"
        return self.base_dir / f"{timestamp}_{suffix}"


class OffloadConfig(BaseModel):
    """Remote offload configuration (Hemma via tunnel).

    When URLs are set, the research pipeline can offload:
    - DeBERTa embeddings to Hemma (binary `.npy` response)
    - LanguageTool checks to Hemma (`services/language_tool_service` HTTP API)
    """

    model_config = ConfigDict(extra="forbid")

    embedding_service_url: str | None = Field(
        default=None,
        description="Base URL for the offload embedding server (e.g. http://127.0.0.1:19000).",
    )
    language_tool_service_url: str | None = Field(
        default=None,
        description="Base URL for LanguageTool service (e.g. http://127.0.0.1:18085).",
    )
    request_timeout_s: float = Field(default=60.0, ge=1.0, le=600.0)
    embedding_cache_dir: Path = Field(
        default=Path("output/essay_scoring/.cache/offload_embeddings"),
        description="Disk cache for per-text embedding vectors (Mac-side).",
    )
    language_tool_cache_dir: Path = Field(
        default=Path("output/essay_scoring/.cache/offload_language_tool"),
        description="Disk cache for per-text LanguageTool responses (Mac-side).",
    )
    language_tool_max_concurrency: int = Field(
        default=10,
        ge=1,
        le=64,
        description="Max concurrent LanguageTool offload HTTP requests (Mac-side).",
    )


class ExperimentConfig(BaseModel):
    """Top-level experiment configuration."""

    model_config = ConfigDict(extra="forbid")

    dataset_kind: DatasetKind = DatasetKind.IELTS
    dataset_path: Path = Path("data/cefr_ielts_datasets/ielts_writing_dataset.csv")
    ellipse_train_path: Path = Path("data/ELLIPSE_TRAIN_TEST/ELLIPSE_Final_github_train.csv")
    ellipse_test_path: Path = Path("data/ELLIPSE_TRAIN_TEST/ELLIPSE_Final_github_test.csv")
    ellipse_excluded_prompts: list[str] = Field(
        default_factory=lambda: [
            "Community service",
            "Grades for extracurricular activities",
            "Cell phones at school",
            "Letter to employer",
        ],
        description="Prompt names to drop entirely when dataset_kind=ellipse.",
    )
    feature_set: FeatureSet = FeatureSet.COMBINED
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    offload: OffloadConfig = Field(default_factory=OffloadConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    @classmethod
    def from_json(cls, json_text: str) -> "ExperimentConfig":
        """Build a config instance from JSON text."""
        return cls.model_validate_json(json_text)
