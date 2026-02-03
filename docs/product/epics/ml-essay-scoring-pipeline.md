---
type: epic
id: EPIC-010
title: ML Essay Scoring Pipeline
status: draft
phase: 1
sprint_target: null
created: '2025-12-05'
last_updated: '2026-02-02'
---
# EPIC-010: ML Essay Scoring Pipeline

## Summary

Build a **whitebox** ML pipeline for automated essay scoring as a checks-and-balances system against CJ Assessment's **blackbox** LLM-based ranking. The model uses DeBERTa-v3-base embeddings (768-dim) combined with research-backed interpretable features (~25-30) and XGBoost ordinal regression to predict a validated **Overall** target score (current research baseline: ELLIPSE).

**Business Value**: Independent, explainable essay quality assessment that validates CJ rankings and provides interpretable quality signals for teachers and researchers via SHAP explanations.

**Research Foundation**: Feature selection based on Faseeh et al. (2024), Uto et al. (2020), and MSSF work. DeBERTa-v3-base chosen for superior [CLS] token quality with frozen embeddings. XGBoost regression approach captures ordinal structure better than classification.

**Scope Boundaries**:
- **In Scope**: DeBERTa-v3-base embedding extraction ([CLS] pooling), tiered hand-rolled feature pipeline, XGBoost ordinal regression with QWK early stopping, SHAP explainability, model serving in NLP Service
- **Out of Scope**: Swedish grade mapping (future; requires grade-scale behavior report), automated CJ validation pipeline (future)

## Deliverables

### Phase 1: Feature Engineering & Data Pipeline
- [ ] Data loader for canonical AES dataset (current: ELLIPSE train/test in `data/ELLIPSE_TRAIN_TEST/`; IELTS dataset is blocked pending source validation)
- [ ] DeBERTa-v3-base embedding extractor (768-dim, [CLS] pooling, max_length=512)
- [ ] Tier 1 feature extractors (highest predictive value):
  - [ ] Error density features (LanguageTool: grammar, spelling, punctuation density)
  - [ ] Readability indices (Flesch-Kincaid, SMOG, Coleman-Liau, ARI ensemble)
  - [ ] Core length metrics (avg_sentence_length, ttr, word_count, avg_word_length)
- [ ] Tier 2 feature extractors (strong signal):
  - [ ] Syntactic complexity (spaCy: parse_tree_depth, clause_count, passive_ratio, dep_distance)
  - [ ] Cohesion features (connective_diversity, sentence_similarity_variance)
  - [ ] Prompt relevance (sentence-transformers: prompt_similarity, intro_prompt_sim, min_para_relevance)
- [ ] Tier 3 feature extractors (refinement):
  - [ ] Structure features (paragraph_count, has_intro, has_conclusion)
  - [ ] Additional metrics (lexical_overlap, pronoun_noun_ratio)
- [ ] Feature combiner (embeddings + ~25-30 hand-rolled → combined vector)
- [ ] Feature schema with Pydantic V2 models
- [ ] Train/validation/test split utilities
- [ ] Grade-scale behavior report (assumption-light diagnostics; required before Swedish mapping)

### Phase 2: Model Training Pipeline
- [ ] XGBoost ordinal regressor (`reg:squarederror` objective, predictions rounded to nearest 0.5 band)
- [ ] Custom QWK evaluation metric for early stopping (prevents overfitting)
- [ ] Strong L2 regularization + column sampling (prevents embedding dominance over hand-rolled features)
- [ ] Cross-validation framework (stratified 5-fold with QWK scoring)
- [ ] Hyperparameter tuning (RandomizedSearchCV over key params)
- [ ] Training CLI: `pdm run nlp-ml-train`

### Phase 3: Model Evaluation & Serving
- [ ] Evaluation metrics: QWK, adjacent accuracy, per-band F1
- [ ] SHAP explainability for teacher-facing score explanations
- [ ] Model artifact storage and versioning
- [ ] Hot-reload model serving in NLP Service
- [ ] Prometheus metrics for inference monitoring

## User Stories

### US-010.1: DeBERTa-v3-base Embedding Extraction
**As a** ML engineer
**I want to** extract DeBERTa-v3-base embeddings from essays
**So that** I capture semantic content and writing quality signals with superior [CLS] token quality.

