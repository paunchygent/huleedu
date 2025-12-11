---
id: 'ml-model-serving-infrastructure-for-essay-scoring'
title: 'ML Model Serving Infrastructure for Essay Scoring'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-12-05'
last_updated: '2025-12-05'
related: ['task-054-suggested-improvements-to-bayesian-model']
labels: ['mlops', 'infrastructure', 'deployment']
---
# ML Model Serving Infrastructure for Essay Scoring

## Objective

Design production deployment and serving infrastructure for gradient boosting essay scoring models within HuleEdu's existing Docker Compose architecture, supporting hot-reload deployments, monitoring, and CI/CD automation.

## Context

### Current State
- **Scoring Method**: Comparative Judgement (CJ) using Bradley-Terry model via LLM comparisons
- **Bayesian Consensus**: Experimental Gaussian kernel model (`scripts/bayesian_consensus_model/`)
- **ML Model**: Gradient Boosting classifier for ordinal Swedish 8-grade classification
- **Infrastructure**: Docker Compose, PostgreSQL, Kafka, Redis, Prometheus, Grafana
- **Model Size**: Small (~10-50MB serialized)
- **No Kubernetes**: Pure Docker Compose deployment target

### Requirements
1. Production model serving with zero-downtime updates
2. Feature extraction and caching for CJ-derived features
3. Model versioning and A/B testing capability
4. Integration with existing observability stack
5. Automated training and deployment pipelines
6. Model validation gates before production deployment

## Architecture Decision: Embedded vs Dedicated Service

### Option A: Embedded in CJ Assessment Service (RECOMMENDED)

**Pros:**
- Simpler deployment (no new service container)
- Direct access to CJ batch state and BT scores
- Lower latency (in-process feature extraction)
- Fewer network hops and serialization overhead
- Reuses existing DB connections and observability
- Natural evolution path from BT-only scoring

**Cons:**
- Couples ML model lifecycle to CJ service deployment
- Larger container image size (~100MB increase)
- ML dependencies (scikit-learn, xgboost) in CJ environment
- Potentially higher memory footprint per container

**Implementation Pattern:**
```
services/cj_assessment_service/
├── ml_scoring/
│   ├── __init__.py
│   ├── protocols.py              # ModelLoaderProtocol, ModelScorerProtocol
│   ├── implementations/
│   │   ├── model_loader_impl.py   # Hot-reload, versioning
│   │   ├── gb_scorer_impl.py      # Gradient boosting scorer
│   │   └── feature_extractor.py   # CJ + essay metadata → features
│   ├── models/                    # Model artifacts (volume mount)
│   │   └── .gitkeep
│   └── tests/
│       ├── test_model_loading.py
│       └── test_feature_extraction.py
```

### Option B: Dedicated ML Inference Service

**Pros:**
- Independent scaling for ML workloads
- Clearer separation of concerns
- Can serve multiple model types
- Easier to replace/upgrade ML stack
- Multiple consumers (CJ, future AI feedback service)

**Cons:**
- Additional service container and complexity
- Network latency for HTTP/gRPC calls
- Duplicate feature extraction if CJ context needed
- More moving parts in deployment pipeline

**Implementation Pattern:**
```
services/ml_inference_service/
├── app.py                     # Quart HTTP API
├── protocols.py
├── implementations/
│   ├── gb_scorer_impl.py
│   └── model_loader_impl.py
├── api/
│   └── scoring_routes.py      # POST /v1/score/batch
└── models/                    # Model artifacts (volume mount)
```

**Recommendation:** Start with **Option A (Embedded)** for faster iteration and lower operational overhead. Design with protocols to enable future migration to Option B if needed.

## Detailed Design: Embedded ML Scoring

### 1. Model Storage and Versioning

**Volume Mount Strategy:**
```yaml
# docker-compose.services.yml
services:
  cj_assessment_service:
    volumes:
      - ./models/cj_grading:/app/models/cj_grading:ro  # Read-only mount
```

