---
id: 'TASK-052K-IETLS-MODEL-INTEGRATION-PLAN'
title: 'TASK-052K — CEFR/IELTS Scoring Model Integration Plan'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'integrations'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-17'
last_updated: '2025-11-17'
related: []
labels: []
---
# TASK-052K — CEFR/IELTS Scoring Model Integration Plan

## 1. Objective

Deliver a production-quality scoring component that maps NLP + LanguageTool features to CEFR/IELTS bands so teachers receive meaningful proficiency indicators alongside raw metrics.

## 1.1 Label Source Clarification

- Training data currently comes from `data/cefr_ielts_datasets/IELTS-writing-task-2-evaluation/`.
- Authoritative human annotation is the IELTS overall `band` column; no CEFR labels exist in the raw data.
- CEFR bands used in modeling are **derived** via the agreed lookup (`>=8.5→C2`, `>=7.0→C1`, `>=6.0→B2`, `>=5.0→B1`, `>=4.0→A2`, `<4.0→A1`) during preprocessing (see `scripts/data_preparation/prepare_ielts_task2_dataset.py`).
- Modeling artifacts must retain the original IELTS band while optionally storing the derived CEFR label/code for convenience.

## 2. Key Placement Decisions

### 2.1 Inference Location (WHERE the model runs)

- **Recommended**: Result Aggregator Service (RAS) gains an "analytics" module that performs model inference after NLP metrics are persisted.
  - Rationale: RAS already owns cross-phase aggregation and has all metric fields in one place; keeps NLP service lean and focused on feature extraction.
  - Alternative (deferred): dedicated analytics microservice if inference load or model lifecycle becomes complex.

### 2.2 Training Environment (WHERE the model is built)

- **Recommended**: Offline ML workspace (e.g., `ml/cefr_scoring/` repo module or hosted notebook) using reproducible scripts run via CI job.
  - Use existing labeled datasets (CEFR corpora, IELTS scripts, internal rubrics). No production services run training.

### 2.3 Model Class Choice

- **Primary**: Gradient-boosted decision trees (XGBoost/LightGBM) on concatenated features.
  - Pros: Handles heterogeneous tabular data, interpretable feature importances, small model artifact (<5 MB), fast CPU inference for RAS.
- **Secondary**: Small feed-forward network only if tree-based baseline underperforms; requires GPU for training and less explainability.

### 2.4 RoBERTa Usage

- Keep HuggingFace `roberta-large` embeddings frozen during baseline training (mean pooled per essay). Fine-tuning occurs offline only if performance gaps remain.
- If fine-tuning: half-precision training on GPU, using essay text and prompt as input; export encoder weights separately and ensure inference runtime (probably ONNX or TorchScript) fits latency budget.

## 3. Workstream Breakdown

### 3.1 Data Curation & Governance

1. Inventory available labeled datasets (IELTS with band scores, any CEFR-native corpora, internal rubrics). Capture license, size, metadata.
2. Harmonize labels (map to CEFR A1–C2 and normalized IELTS 0–9 continuous scores).
3. Define train/validation/test splits stratified by prompt and source dataset.

### 3.2 Feature Extraction Pipeline

1. Implement dev team’s 50-signal feature extractor in NLP service (hand-engineered metrics + LanguageTool stats + readability + prompt alignment).
2. Persist all features to RAS schema (already expanded in TASK-052I) for reuse in model retraining.
3. Export training tables from RAS DB (or feature store) with `batch_id`, `essay_id`, label, features, embeddings.

### 3.3 Model Training

1. Build training script (e.g., `ml/cefr_model/train.py`) that:
   - Loads curated dataset parquet/CSV.
   - Computes z-scored handcrafted features and concatenates with RoBERTa embeddings (optionally PCA-reduced for stability).
   - Trains XGBoost classifier (multi-class CEFR) + regression head (IELTS) with shared features.
   - Outputs calibrated probabilities (Quadratic Weighted Kappa optimization).
2. Track metrics (macro-F1, QWK, RMSE) per dataset split.
3. Save artifacts: model binary, feature scaler, label encoder, config JSON.

### 3.4 Optional RoBERTa Fine-Tuning

1. If baseline underperforms, fine-tune RoBERTa encoder using multi-task loss (classification + regression) in a dedicated experiment pipeline.
2. Export fine-tuned encoder to ONNX; update inference stack (see 3.5) to load new encoder.

### 3.5 Inference Integration in RAS

1. Create `services/result_aggregator_service/implementations/cefr_scorer.py` that loads model artifact at startup (APP scope provider).
2. Extend NLP event handler to call scorer after persisting metrics; store CEFR band + probability + IELTS estimate in DB.
3. Expose fields via RAS API for dashboards; include explanation data (e.g., top contributing features from SHAP if using trees).

### 3.6 Validation & Monitoring

1. Backfill scores for historical essays; compare against human rubrics where available.
2. Add automated evaluation job that reruns training monthly and compares metrics (acceptance thresholds).
3. Instrument inference latency and drift (feature distribution monitoring).

## 4. Open Decisions

- Final choice of boosting library (XGBoost vs LightGBM) – decide after benchmarking on curated dataset.
- Whether to compress RoBERTa embeddings (e.g., PCA to 128 dims) for faster inference.
- Governance for model artifact versioning (MLflow? local registry?).

## 5. Next Steps

1. Approve plan for inference in RAS and offline training workflow.
2. Spin up dataset inventory task (owners: data science team).
3. Begin feature extractor refactor per dev team helper list (NLP service).
4. Prototype XGBoost baseline and report metrics before considering RoBERTa fine-tune.
