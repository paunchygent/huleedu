---
type: research
id: RES-ml-essay-scoring-source-traceability-matrix
title: "ML Essay Scoring Source Traceability Matrix"
status: active
created: 2025-12-06
source: docs/product/epics/ml-essay-scoring-pipeline.md
related:
  - docs/decisions/0021-ml-scoring-integration-in-nlp-service.md
last_updated: 2025-12-06
---

# EPIC-010: ML Essay Scoring Source Traceability Matrix

This document provides academic source traceability for all design decisions in EPIC-010 (ML Essay Scoring Pipeline) and ADR-0021 (ML Scoring Integration in NLP Service). Each architectural choice maps to peer-reviewed literature or established technical specifications.

## Complete Source Registry

| # | Citation | URL | Type |
|---|----------|-----|------|
| 1 | Faseeh, M. et al. (2024). "Hybrid Approach to Automated Essay Scoring." *Mathematics*, 12(21), 3416. | <https://www.mdpi.com/2227-7390/12/21/3416> | AES Architecture |
| 2 | Uto, M. & Xie, Y. (2020). "Neural Automated Essay Scoring Incorporating Handcrafted Features." *COLING 2020*, pp. 6077-6088. | <https://aclanthology.org/2020.coling-main.535/> | AES Architecture |
| 3 | Li, Y. et al. (2023). "Automatic Essay Scoring Method Based on Multi-Scale Features." *Applied Sciences*, 13(11), 6775. | <https://www.mdpi.com/2076-3417/13/11/6775> | Feature Engineering |
| 4 | Zhao, X. (2025). "A hybrid deep learning and fuzzy logic framework for feature-based evaluation." *Scientific Reports*, 15, 33657. | <https://www.nature.com/articles/s41598-025-17738-z> | AES Architecture |
| 5 | Aljuaid, H. et al. (2025). "TransGAT: Transformer-Based Graph Neural Networks for Multi-Dimensional AES." *arXiv:2509.01640*. | <https://arxiv.org/abs/2509.01640> | Embedding Models |
| 6 | Misgna, H. et al. (2024). "A survey on deep learning-based AES and feedback generation." *AI Review*, 58(2), 36. | <https://link.springer.com/article/10.1007/s10462-024-11017-5> | Survey/Overview |
| 7 | He, P. et al. (2021). "DeBERTa: Decoding-enhanced BERT with Disentangled Attention." *ICLR 2021*. | <https://openreview.net/pdf?id=XPZIaotutsD> | Embedding Models |
| 8 | Vallejo-Vera et al. (2024). "BERT, RoBERTa or DeBERTa? Comparing Performance." *JOP Working Paper*. | <https://svallejovera.github.io/files/bert_roberta_jop.pdf> | Model Comparison |
| 9 | Galke, L. et al. (2025). "Are We Really Making Much Progress in Text Classification? A Comparative Review." *arXiv:2204.03954v6*. | <https://arxiv.org/abs/2204.03954> | Model Comparison |
| 10 | Kahl, F. et al. (2025). "XGBOrdinal: An XGBoost Extension for Ordinal Data." *SHTI*, 327, 462-466. | <https://pubmed.ncbi.nlm.nih.gov/40380490/> | XGBoost/Ordinal |
| 11 | Thananusak et al. (2020). "Structural Explanation of Automated Essay Scoring." *EDM 2020*. | <https://educationaldatamining.org/files/conferences/EDM2020/papers/paper_259.pdf> | XGBoost/AES |
| 12 | Bartz-Beielstein et al. (2023). "Case Study II: Tuning of Gradient Boosting." *Springer*. | <https://link.springer.com/chapter/10.1007/978-981-19-5170-1_9> | Hyperparameter Tuning |
| 13 | Benton, T. (2021). "Comparative Judgement for Linking Two Existing Scales." *Frontiers in Education*, 6, 775203. | <https://doi.org/10.3389/feduc.2021.775203> | CJ Calibration |
| 14 | Bramley, T. (2005). "A Rank-Ordering Method for Equating Tests by Expert Judgment." *J. Applied Measurement*, 6, 202-223. | Referenced in Benton 2021 | CJ Calibration |
| 15 | Bramley, T. & Gill, T. (2010). "Evaluating the Rank-ordering Method for Standard Maintaining." *Research Papers in Education*, 25(3), 293-317. | <https://doi.org/10.1080/02671522.2010.498147> | CJ Calibration |
| 16 | Gabriel, J.S. & Kimura, M. (2025). "Enhancing AES Interpretability Using Triplet Loss with Rubric Anchors." *AIBB 2025, LNNS vol 1618*, Springer. | <https://link.springer.com/chapter/10.1007/978-3-032-04728-1_11> | Anchor Essays |
| 17 | Bradley, R.A. & Terry, M.E. (1952). "Rank Analysis of Incomplete Block Designs." *Biometrika*, 39, 324-345. | <https://doi.org/10.1093/biomet/39.3-4.324> | Statistical Foundation |
| 18 | Microsoft (2021). DeBERTa-v3-base Model Card. *Hugging Face*. | <https://huggingface.co/microsoft/deberta-v3-base> | Technical Spec |
| 19 | Rhode Island DOE (2013). "Writing Calibration Protocol." | <https://ride.ri.gov/sites/g/files/xkgbur806/files/Portals/0/Uploads/Documents/Common-Core/RIDE_Calibration_Process.pdf> | Practical Guidance |
| 20 | SAGE Encyclopedia (2018). "Holistic Scoring." *SAGE Encyclopedia of Educational Research, Measurement, and Evaluation*. | <https://methods.sagepub.com/reference/the-sage-encyclopedia-of-educational-research-measurement-and-evaluation/i10438.xml> | Reference |