**Model Artifact Structure:**
```
models/cj_grading/
├── production/
│   ├── model.pkl                 # Active model
│   ├── model_metadata.json       # Version, metrics, training date
│   ├── feature_config.json       # Feature extraction config
│   └── model_signature.sha256    # Integrity check
├── staging/
│   └── [same structure]
└── archive/
    ├── v1.0.0/
    ├── v1.1.0/
    └── v1.2.0/
```

**Model Metadata Schema:**
```json
{
  "model_version": "1.2.0",
  "model_type": "gradient_boosting",
  "framework": "sklearn",
  "framework_version": "1.5.1",
  "training_date": "2025-12-01T10:30:00Z",
  "training_dataset": {
    "batch_ids": ["batch-123", "batch-456"],
    "n_essays": 5000,
    "grade_distribution": {"A": 120, "B": 450, ...}
  },
  "validation_metrics": {
    "qwk": 0.78,
    "accuracy": 0.72,
    "mae": 0.45
  },
  "features": ["bt_score", "bt_se", "word_count", "comparison_count", ...],
  "min_inference_latency_ms": 5,
  "max_inference_latency_ms": 50
}
```

### 2. Model Loading with Hot-Reload

**Protocol:**
```python
# services/cj_assessment_service/ml_scoring/protocols.py

from typing import Protocol, TypedDict
import numpy as np

class ModelMetadata(TypedDict):
    model_version: str
    training_date: str
    validation_metrics: dict[str, float]

class ModelLoaderProtocol(Protocol):
    async def load_model(self, model_path: str) -> tuple[Any, ModelMetadata]:
        """Load model and metadata from disk."""
        ...

    async def get_active_model(self) -> tuple[Any, ModelMetadata]:
        """Get currently active model."""
        ...

    async def reload_model(self) -> bool:
        """Hot-reload model if new version detected."""
        ...
```

**Implementation with File Watching:**
```python
# services/cj_assessment_service/ml_scoring/implementations/model_loader_impl.py

import asyncio
import hashlib
import pickle
from pathlib import Path
from dataclasses import dataclass
from typing import Any

@dataclass
class LoadedModel:
    model: Any
    metadata: ModelMetadata
    loaded_at: datetime
    file_hash: str

class ModelLoaderImpl:
    def __init__(self, model_dir: Path, check_interval: int = 60):
        self._model_dir = model_dir
        self._check_interval = check_interval
        self._current_model: LoadedModel | None = None
        self._watch_task: asyncio.Task | None = None

    async def start_watching(self):
        """Background task to watch for model updates."""
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def _watch_loop(self):
        while True:
            await asyncio.sleep(self._check_interval)
            try:
                await self._check_and_reload()
            except Exception as e:
                logger.error(f"Model reload check failed: {e}")

    async def _check_and_reload(self):
        """Check if model file changed and reload if needed."""
        model_path = self._model_dir / "production" / "model.pkl"
        if not model_path.exists():
            return

        current_hash = self._compute_file_hash(model_path)

        if self._current_model is None or current_hash != self._current_model.file_hash:
            logger.info(f"Model file changed (hash: {current_hash[:8]}), reloading...")
            await self._load_and_activate(model_path, current_hash)

    async def _load_and_activate(self, model_path: Path, file_hash: str):
        """Load model in background thread and atomically swap."""
        # Load in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        model, metadata = await loop.run_in_executor(
            None, self._load_model_sync, model_path
        )

        # Atomic swap
        old_model = self._current_model
        self._current_model = LoadedModel(
            model=model,
            metadata=metadata,
            loaded_at=datetime.utcnow(),
            file_hash=file_hash
        )

        logger.info(f"Model reloaded: v{metadata['model_version']}, "
                   f"QWK: {metadata['validation_metrics']['qwk']:.3f}")

        # Increment Prometheus counter
        model_reload_total.inc()

    @staticmethod
    def _load_model_sync(model_path: Path) -> tuple[Any, ModelMetadata]:
        """Synchronous model loading (runs in executor)."""
        with open(model_path, 'rb') as f:
            model = pickle.load(f)

        metadata_path = model_path.parent / "model_metadata.json"
        with open(metadata_path) as f:
            metadata = json.load(f)

        return model, metadata
```