**Acceptance Criteria**:
- [ ] DeBERTa-v3-base model loaded (`microsoft/deberta-v3-base`, 768-dim)
- [ ] [CLS] token pooling for document-level representation
- [ ] Max token length: 512 (validate per dataset; adjust if truncation impacts performance)
- [ ] Essays tokenized and embedded as 768-dim vectors
- [ ] Batch inference supported for efficiency
- [ ] Embeddings cacheable for repeated training runs

**Rationale**: DeBERTa-v3-base chosen over RoBERTa for:
- Better [CLS] aggregation quality (disentangled attention)
- Relative position bias encodes essay structure (intro vs conclusion)
- Field convergence: recent AES papers (2024-2025) use DeBERTa

### US-010.2: Tiered Hand-rolled Feature Extraction
**As a** ML engineer
**I want to** extract research-backed interpretable text features from essays
**So that** model predictions can be explained to teachers and features drive XGBoost splits.

**Acceptance Criteria**:

**Tier 1 (Highest Predictive Value)**:
- [ ] Error density: grammar_density, spelling_density, punct_errors (LanguageTool, normalized per 100 words)
- [ ] Readability ensemble: flesch_kincaid, smog, coleman_liau, ari (4 indices)
- [ ] Core length: avg_sentence_length, ttr, word_count, avg_word_length

**Tier 2 (Strong Signal)**:
- [ ] Syntactic complexity: parse_tree_depth, clause_count, passive_ratio, dep_distance (spaCy)
- [ ] Cohesion: connective_diversity, sent_similarity_variance
- [ ] Prompt relevance: prompt_similarity, intro_prompt_sim, min_para_relevance (sentence-transformers)

**Tier 3 (Refinement)**:
- [ ] Structure: paragraph_count, has_intro, has_conclusion
- [ ] Additional: lexical_overlap, pronoun_noun_ratio

**Implementation**:
- [ ] Features serialized as Pydantic models for type safety
- [ ] Each tier implemented as separate extractor module
- [ ] Total: ~25-30 features

### US-010.3: Train XGBoost Ordinal Regressor
**As a** ML engineer
**I want to** train an XGBoost ordinal regressor on combined embeddings + hand-rolled features
**So that** I can predict essay quality bands while respecting ordinal structure.

**Acceptance Criteria**:
- [ ] Load canonical dataset (current: ELLIPSE train/test; Overall target)
- [ ] Feature pipeline: DeBERTa embeddings (768-dim) + hand-rolled (~25 features) = ~793 total
- [ ] Stratified train/val/test split (70/15/15)
- [ ] XGBoost with `reg:squarederror` objective (regression captures ordinality)
- [ ] Custom QWK evaluation metric for early stopping
- [ ] Predictions post-processed to match the dataset label scale (rounding/clipping must be explicit)
- [ ] 5-fold cross-validation with QWK scoring
- [ ] Model achieves QWK > 0.60 on validation set

**Key Hyperparameters** (per architect recommendations):
- `max_depth`: 6 (balances bias-variance with 800 features)
- `learning_rate`: 0.03 (low for stability)
- `reg_lambda`: 2.0 (strong L2 prevents embedding dominance)
- `colsample_bytree`: 0.6 (aggressive sampling for correlated embeddings)
- `early_stopping_rounds`: 100 (with QWK metric)

### US-010.4: Evaluate Model Performance & Explainability
**As a** ML engineer
**I want to** evaluate model performance with ordinal metrics and generate explanations
**So that** I understand prediction quality and can explain scores to teachers.

**Acceptance Criteria**:
- [ ] Quadratic Weighted Kappa (QWK) computed
- [ ] Adjacent accuracy (within ±0.5 band) reported
- [ ] Confusion matrix by band score
- [ ] XGBoost feature importance analysis
- [ ] SHAP values for per-prediction explanations
- [ ] SHAP summary plots showing feature contributions across dataset
- [ ] Verify hand-rolled features appear in top importance (not dominated by embeddings)
- [ ] Bias detection for essay length correlation

**Teacher-Facing Explainability**:
- [ ] SHAP waterfall plots for individual essays
- [ ] Natural language templates: "Score influenced by: high grammar error density (-0.3), strong readability (+0.2)"

### US-010.5: Serve Model in NLP Service
**As a** developer
**I want to** load trained models in NLP Service for inference
**So that** whitebox scoring can validate CJ Assessment results.