---

## Design Element → Source Mapping

### A. Core Architecture Decisions

| Design Element | Sources | Key Evidence | EPIC-010 Section |
|----------------|---------|--------------|------------------|
| **Late fusion architecture** (embeddings + handcrafted → ensemble) | [1], [2], [4] | Faseeh: 0.941 QWK; Uto: +0.09 QWK improvement over BERT alone | Summary, US-010.3 |
| **Late fusion over deep fusion** (interpretability rationale) | [1], [6] | Faseeh: native feature importance; Misgna: interpretability limitations of end-to-end DL | ADR-0021 Rationale |
| **XGBoost as final predictor** | [1], [11] | Faseeh: proven on ASAP; Thananusak: 0.7667 QWK with feature importance | Phase 2, US-010.3 |
| **Regression objective for ordinal bands** | [1], [10], [11] | Faseeh: regression + QWK stopping; Kahl: ordinal regression extension validated | Model Configuration |

### B. Embedding Model Selection

| Design Element | Sources | Key Evidence | EPIC-010 Section |
|----------------|---------|--------------|------------------|
| **DeBERTa-v3 as backbone** | [4], [5], [7], [18] | Zhao/Aljuaid: recent AES convergence; He: architecture details | US-010.1 |
| **DeBERTa over RoBERTa** | [7], [8], [9] | He: +0.9% MNLI, +2.3% SQuAD; Vallejo-Vera: similar performance, 2× compute | US-010.1 Rationale |
| **Disentangled attention benefit** | [7], [18] | He: content/position separation improves contextual encoding | US-010.1 Rationale |
| **Frozen embeddings (not fine-tuned)** | [1], [2] | Faseeh/Uto: concatenation to XGBoost without end-to-end training | Phase 1 |
| **[CLS] token pooling** | [7], [18] | DeBERTa-v3 architecture; document-level representation | US-010.1 |

### C. Feature Engineering

| Design Element | Sources | Key Evidence | EPIC-010 Section |
|----------------|---------|--------------|------------------|
| **Error density (grammar/spelling)** | [1], [2], [3], [4] | All sources identify as high-predictive feature | US-010.2 Tier 1 |
| **Readability ensemble** (Flesch-Kincaid, SMOG, etc.) | [1], [3] | Faseeh: tier 1 feature; Li: multi-scale approach | US-010.2 Tier 1 |
| **Type-token ratio** (lexical diversity) | [1], [2], [4] | Consistently identified across hybrid AES literature | US-010.2 Tier 1 |
| **Syntactic complexity** (parse depth, dependency) | [2], [3] | Uto: significant contribution; Li: sentence-scale features | US-010.2 Tier 2 |
| **Prompt-essay similarity** | [3], [11] | Li: prompt relevance stream; Thananusak: prompt overlap ratio | US-010.2 Tier 2 |
| **Feature grouping for SHAP** | [4] | Zhao: Syntax, Cohesion, Vocabulary as dominant categories | US-010.4 |

### D. XGBoost Configuration