### 3. Feature Extraction from CJ Context

**Feature Engineering Strategy:**
```python
# services/cj_assessment_service/ml_scoring/implementations/feature_extractor.py

from dataclasses import dataclass

@dataclass
class EssayFeatures:
    """Features derived from CJ processing."""
    bt_score: float
    bt_se: float
    rank: int
    comparison_count: int
    win_rate: float
    comparison_variance: float
    word_count: int
    unique_word_ratio: float
    avg_sentence_length: float

    def to_array(self) -> np.ndarray:
        return np.array([
            self.bt_score, self.bt_se, self.rank,
            self.comparison_count, self.win_rate,
            self.comparison_variance, self.word_count,
            self.unique_word_ratio, self.avg_sentence_length
        ])

class FeatureExtractorImpl:
    async def extract_features(
        self,
        essay: ProcessedEssay,
        batch_state: CJBatchState,
        essay_text: str
    ) -> EssayFeatures:
        """Extract ML features from CJ results and essay text."""

        # CJ-derived features
        bt_score = essay.current_bt_score or 0.0
        bt_se = essay.bt_se or 0.0

        # Comparison statistics
        comparisons = await self._comparison_repo.get_comparisons_for_essay(
            essay.essay_id
        )
        comparison_count = len(comparisons)
        wins = sum(1 for c in comparisons if c.winner_essay_id == essay.essay_id)
        win_rate = wins / comparison_count if comparison_count > 0 else 0.0

        # Text features (cached in Redis)
        text_features = await self._compute_text_features(essay.essay_id, essay_text)

        return EssayFeatures(
            bt_score=bt_score,
            bt_se=bt_se,
            rank=essay.rank or 0,
            comparison_count=comparison_count,
            win_rate=win_rate,
            comparison_variance=self._compute_comparison_variance(comparisons),
            word_count=text_features['word_count'],
            unique_word_ratio=text_features['unique_word_ratio'],
            avg_sentence_length=text_features['avg_sentence_length']
        )

    async def _compute_text_features(
        self, essay_id: str, text: str
    ) -> dict[str, float]:
        """Compute and cache text-based features."""
        cache_key = f"essay_text_features:{essay_id}"

        # Try cache first
        cached = await self._cache.get(cache_key)
        if cached:
            return json.loads(cached)

        # Compute features
        words = text.split()
        sentences = text.split('.')

        features = {
            'word_count': len(words),
            'unique_word_ratio': len(set(words)) / len(words) if words else 0,
            'avg_sentence_length': len(words) / len(sentences) if sentences else 0
        }

        # Cache for 24 hours
        await self._cache.set(cache_key, json.dumps(features), ttl=86400)
        return features
```

### 4. Model Scoring Integration

**Scorer Protocol:**
```python
# services/cj_assessment_service/ml_scoring/protocols.py

class GradePrediction(TypedDict):
    grade: str                    # Predicted grade (A, B, C+, etc.)
    confidence: float             # Model confidence [0, 1]
    grade_probabilities: dict[str, float]  # Full distribution
    model_version: str
    features_used: list[str]

class ModelScorerProtocol(Protocol):
    async def score_essay(
        self,
        essay: ProcessedEssay,
        batch_state: CJBatchState
    ) -> GradePrediction:
        """Score single essay."""
        ...

    async def score_batch(
        self,
        essays: list[ProcessedEssay],
        batch_state: CJBatchState
    ) -> list[GradePrediction]:
        """Score multiple essays efficiently."""
        ...
```

