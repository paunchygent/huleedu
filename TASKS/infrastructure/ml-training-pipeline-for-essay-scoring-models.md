---
id: ml-training-pipeline-for-essay-scoring-models
title: ML Training Pipeline for Essay Scoring Models
type: task
status: proposed
priority: medium
domain: infrastructure
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-12-05'
last_updated: '2026-02-01'
related: []
labels: []
---
# ML Training Pipeline for Essay Scoring Models

## Objective

Implement a production-ready ML training pipeline for essay scoring models using gradient boosting for ordinal classification, with experiment tracking, model registry, and complete integration with HuleEdu's existing infrastructure.

## Context

**Educational Platform (HuleEdu)**:
- Swedish 8-grade system: F, E, D, D+, C, C+, B, A
- Training data: Teacher-graded essays from PostgreSQL (500-2000 essays)
- Feature pipeline: Already implemented (49 engineered features + 384-dim embeddings)
- Target: Gradient Boosting for ordinal classification (limited data scenario)

**Existing Infrastructure**:
- PDM monorepo with Python 3.11
- Dishka DI framework with protocols and implementations
- asyncpg + SQLAlchemy async
- Docker/Docker Compose
- Prometheus metrics
- Structured logging with structlog

**Key Requirements**:
- DDD architecture with protocols and implementations
- Async-first where applicable (data loading)
- Configuration via Pydantic Settings
- Export to ONNX for inference optimization
- Integration with existing observability stack

## Plan

### Phase 1: Library Structure and Core Components

**1.1 Create `libs/huleedu_ml_training` package**:
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/huleedu_ml_training/`
- Structure:
  ```
  libs/huleedu_ml_training/
  ├── pyproject.toml
  ├── src/huleedu_ml_training/
  │   ├── __init__.py
  │   ├── config.py                    # Pydantic Settings
  │   ├── data/
  │   │   ├── __init__.py
  │   │   ├── protocols.py             # DataLoaderProtocol, DataSplitterProtocol
  │   │   ├── loader.py                # PostgreSQL async data loader
  │   │   └── splitter.py              # Stratified train/val/test splits
  │   ├── models/
  │   │   ├── __init__.py
  │   │   ├── protocols.py             # ModelProtocol, CalibratorProtocol
  │   │   ├── ordinal_classifier.py    # Gradient Boosting wrapper
  │   │   └── calibration.py           # Confidence calibration
  │   ├── training/
  │   │   ├── __init__.py
  │   │   ├── protocols.py             # TrainerProtocol, ValidatorProtocol
  │   │   ├── trainer.py               # Training orchestration
  │   │   ├── hyperparameter.py        # Optuna integration
  │   │   └── validation.py            # Cross-validation
  │   ├── registry/
  │   │   ├── __init__.py
  │   │   ├── protocols.py             # ModelRegistryProtocol
  │   │   └── postgres_registry.py     # PostgreSQL-backed registry
  │   ├── metrics/
  │   │   ├── __init__.py
  │   │   └── evaluation.py            # Classification metrics
  │   └── cli.py                        # Typer CLI interface
  └── tests/
      ├── unit/
      └── integration/
  ```

**1.2 Configuration Management**:
- `config.py` with Pydantic Settings for:
  - Database connection (PostgreSQL)
  - Training hyperparameters
  - Model export paths
  - MLflow tracking (optional)
  - Logging configuration

**1.3 Data Loading**:
- Async PostgreSQL data loader using SQLAlchemy
- Load teacher-graded essays with features
- Protocol-based design for testability

**1.4 Data Splitting**:
- Stratified train/val/test splits
- Preserve grade distribution
- Reproducible splits with seed control

### Phase 2: Model Implementation

**2.1 Ordinal Classifier**:
- Gradient Boosting wrapper (LightGBM/XGBoost)
- Ordinal regression support
- ONNX export capability
- Protocol-based interface

**2.2 Calibration**:
- Isotonic/Platt calibration for confidence scores
- Separate calibration on validation set
- Integrated into inference pipeline

**2.3 Evaluation Metrics**:
- Classification accuracy
- Mean Absolute Error (MAE) for ordinal targets
- Confusion matrix
- Per-grade precision/recall
- Calibration metrics (Brier score, ECE)

### Phase 3: Training Pipeline

**3.1 Training Orchestration**:
- Trainer class with early stopping
- Checkpoint saving
- Progress logging with structlog
- Prometheus metrics integration

**3.2 Hyperparameter Tuning**:
- Optuna integration for hyperparameter search
- Cross-validation within optimization
- Configurable search space

**3.3 Cross-Validation**:
- Stratified k-fold CV
- Temporal validation (if timestamps available)
- Nested CV for hyperparameter tuning

### Phase 4: Model Registry

**4.1 PostgreSQL-Backed Registry**:
- Schema design for model metadata:
  ```sql
  CREATE TABLE ml_models (
    id UUID PRIMARY KEY,
    model_name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    stage VARCHAR NOT NULL,  -- dev, staging, production
    model_path VARCHAR NOT NULL,
    metrics JSONB,
    hyperparameters JSONB,
    feature_names JSONB,
    metadata JSONB
  );
  ```

**4.2 Version Management**:
- Date-based versioning (YYYYMMDD_HHMMSS)
- Promotion workflow (dev → staging → production)
- Rollback support
- Migration scripts (Alembic)

**4.3 Model Storage**:
- Local filesystem for development
- S3-compatible storage (optional, future)
- ONNX and native format storage

### Phase 5: CLI Interface

**5.1 Training Commands**:
```bash
pdm run train-essay-grader train \
  --config config.yaml \
  --experiment-name "ordinal-gb-v1"