| Design Element | Sources | Key Evidence | EPIC-010 Section |
|----------------|---------|--------------|------------------|
| **Ordinal regression approach** | [10], [11] | Kahl: XGBOrdinal outperforms classifier/regressor; Thananusak: logistic objective | Model Configuration |
| **max_depth = 6** | [11], [12] | Thananusak: AES-specific; Bartz-Beielstein: bias-variance balance | US-010.3 Hyperparameters |
| **Low learning rate (0.03)** | [11], [12] | Thananusak: 0.001 for AES; general tuning guidance | US-010.3 Hyperparameters |
| **Strong L2 regularization (reg_lambda=2.0)** | [12] | Bartz-Beielstein: alpha/lambda have largest effect on performance | US-010.3 Hyperparameters |
| **Aggressive column sampling (0.6)** | [12] | Prevents embedding dominance; forces diverse splits | Model Configuration |
| **Early stopping with QWK** | [11], [12] | Thananusak: 100 epochs; prevents overfitting | Phase 2 |
| **QWK as evaluation metric** | [1], [11] | Field standard across all AES literature | Success Criteria |

### E. Explainability Architecture

| Design Element | Sources | Key Evidence | EPIC-010 Section |
|----------------|---------|--------------|------------------|
| **SHAP for feature explanation** | [4], [11] | Zhao: DeepSHAP for hybrid models; Thananusak: XGBoost feature importance | US-010.4, Phase 3 |
| **Hierarchical feature grouping** | [4] | Zhao: Syntax, Cohesion, Vocabulary categories | US-010.2 Tiers |
| **TreeExplainer for XGBoost** | [4], [11] | Exact, fast SHAP computation for tree models | US-010.4 |
| **Teacher-facing output format** | [4], [16] | Zhao: interpretable categories; Gabriel: rubric alignment | US-010.4 |

### F. Comparative Judgment & Calibration (CJ Assessment Integration)

| Design Element | Sources | Key Evidence | ADR-0021 Section |
|----------------|---------|--------------|------------------|
| **Bradley-Terry model for CJ** | [13], [14], [17] | Benton: core methodology; Bradley-Terry 1952: foundational | Integration with CJ |
| **Regression calibration** (score ↔ measure) | [13], [14], [15] | Benton: simplified pairs; Bramley: score-on-measure vs measure-on-score | Integration with CJ |
| **~300 comparisons sufficient** | [13] | Benton: simulation evidence for acceptable reliability | Integration with CJ |
| **Logistic regression for scale linking** | [13] | Benton: bypasses full Bradley-Terry, improved efficiency | Integration with CJ |

### G. Anchor-Based Validation (Future Scope)

| Design Element | Sources | Key Evidence | EPIC-010 Section |
|----------------|---------|--------------|------------------|
| **Anchor essays for calibration** | [13], [16], [19], [20] | Benton: representations across score range; Gabriel: rubric anchors; RIDE: practical protocol | Notes (future scope) |
| **12-24 anchors for linear calibration** | [13], [19] | Benton: ~50 representations typical; RIDE: multiple score points | Notes (future scope) |
| **Anchor selection 20-90% range** | [13] | Benton: deliberate selection for score spread | Notes (future scope) |
| **Leave-one-out cross-validation** | [13] | Benton: validation methodology for small anchor sets | Notes (future scope) |
| **Monotonicity checks on CJ ordering** | [13], [15] | Benton/Bramley: anchor inversion detection | Notes (future scope) |

---

## Source → Design Element Mapping

| Source | Design Elements Supported |
|--------|---------------------------|
| **[1] Faseeh 2024** | Late fusion architecture, XGBoost predictor, QWK metric, Handcrafted features, Regression objective |
| **[2] Uto 2020** | Late fusion pattern, Feature concatenation, Handcrafted feature benefit (+0.09 QWK) |
| **[3] Li 2023** | Multi-scale features, Readability metrics, Prompt relevance, Feature weighting |
| **[4] Zhao 2025** | DeBERTa selection, SHAP explainability, Feature grouping, LSTM fusion alternative |
| **[5] Aljuaid 2025** | DeBERTa-v3 backbone, Transformer + GAT architecture |
| **[6] Misgna 2024** | Interpretability rationale for hybrid approaches |
| **[7] He 2021** | DeBERTa architecture, RoBERTa comparison benchmarks, Disentangled attention |
| **[8] Vallejo-Vera 2024** | RoBERTa vs DeBERTa performance/compute tradeoff |
| **[9] Galke et al. 2025** | SLM superiority for classification, RoBERTa/DeBERTa SOTA status |
| **[10] Kahl 2025** | XGBoost ordinal regression, Frank-Hall decomposition |
| **[11] Thananusak 2020** | XGBoost AES hyperparameters, QWK validation, Feature importance |
| **[12] Bartz-Beielstein 2023** | Hyperparameter tuning methodology, Regularization effects |
| **[13] Benton 2021** | CJ calibration, Bradley-Terry, Simplified pairs, Anchor methodology |
| **[14] Bramley 2005** | Foundational CJ equating method |
| **[15] Bramley & Gill 2010** | Regression calibration comparison |
| **[16] Gabriel & Kimura 2025** | Anchor essays in AES, Triplet loss with rubric anchors, Interpretability |
| **[17] Bradley-Terry 1952** | Statistical foundation for pairwise comparison |
| **[18] DeBERTa Model Card** | Technical specifications, Training details |
| **[19] RIDE 2013** | Practical anchor calibration protocol |
| **[20] SAGE Holistic Scoring** | Anchor essay methodology reference |