**Implementation:**
```python
# services/cj_assessment_service/ml_scoring/implementations/gb_scorer_impl.py

class GradientBoostingScorerImpl:
    def __init__(
        self,
        model_loader: ModelLoaderProtocol,
        feature_extractor: FeatureExtractorImpl,
        content_client: ContentClientProtocol
    ):
        self._model_loader = model_loader
        self._feature_extractor = feature_extractor
        self._content_client = content_client

    async def score_batch(
        self,
        essays: list[ProcessedEssay],
        batch_state: CJBatchState
    ) -> list[GradePrediction]:
        """Score batch of essays with ML model."""

        model, metadata = await self._model_loader.get_active_model()
        if model is None:
            raise ModelNotLoadedError("No active model available")

        # Extract features for all essays
        feature_matrix = []
        for essay in essays:
            text = await self._content_client.get_essay_text(essay.text_storage_id)
            features = await self._feature_extractor.extract_features(
                essay, batch_state, text
            )
            feature_matrix.append(features.to_array())

        X = np.vstack(feature_matrix)

        # Run inference in executor (sklearn models are CPU-bound)
        loop = asyncio.get_event_loop()
        predictions, probabilities = await loop.run_in_executor(
            None, self._predict_sync, model, X
        )

        # Convert to grade predictions
        grade_scale = ["F", "E", "D", "C", "B", "A"]  # Simplified
        results = []
        for pred, probs in zip(predictions, probabilities):
            results.append(GradePrediction(
                grade=grade_scale[pred],
                confidence=float(probs.max()),
                grade_probabilities={
                    grade: float(p) for grade, p in zip(grade_scale, probs)
                },
                model_version=metadata['model_version'],
                features_used=metadata['features']
            ))

        return results

    @staticmethod
    def _predict_sync(model, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Synchronous prediction (runs in executor)."""
        predictions = model.predict(X)
        probabilities = model.predict_proba(X)
        return predictions, probabilities
```

### 5. Integration into CJ Workflow

**Update BatchFinalizer to include ML predictions:**
```python
# services/cj_assessment_service/cj_core_logic/batch_finalizer.py

class BatchFinalizer:
    def __init__(
        self,
        # ... existing dependencies
        ml_scorer: ModelScorerProtocol | None = None  # Optional
    ):
        self._ml_scorer = ml_scorer

    async def finalize_scoring(
        self,
        batch_id: str,
        batch_state: CJBatchState
    ) -> AssessmentResultV1:
        """Finalize batch with BT scores and optional ML predictions."""

        essays = await self._essay_repo.get_essays_for_batch(batch_id)

        # Existing BT scoring
        bt_rankings = self._compute_bt_rankings(essays)

        # Optional ML predictions
        ml_predictions = None
        if self._ml_scorer:
            try:
                ml_predictions = await self._ml_scorer.score_batch(
                    essays, batch_state
                )
                logger.info(f"ML predictions generated for {len(ml_predictions)} essays")
            except Exception as e:
                logger.error(f"ML scoring failed: {e}", exc_info=True)
                # Continue with BT-only results

        # Merge BT and ML results
        results = []
        for essay, bt_rank in zip(essays, bt_rankings):
            ml_pred = None
            if ml_predictions:
                ml_pred = next(
                    (p for p in ml_predictions if p['essay_id'] == essay.essay_id),
                    None
                )

            results.append(EssayResult(
                essay_id=essay.essay_id,
                bt_score=essay.current_bt_score,
                bt_se=essay.bt_se,
                rank=bt_rank,
                ml_grade=ml_pred['grade'] if ml_pred else None,
                ml_confidence=ml_pred['confidence'] if ml_pred else None
            ))

        return AssessmentResultV1(
            batch_id=batch_id,
            results=results,
            scoring_method="hybrid_bt_ml" if ml_predictions else "bt_only",
            model_version=ml_predictions[0]['model_version'] if ml_predictions else None
        )
```

### 6. Docker Compose Configuration

**Update CJ Assessment Service:**
```yaml
# docker-compose.services.yml

services:
  cj_assessment_service:
    build:
      context: .
      dockerfile: services/cj_assessment_service/Dockerfile
    volumes:
      # Existing volumes
      - ./models/cj_grading:/app/models/cj_grading:ro  # NEW: Model artifacts
    environment:
      # Existing environment
      - CJ_ASSESSMENT_SERVICE_ML_ENABLED=true
      - CJ_ASSESSMENT_SERVICE_ML_MODEL_DIR=/app/models/cj_grading
      - CJ_ASSESSMENT_SERVICE_ML_CHECK_INTERVAL=60  # Check for updates every 60s
      - CJ_ASSESSMENT_SERVICE_ML_MIN_COMPARISON_COUNT=10  # Min comparisons for ML
    deploy:
      resources:
        limits:
          memory: 2G      # Increased for ML dependencies
          cpus: '1.5'
        reservations:
          memory: 1G
```