**Acceptance Criteria**:
- [ ] DeBERTa-v3-base model and XGBoost regressor loaded at startup
- [ ] Graceful fallback if model files missing
- [ ] Inference latency < 500ms per essay (includes embedding + feature extraction)
- [ ] Prometheus metrics for predictions and latency
- [ ] Feature extraction dependencies (spaCy, LanguageTool) initialized at startup
- [ ] SHAP TreeExplainer initialized for on-demand explanations

## Technical Architecture

### Whitebox vs Blackbox Relationship
```
┌─────────────────────────────────────────────────────────────┐
│                      Essay Batch                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌───────────────────┐       ┌───────────────────┐
│   CJ Assessment   │       │    NLP Service    │
│   (BLACKBOX)      │       │   (WHITEBOX)      │
│                   │       │                   │
│ LLM Comparative   │       │ DeBERTa + Features│
│ Judgment Rankings │       │ Quality Scores    │
└─────────┬─────────┘       └─────────┬─────────┘
          │                           │
          └─────────────┬─────────────┘
                        ▼
              ┌─────────────────┐
              │  Cross-check &  │
              │   Validation    │
              └─────────────────┘
```

### Data Source
```
data/ELLIPSE_TRAIN_TEST/
├── ELLIPSE_Final_github_train.csv
└── ELLIPSE_Final_github_test.csv

Columns (subset):
- full_text (essay text)
- prompt (writing prompt)
- Overall (target)
```

Blocked:
- `data/cefr_ielts_datasets/ielts_writing_dataset.csv` (do not use for claims until source/licensing is validated)

### Feature Architecture

| Layer | Features | Dimensions | Tool |
|-------|----------|------------|------|
| **DeBERTa-v3-base Embeddings** | [CLS] token pooling, max_length=512 | 768 | transformers |
| **Tier 1 (Highest Signal)** | | | |
| └── Error density | grammar_density, spelling_density, punct_errors | 3+ | LanguageTool |
| └── Readability | flesch_kincaid, smog, coleman_liau, ari | 4 | textdescriptives |
| └── Core length | avg_sentence_length, ttr, word_count, avg_word_length | 4 | spaCy |
| **Tier 2 (Strong Signal)** | | | |
| └── Syntactic | parse_tree_depth, clause_count, passive_ratio, dep_distance | 4 | spaCy |
| └── Cohesion | connective_diversity, sent_similarity_variance | 2 | spaCy |
| └── Prompt relevance | prompt_similarity, intro_prompt_sim, min_para_relevance | 3 | sentence-transformers |
| **Tier 3 (Refinement)** | | | |
| └── Structure | paragraph_count, has_intro, has_conclusion | 3 | regex/heuristics |
| └── Additional | lexical_overlap, pronoun_noun_ratio | 2 | spaCy |
| **Combined Vector** | embeddings + ~25 hand-rolled | **~793** | |

### Service Structure
```
services/nlp_service/
├── features/
│   ├── student_matching/        # Existing Phase 1
│   └── essay_scoring/           # NEW: Whitebox scoring
│       ├── __init__.py
│       ├── protocols.py         # EssayScorerProtocol, FeatureExtractorProtocol
│       ├── models.py            # EssayFeatures, ScoringResult, TieredFeatures
│       ├── extractors/
│       │   ├── deberta_embeddings.py      # DeBERTa-v3-base (768-dim, [CLS] pooling)
│       │   ├── tier1_error_readability.py # LanguageTool + textdescriptives
│       │   ├── tier2_syntactic_cohesion.py # spaCy + sentence-transformers
│       │   ├── tier3_structure.py         # Paragraph/intro/conclusion
│       │   └── feature_combiner.py        # Merge embeddings + all tiers
│       ├── training/
│       │   ├── data_loader.py          # Load canonical AES dataset (ELLIPSE baseline; IELTS blocked)
│       │   ├── trainer.py              # XGBoost ordinal regressor training
│       │   ├── evaluation.py           # QWK, metrics, feature importance
│       │   └── explainability.py       # SHAP integration
│       └── implementations/
│           └── essay_scorer_impl.py
├── ml_models/
│   └── essay_scoring/
│       └── v1.0.0/
│           ├── xgboost_regressor.pkl   # XGBoost ordinal regressor
│           ├── deberta_config.json     # DeBERTa-v3-base model config
│           └── metadata.json           # Feature list, training metrics, hyperparams
└── cli_ml.py                           # pdm run nlp-ml-train
```