---

## Coverage Summary

| Design Category | # Sources | Coverage Status | Primary Sources |
|-----------------|-----------|-----------------|-----------------|
| Core Architecture | 6 | ✅ Complete | [1], [2], [4], [6], [10], [11] |
| Embedding Model Selection | 6 | ✅ Complete | [4], [5], [7], [8], [9], [18] |
| Feature Engineering | 5 | ✅ Complete | [1], [2], [3], [4], [11] |
| XGBoost Configuration | 4 | ✅ Complete | [10], [11], [12] |
| Explainability | 3 | ✅ Complete | [4], [11], [16] |
| CJ & Calibration | 5 | ✅ Complete | [13], [14], [15], [17] |
| Anchor Validation | 5 | ✅ Complete | [13], [16], [19], [20] |

---

## Traceability to EPIC-010 Sections

| EPIC-010 Section | Supporting Sources |
|------------------|-------------------|
| **Summary** | [1], [2], [7] |
| **Phase 1: Feature Engineering** | [1], [2], [3], [4], [7], [18] |
| **Phase 2: Model Training** | [1], [10], [11], [12] |
| **Phase 3: Evaluation & Serving** | [4], [11] |
| **US-010.1: DeBERTa Embedding** | [7], [8], [9], [18] |
| **US-010.2: Tiered Features** | [1], [2], [3], [4] |
| **US-010.3: XGBoost Regressor** | [1], [10], [11], [12] |
| **US-010.4: Explainability** | [4], [11], [16] |
| **US-010.5: Model Serving** | [4], [11] |
| **Model Configuration** | [7], [10], [11], [12], [18] |
| **Success Criteria** | [1], [4], [11] |

## Traceability to ADR-0021 Sections

| ADR-0021 Section | Supporting Sources |
|------------------|-------------------|
| **Context** | [1], [2], [6] |
| **Feature Architecture** | [1], [2], [3], [4], [7], [10] |
| **Rationale** | [1], [6], [7] |
| **Architecture** | [1], [2], [4], [11] |
| **Feature Pipeline** | [1], [2], [3], [4] |
| **Integration with CJ** | [13], [14], [15], [17] |
| **Consequences** | [4], [6], [7], [11] |

---

## Source Validation Status (2025-12-06)

| Status | Count | Sources |
|--------|-------|---------|
| ✅ Verified | 17 | [1], [2], [3], [4], [5], [6], [7], [10], [11], [12], [13], [15], [16], [17], [18], [19], [20] |
| ⚠️ PDF only | 2 | [8], [14] (content not machine-readable, but URLs valid) |
| 🔄 Corrected | 1 | [9] (was "Bennani-Smires", now "Galke et al.") |

### Validation Notes

- **Source [9]**: Citation corrected from "Bennani-Smires et al." to actual authors "Galke, Scherp et al."
- **Source [16]**: Verified - Gabriel & Kimura (2025) published in AIBB 2025 (Springer LNNS vol 1618). URL returns 303 redirect which is normal for Springer.
- **Sources [19], [20]**: URLs were incomplete placeholders; now corrected to full URLs.

---

## Notes

All design decisions in EPIC-010 and ADR-0021 now have traceable source support for:
- Academic review and documentation
- Justification of architectural choices to stakeholders
- Future literature review and methodology updates

Key benchmark to target: **Faseeh et al. (2024) achieved 0.941 QWK** using a similar late-fusion hybrid architecture with XGBoost on the ASAP dataset.