**Dockerfile updates:**
```dockerfile
# services/cj_assessment_service/Dockerfile

FROM python:3.11-slim as base

# Install ML dependencies
RUN pip install --no-cache-dir \
    scikit-learn==1.5.1 \
    xgboost==2.0.3 \
    numpy==1.26.4

# ... rest of Dockerfile
```

### 7. Monitoring and Observability

**Prometheus Metrics:**
```python
# services/cj_assessment_service/ml_scoring/metrics.py

from prometheus_client import Counter, Histogram, Gauge

# Model management
model_reload_total = Counter(
    'cj_ml_model_reload_total',
    'Total number of model reloads'
)

active_model_version = Gauge(
    'cj_ml_active_model_version',
    'Currently active model version',
    ['model_version', 'training_date']
)

# Inference metrics
ml_prediction_duration_seconds = Histogram(
    'cj_ml_prediction_duration_seconds',
    'Time to generate ML predictions',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0]
)

ml_prediction_total = Counter(
    'cj_ml_prediction_total',
    'Total ML predictions',
    ['grade', 'confidence_bucket']
)

ml_prediction_errors_total = Counter(
    'cj_ml_prediction_errors_total',
    'Total ML prediction errors',
    ['error_type']
)

# Feature extraction
feature_extraction_duration_seconds = Histogram(
    'cj_ml_feature_extraction_duration_seconds',
    'Time to extract features per essay'
)

feature_cache_hit_total = Counter(
    'cj_ml_feature_cache_hit_total',
    'Feature cache hits'
)
```

**Grafana Dashboard Panel Examples:**
```json
{
  "title": "ML Model Performance",
  "panels": [
    {
      "title": "Active Model Version",
      "targets": [
        {
          "expr": "cj_ml_active_model_version"
        }
      ]
    },
    {
      "title": "Prediction Latency (p95)",
      "targets": [
        {
          "expr": "histogram_quantile(0.95, rate(cj_ml_prediction_duration_seconds_bucket[5m]))"
        }
      ]
    },
    {
      "title": "Grade Distribution",
      "targets": [
        {
          "expr": "rate(cj_ml_prediction_total[5m])"
        }
      ]
    },
    {
      "title": "Feature Cache Hit Rate",
      "targets": [
        {
          "expr": "rate(cj_ml_feature_cache_hit_total[5m]) / (rate(cj_ml_feature_cache_hit_total[5m]) + rate(feature_cache_miss_total[5m]))"
        }
      ]
    }
  ]
}
```

## CI/CD Pipeline Design

### GitHub Actions Workflow

**Trigger Conditions:**
- Manual dispatch with training config
- Scheduled weekly retrain
- On new labeled data threshold (100+ essays)