### Model Configuration

**Embedding Model**:
- Model: `microsoft/deberta-v3-base` (768-dim)
- Pooling: [CLS] token (document-level representation)
- Max length: 512 tokens (validate per dataset; adjust if truncation is material)
- Rationale: Superior [CLS] quality via disentangled attention; relative position bias encodes essay structure

**XGBoost Ordinal Regressor**:
- Objective: `reg:squarederror` (regression captures ordinal structure better than classification)
- Predictions: Post-processed to match the dataset label scale (rounding/clipping must be explicit)
- Early stopping: Custom QWK evaluation metric

**Key Hyperparameters** (architect recommendations):
```python
params = {
    'objective': 'reg:squarederror',
    'max_depth': 6,              # Balances bias-variance with ~800 features
    'learning_rate': 0.03,       # Low for stability
    'n_estimators': 1500,        # High with early stopping
    'min_child_weight': 5,       # Prevents overfitting
    'reg_lambda': 2.0,           # Strong L2 prevents embedding dominance
    'colsample_bytree': 0.6,     # Aggressive sampling for correlated embeddings
    'subsample': 0.8,
    'early_stopping_rounds': 100,
}
```

**Regularization Rationale**:
- Strong L2 (`reg_lambda=2.0`): Prevents embedding dimensions from dominating hand-rolled features—critical for whitebox interpretability
- Aggressive column sampling (`colsample_bytree=0.6`): Forces trees to find diverse splits across correlated embedding dimensions

**Validation**: 5-fold stratified CV with QWK scoring

## Related Documents
- ADR-0021: ML Scoring Integration in NLP Service (`docs/decisions/0021-ml-scoring-integration-in-nlp-service.md`)
- Source Traceability Matrix (`docs/research/epic-010-ml-essay-scoring-source-traceability.md`)

## Dependencies

### Infrastructure
- NLP Service operational
- Canonical dataset available: `data/ELLIPSE_TRAIN_TEST/` (IELTS dataset is blocked pending validation)

### Python Packages
- **Embeddings**: transformers, torch (`microsoft/deberta-v3-base`)
- **Regressor**: xgboost, scikit-learn
- **Tier 1 Features**: language-tool-python, textdescriptives, spaCy
- **Tier 2 Features**: spacy (en_core_web_sm), sentence-transformers
- **Data**: pandas, numpy
- **Explainability**: shap (TreeExplainer for XGBoost)

## Success Criteria
- QWK > 0.60 on held-out test set
- Adjacent accuracy > 0.85 (within ±0.5 band)
- Inference latency < 500ms per essay (includes embedding + feature extraction)
- Training pipeline runnable via single CLI command
- XGBoost feature importance shows Tier 1 hand-rolled features in top splits (not dominated by embeddings)
- SHAP explanations generate meaningful teacher-facing feedback
- Regularization prevents embedding dominance over interpretable features

## Grade-Scale Behavior Report (Template)

Complete this report **before** any Swedish grade mapping work. Do not assume equal spacing between grade bands until validated by data.

**Dataset & Context**
- Dataset version/source:
- Grade scale definition (labels + rubric reference):
- Prompt/task coverage:
- Rater context (single vs multiple raters; moderation process):

**Distribution Checks**
- Overall grade distribution:
- Per-prompt grade distributions:
- Missingness or sparsity notes:

**Assumption-Light Diagnostics**
- Monotonicity: Spearman correlation between latent score and grade:
- Isotonic fit shape (monotone curve notes):
- Boundary spacing: overlap between adjacent grade score distributions:
- Prompt/cohort stability: cut-point shifts across subsets:
- Adjacent confusion matrix (most frequent near-boundary errors):
- Length bias check (correlation with length proxies):

**Mapping Decision**
- Chosen mapping: learned cut-points / isotonic / fixed intervals (only with evidence)
- Rationale:
- Open questions / risks:

**Decision Outcome**
- Approved by:
- Date:
- Next review trigger:

## Notes
- **Whitebox purpose**: Independent validation of CJ blackbox rankings
- IELTS↔CEFR mapping is not canonical; do not rely on it without a sourced reference and validated dataset.
- Swedish grade mapping is future scope (requires labeled Swedish data)
- Automated CJ validation pipeline is future scope (compare whitebox scores to CJ ranks)
