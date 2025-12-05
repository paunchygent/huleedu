---
type: decision
id: ADR-0021
status: proposed
created: '2025-12-05'
last_updated: '2025-12-05'
---
# ADR-0021: ML Scoring Integration in NLP Service

## Status

Proposed

## Context

HuleEdu's CJ Assessment Service uses LLM-based Comparative Judgment to rank essays. This is inherently a **blackbox** approach - the LLM's decision process is opaque and non-deterministic.

We need a complementary **whitebox** assessment system that:
1. Provides explainable, deterministic quality scores
2. Acts as checks-and-balances against CJ rankings
3. Enables validation of CJ results against interpretable metrics
4. Supports research into essay quality factors

### Training Data

IELTS Writing Dataset (`data/cefr_ielts_datasets/ielts_writing_dataset.csv`):
- 5,432 essays with expert-assigned band scores (5.0-7.5)
- Component scores: Task Response, Coherence/Cohesion, Lexical Resource, Grammar

### Feature Architecture

Based on research (Faseeh et al. 2024, Uto et al. 2020, MSSF), the model uses a **hybrid feature approach with tiered hand-rolled features**:

1. **Primary: Dense Embeddings** - DeBERTa-v3-base (`microsoft/deberta-v3-base`, 768-dim)
   - [CLS] token pooling for document-level representation
   - Max length: 512 tokens (covers 95%+ IELTS essays)
   - Chosen over RoBERTa for superior [CLS] quality via disentangled attention
   - Relative position bias encodes essay structure (intro vs conclusion)

2. **Secondary: Tiered Hand-rolled Features** (~25 features)
   - **Tier 1 (Highest Signal)**: Error density (LanguageTool), readability indices (FK, SMOG, CL, ARI), core length metrics
   - **Tier 2 (Strong Signal)**: Syntactic complexity (spaCy), cohesion features, prompt relevance (sentence-transformers)
   - **Tier 3 (Refinement)**: Structure features, lexical overlap, pronoun ratios

3. **XGBoost Ordinal Regressor** (not classifier):
   - Objective: `reg:squarederror` (regression captures ordinal structure)
   - Predictions rounded to nearest 0.5 band, clipped to [5.0, 7.5]
   - Custom QWK evaluation metric for early stopping
   - Strong L2 regularization prevents embedding dominance over hand-rolled features

This hybrid approach provides:
- **Predictive power** from embeddings
- **Interpretability** from tiered hand-rolled features with proven research backing
- **Explainability** for teacher feedback via SHAP values

### Service Location Options

**Option A: CJ Assessment Service**
- Close to where CJ scores are computed
- Would couple whitebox/blackbox in same service

**Option B: NLP Service**
- Already handles text analysis and feature extraction
- Natural home for embedding computation and text metrics
- Maintains separation between CJ (ranking) and ML (scoring)

## Decision

Implement ML essay scoring in **NLP Service** as a whitebox complement to CJ Assessment.

### Rationale

1. **Separation of concerns**: CJ Assessment owns blackbox ranking; NLP Service owns whitebox scoring
2. **Feature extraction home**: NLP Service already handles text analysis
3. **Checks-and-balances**: Independent service provides genuine validation of CJ results
4. **Embedding computation**: NLP Service is appropriate home for transformer inference

### Architecture

```
services/nlp_service/
├── features/
│   ├── student_matching/          # Existing Phase 1
│   └── essay_scoring/             # NEW: Whitebox scoring
│       ├── protocols.py           # EssayScorerProtocol, FeatureExtractorProtocol
│       ├── models.py              # EssayFeatures, ScoringResult, TieredFeatures
│       ├── extractors/
│       │   ├── deberta_embeddings.py      # DeBERTa-v3-base (768-dim, [CLS] pooling)
│       │   ├── tier1_error_readability.py # LanguageTool + textstat
│       │   ├── tier2_syntactic_cohesion.py # spaCy + sentence-transformers
│       │   ├── tier3_structure.py         # Paragraph/intro/conclusion
│       │   └── feature_combiner.py        # Merge embeddings + all tiers
│       ├── training/
│       │   ├── data_loader.py          # IELTS dataset loader
│       │   ├── trainer.py              # XGBoost ordinal regressor training
│       │   ├── evaluation.py           # QWK, metrics, feature importance
│       │   └── explainability.py       # SHAP integration
│       └── implementations/
│           └── essay_scorer_impl.py    # Inference implementation
├── ml_models/
│   └── essay_scoring/
│       └── v1.0.0/
│           ├── xgboost_regressor.pkl   # XGBoost ordinal regressor
│           ├── deberta_config.json     # DeBERTa-v3-base model config
│           └── metadata.json           # Feature list, training metrics, hyperparams
└── cli_ml.py                           # pdm run nlp-ml-train
```

### Feature Pipeline

```
Essay Text + Prompt
    │
    ├──> DeBERTa-v3-base [CLS] ──> [768-dim embedding]
    │
    ├──> Tier 1 (LanguageTool + textstat) ──> [~11 features]
    │         ├── grammar_density, spelling_density, punct_errors
    │         ├── flesch_kincaid, smog, coleman_liau, ari
    │         └── avg_sentence_length, ttr, word_count, avg_word_length
    │
    ├──> Tier 2 (spaCy + sentence-transformers) ──> [~9 features]
    │         ├── parse_tree_depth, clause_count, passive_ratio, dep_distance
    │         ├── connective_diversity, sent_similarity_variance
    │         └── prompt_similarity, intro_prompt_sim, min_para_relevance
    │
    └──> Tier 3 (heuristics) ──> [~5 features]
              ├── paragraph_count, has_intro, has_conclusion
              └── lexical_overlap, pronoun_noun_ratio
    │
    └──> Concatenate ──> [~793-dim combined vector]
                              │
                              └──> XGBoost Regressor ──> Round to 0.5 ──> Band Score (5.0-7.5)
```

### Integration with CJ Assessment

The whitebox score can be used to:
1. **Validate CJ rankings**: Flag essays where ML score diverges significantly from CJ rank
2. **Quality gate**: Require agreement between CJ and ML before finalizing grades
3. **Research**: Analyze which hand-rolled features correlate with CJ judgments
4. **Explainability**: Provide teachers with interpretable quality signals

## Consequences

### Positive

- **Interpretable assessment**: Hand-rolled features explain score drivers via SHAP
- **Independent validation**: Whitebox vs blackbox cross-check
- **Research capability**: Compare feature importance across assessment methods
- **Deterministic**: Same essay always produces same ML score
- **Teacher-facing explanations**: SHAP waterfall plots and natural language summaries

### Negative

- **Model size**: DeBERTa-v3-base adds ~400MB to container
- **Inference latency**: Transformer + feature extraction adds ~100-500ms per essay
- **Feature dependencies**: LanguageTool, spaCy models, sentence-transformers, SHAP add startup overhead
- **Training complexity**: Requires GPU for efficient transformer inference during training

### Mitigations

| Concern | Mitigation |
|---------|------------|
| Model size | DeBERTa-v3-base is smaller than RoBERTa Large (~400MB vs ~1.3GB) |
| Latency | Batch inference, pre-compute embeddings, lazy-load feature extractors |
| Dependencies | Initialize LanguageTool/spaCy at service startup, cache models |
| GPU training | Train in separate environment, deploy only inference |
| Embedding dominance | Strong L2 regularization + column sampling preserves hand-rolled interpretability |

## Related

- EPIC-010: ML Essay Scoring Pipeline
- Rule 020.15: NLP Service Architecture
- Rule 020.7: CJ Assessment Service Architecture