**Workflow File:**
```yaml
# .github/workflows/ml-training.yml

name: ML Model Training and Deployment

on:
  workflow_dispatch:
    inputs:
      training_config:
        description: 'Training configuration'
        required: true
        default: 'configs/training/default.yaml'
      min_qwk_threshold:
        description: 'Minimum QWK to deploy'
        required: false
        default: '0.70'

  schedule:
    - cron: '0 2 * * 0'  # Weekly Sunday 2 AM

jobs:
  extract-training-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Extract data from production DB
        env:
          PROD_DB_CONNECTION: ${{ secrets.PROD_DB_CONNECTION }}
        run: |
          pdm install
          pdm run python scripts/ml_training/extract_training_data.py \
            --output data/training/batch_$(date +%Y%m%d).csv \
            --min-comparisons 10 \
            --since-days 90

      - name: Upload training data artifact
        uses: actions/upload-artifact@v4
        with:
          name: training-data
          path: data/training/

  train-model:
    needs: extract-training-data
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download training data
        uses: actions/download-artifact@v4
        with:
          name: training-data

      - name: Train gradient boosting model
        run: |
          pdm run python scripts/ml_training/train_gb_classifier.py \
            --config ${{ github.event.inputs.training_config }} \
            --output models/candidate/

      - name: Upload model artifacts
        uses: actions/upload-artifact@v4
        with:
          name: trained-model
          path: models/candidate/

  validate-model:
    needs: train-model
    runs-on: ubuntu-latest
    outputs:
      qwk: ${{ steps.metrics.outputs.qwk }}
      accuracy: ${{ steps.metrics.outputs.accuracy }}
    steps:
      - uses: actions/checkout@v4

      - name: Download model
        uses: actions/download-artifact@v4
        with:
          name: trained-model

      - name: Run validation suite
        id: metrics
        run: |
          pdm run python scripts/ml_training/validate_model.py \
            --model models/candidate/model.pkl \
            --validation-data data/validation/holdout_set.csv \
            --output validation_report.json

          # Extract metrics
          QWK=$(jq -r '.qwk' validation_report.json)
          ACC=$(jq -r '.accuracy' validation_report.json)
          echo "qwk=$QWK" >> $GITHUB_OUTPUT
          echo "accuracy=$ACC" >> $GITHUB_OUTPUT

      - name: Check QWK threshold
        run: |
          QWK=${{ steps.metrics.outputs.qwk }}
          THRESHOLD=${{ github.event.inputs.min_qwk_threshold }}
          if (( $(echo "$QWK < $THRESHOLD" | bc -l) )); then
            echo "QWK $QWK below threshold $THRESHOLD"
            exit 1
          fi

      - name: Integration test with real essays
        run: |
          pdm run pytest scripts/ml_training/tests/test_model_integration.py \
            --model models/candidate/model.pkl

  deploy-staging:
    needs: validate-model
    runs-on: ubuntu-latest
    steps:
      - name: Download model
        uses: actions/download-artifact@v4
        with:
          name: trained-model

      - name: Deploy to staging environment
        run: |
          # Copy to staging model directory
          scp models/candidate/* staging:/app/models/cj_grading/staging/

          # Update staging symlink (triggers hot-reload)
          ssh staging "ln -sf /app/models/cj_grading/staging /app/models/cj_grading/active"

      - name: Wait for health check
        run: |
          sleep 30  # Allow hot-reload
          curl -f http://staging:9090/healthz

  create-deployment-pr:
    needs: [validate-model, deploy-staging]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Download model
        uses: actions/download-artifact@v4
        with:
          name: trained-model
          path: models/cj_grading/production/

      - name: Create deployment PR
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: |
            Deploy ML model v${{ github.run_number }}

            QWK: ${{ needs.validate-model.outputs.qwk }}
            Accuracy: ${{ needs.validate-model.outputs.accuracy }}
          branch: ml-deploy-${{ github.run_number }}
          title: "Deploy ML Model v${{ github.run_number }}"
          body: |
            ## Model Performance

            - **QWK**: ${{ needs.validate-model.outputs.qwk }}
            - **Accuracy**: ${{ needs.validate-model.outputs.accuracy }}
            - **Training Date**: $(date -I)

            ## Validation

            - [x] QWK threshold met
            - [x] Integration tests passed
            - [x] Deployed to staging

            Merging this PR will deploy to production via hot-reload.

  auto-deploy-production:
    needs: create-deployment-pr
    if: github.event_name == 'schedule'  # Auto-deploy scheduled runs
    runs-on: ubuntu-latest
    steps:
      - name: Auto-merge PR
        run: |
          gh pr merge ${{ needs.create-deployment-pr.outputs.pr-number }} \
            --auto --squash
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Training Scripts

**Data Extraction:**
```python
# scripts/ml_training/extract_training_data.py

import asyncio
from datetime import datetime, timedelta
import pandas as pd