pdm run train-essay-grader evaluate \
  --model-path models/model_20250101_120000 \
  --test-data-path data/test.parquet

pdm run train-essay-grader tune \
  --config config.yaml \
  --n-trials 100

pdm run train-essay-grader compare \
  --model-a models/model_v1 \
  --model-b models/model_v2
```

**5.2 Registry Commands**:
```bash
pdm run train-essay-grader registry list
pdm run train-essay-grader registry promote \
  --model-id abc123 \
  --stage production
pdm run train-essay-grader registry rollback \
  --model-name essay-scorer
```

### Phase 6: Integration and Testing

**6.1 Unit Tests**:
- Data loader tests (with test fixtures)
- Model wrapper tests
- Calibration tests
- Metrics calculation tests

**6.2 Integration Tests**:
- End-to-end training pipeline
- Model registry operations
- CLI command execution

**6.3 Docker Integration**:
- Dockerfile for training jobs
- docker-compose for training environment
- Volume mounts for model artifacts

### Phase 7: Documentation

**7.1 Runbook**:
- `/Users/olofs_mba/Documents/Repos/huledu-reboot/docs/operations/ml-training-runbook.md`
- Training procedures
- Hyperparameter tuning guide
- Model promotion workflow
- Troubleshooting

**7.2 ADR**:
- Document model architecture decisions
- Ordinal regression choice
- Registry design
- Export format selection

## Success Criteria

### Functional Requirements:
- [ ] Complete library structure under `libs/huleedu_ml_training`
- [ ] Async data loader reading from PostgreSQL
- [ ] Stratified data splitting with reproducibility
- [ ] Gradient boosting ordinal classifier with ONNX export
- [ ] Confidence calibration implementation
- [ ] Hyperparameter tuning with Optuna
- [ ] PostgreSQL-backed model registry with migration scripts
- [ ] Complete CLI interface with all commands working
- [ ] ONNX model export verified

### Quality Requirements:
- [ ] All code follows DDD patterns (protocols + implementations)
- [ ] Comprehensive unit tests (>80% coverage)
- [ ] Integration tests for end-to-end pipeline
- [ ] Structured logging with correlation IDs
- [ ] Prometheus metrics for training jobs
- [ ] Type checking passes (`pdm run typecheck-all`)
- [ ] Linting passes (`pdm run format-all && pdm run lint-fix --unsafe-fixes`)

### Documentation Requirements:
- [ ] Operational runbook created
- [ ] ADR for model architecture
- [ ] CLI help text complete
- [ ] Code docstrings (Google style)
- [ ] README in library root

### Integration Requirements:
- [ ] PDM scripts added to root `pyproject.toml`
- [ ] Docker configuration for training jobs
- [ ] Integration with existing observability stack
- [ ] Configuration via environment variables

## Implementation Notes

**Data Schema Assumptions**:
- Essays table with: `essay_id`, `text_content`, `grade`, `created_at`
- Features table with: `essay_id`, `feature_vector` (JSONB or separate columns)
- Grade mapping to ordinal integers: F=0, E=1, D=2, D+=3, C=4, C+=5, B=6, A=7

**Model Choice Rationale**:
- Gradient Boosting: Works well with limited data (500-2000 samples)
- Ordinal regression: Respects grade ordering
- LightGBM: Fast, efficient, good with tabular data
- ONNX export: Cross-platform inference

**Feature Engineering**:
- Leverage existing `huleedu_nlp_shared.feature_pipeline`
- 49 engineered features already implemented
- 384-dim embeddings from text analysis
- Total: ~433 features per essay

**Observability Integration**:
- Use `huleedu_service_libs.logging` for structured logging
- Prometheus metrics for:
  - Training duration
  - Model performance (accuracy, MAE)
  - Data loading times
  - Hyperparameter search progress

## Related

- Feature Pipeline: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/huleedu_nlp_shared/src/huleedu_nlp_shared/feature_pipeline/`
- DI Patterns: `.agent/rules/042-async-patterns-and-di.md`
- Database Standards: `.agent/rules/053-sqlalchemy-standards.md`
- Testing Methodology: `.agent/rules/075-test-creation-methodology.md`
- Python Standards: `.agent/rules/050-python-coding-standards.md`