async def extract_training_data(
    min_comparisons: int = 10,
    since_days: int = 90,
    output_path: str = "training_data.csv"
):
    """Extract labeled essays from production CJ batches."""

    # Query essays with sufficient comparisons
    query = """
    SELECT
        e.essay_id,
        e.current_bt_score,
        e.bt_se,
        e.rank,
        COUNT(c.id) as comparison_count,
        SUM(CASE WHEN c.winner_essay_id = e.essay_id THEN 1 ELSE 0 END)::float / COUNT(c.id) as win_rate,
        gp.projected_grade,
        gp.confidence_score,
        b.batch_id,
        b.created_at
    FROM cj_processed_essays e
    JOIN cj_batch_uploads b ON e.batch_id = b.batch_id
    LEFT JOIN cj_comparison_pairs c ON (c.essay_a_id = e.essay_id OR c.essay_b_id = e.essay_id)
    LEFT JOIN grade_projections gp ON e.essay_id = gp.essay_id
    WHERE
        b.status = 'COMPLETED'
        AND b.created_at >= NOW() - INTERVAL '%s days'
        AND gp.projected_grade IS NOT NULL  -- Only labeled data
    GROUP BY e.essay_id, e.current_bt_score, e.bt_se, e.rank,
             gp.projected_grade, gp.confidence_score, b.batch_id, b.created_at
    HAVING COUNT(c.id) >= %s
    """

    # Execute and save
    df = await fetch_dataframe(query, since_days, min_comparisons)

    # Enrich with text features
    df = await add_text_features(df)

    df.to_csv(output_path, index=False)
    logger.info(f"Extracted {len(df)} training examples to {output_path}")
```

**Model Training:**
```python
# scripts/ml_training/train_gb_classifier.py

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import cohen_kappa_score
import pickle
import json

def train_model(config: dict, data_path: str, output_dir: str):
    """Train gradient boosting classifier."""

    # Load data
    df = pd.read_csv(data_path)

    # Features
    feature_cols = [
        'bt_score', 'bt_se', 'rank', 'comparison_count', 'win_rate',
        'word_count', 'unique_word_ratio', 'avg_sentence_length'
    ]
    X = df[feature_cols].values

    # Target: ordinal grades
    grade_mapping = {'F': 0, 'E': 1, 'D': 2, 'C': 3, 'B': 4, 'A': 5}
    y = df['projected_grade'].map(grade_mapping).values

    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Train model
    model = GradientBoostingClassifier(
        n_estimators=config.get('n_estimators', 100),
        max_depth=config.get('max_depth', 5),
        learning_rate=config.get('learning_rate', 0.1),
        random_state=42
    )
    model.fit(X_train, y_train)

    # Validate
    y_pred = model.predict(X_test)
    qwk = cohen_kappa_score(y_test, y_pred, weights='quadratic')
    accuracy = (y_pred == y_test).mean()

    # Save model
    with open(f"{output_dir}/model.pkl", 'wb') as f:
        pickle.dump(model, f)

    # Save metadata
    metadata = {
        'model_version': f"1.{datetime.now().strftime('%Y%m%d')}",
        'model_type': 'gradient_boosting',
        'framework': 'sklearn',
        'framework_version': sklearn.__version__,
        'training_date': datetime.utcnow().isoformat(),
        'training_dataset': {
            'n_essays': len(df),
            'grade_distribution': df['projected_grade'].value_counts().to_dict()
        },
        'validation_metrics': {
            'qwk': float(qwk),
            'accuracy': float(accuracy)
        },
        'features': feature_cols
    }

    with open(f"{output_dir}/model_metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Model trained: QWK={qwk:.3f}, Accuracy={accuracy:.3f}")
```

## Deployment Strategy

### Blue-Green Deployment via Symlinks

**Current State:**
```
models/cj_grading/
├── production/
│   └── model.pkl          # Active model
├── staging/
│   └── model.pkl          # Candidate model
└── active -> production   # Symlink (hot-reload watches this)
```

**Deployment Process:**
1. Train new model → save to `staging/`
2. Validate in staging environment
3. Create PR with model artifacts
4. On merge: Update `production/` directory
5. Hot-reload detects change via file hash
6. Model swaps atomically in-process (zero downtime)

**Rollback:**
```bash
# Restore previous version
cp models/cj_grading/archive/v1.1.0/* models/cj_grading/production/

# Service detects change and reloads within 60 seconds
```

### Health Checks

**Model Availability:**
```python
# services/cj_assessment_service/api/health_routes.py

@health_bp.route("/healthz", methods=["GET"])
async def health_check():
    """Extended health check including ML model status."""

    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "ml_model": {
            "loaded": False,
            "version": None,
            "loaded_at": None
        }
    }

    # Check ML model
    if ml_scorer:
        try:
            model, metadata = await ml_scorer._model_loader.get_active_model()
            health_status["ml_model"]["loaded"] = model is not None
            if model:
                health_status["ml_model"]["version"] = metadata['model_version']
                health_status["ml_model"]["loaded_at"] = metadata.get('loaded_at')
        except Exception as e:
            health_status["ml_model"]["error"] = str(e)

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code
```

## Model Validation Gates

### Pre-Deployment Checks

**1. Performance Thresholds:**
- QWK > 0.70 (Cohen's Kappa, quadratic weighted)
- Accuracy > 0.65
- No grade more than 10% overrepresented vs training distribution

**2. Distribution Drift:**
```python
# scripts/ml_training/validate_model.py

def check_prediction_distribution(predictions: np.ndarray, reference_dist: dict):
    """Ensure predicted grades match expected distribution."""

    pred_dist = pd.Series(predictions).value_counts(normalize=True)

    for grade, expected_freq in reference_dist.items():
        actual_freq = pred_dist.get(grade, 0)
        if abs(actual_freq - expected_freq) > 0.10:
            raise ValidationError(
                f"Grade {grade} distribution drift: "
                f"expected {expected_freq:.1%}, got {actual_freq:.1%}"
            )
```

**3. Inference Latency:**
- p95 latency < 100ms per essay
- Batch of 50 essays < 2 seconds

**4. Integration Test:**
```python
# scripts/ml_training/tests/test_model_integration.py

@pytest.mark.asyncio
async def test_model_scores_real_essays():
    """Test model against known essay set."""

    model_path = "models/candidate/model.pkl"

    # Load holdout essays with known grades
    holdout_essays = await load_holdout_essays()

    # Score with model
    predictions = await score_essays(model_path, holdout_essays)

    # Verify agreement
    agreement = sum(
        pred.grade == essay.known_grade
        for pred, essay in zip(predictions, holdout_essays)
    ) / len(holdout_essays)

    assert agreement > 0.70, f"Agreement {agreement:.1%} below threshold"
```

## Success Criteria

### Technical
- [x] Model hot-reload without service restart
- [x] Inference latency < 100ms (p95)
- [x] Feature cache hit rate > 80%
- [x] Zero downtime during model updates
- [x] Rollback capability < 5 minutes

### Operational
- [x] Automated weekly training pipeline
- [x] Model validation gates enforced in CI
- [x] Prometheus metrics for all ML operations
- [x] Grafana dashboard for model performance
- [x] Integration with existing observability stack

### Quality
- [x] QWK > 0.70 before production deployment
- [x] Accuracy > 0.65
- [x] No distribution drift > 10%
- [x] Integration tests pass with real essays

## Future Enhancements

### Phase 2: Advanced Features
- A/B testing framework (route 10% traffic to candidate model)
- Online learning from teacher corrections
- Confidence-based human review routing
- Multi-model ensembling

### Phase 3: Migration to Dedicated Service
- Extract ML inference to separate service
- gRPC API for lower latency
- Model serving for multiple consumers (AI feedback service)
- GPU support for deep learning models

## Related

- `/Users/olofs_mba/Documents/Repos/huledu-reboot/TASKS/assessment/task-054-suggested-improvements-to-bayesian-model.md`
- `.agent/rules/020.7-cj-assessment-service.md`
- `docker-compose.services.yml`
- `observability/grafana/dashboards/cj-assessment/`
