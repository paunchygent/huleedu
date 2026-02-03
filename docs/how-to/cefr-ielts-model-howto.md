# How-To: Build the CEFR/IELTS Scoring Model

> Status (2026-02-03): The repo IELTS dataset is **blocked** until the source and licensing are validated.
> Do not use IELTS-based runs for reported metrics or decisions. For the canonical research workflow
> (current dataset: ELLIPSE train/test), use `docs/operations/ml-nlp-runbook.md`.

This guide walks you through every step of creating the scoring component that maps our NLP and LanguageTool features to CEFR/IELTS proficiency bands. It assumes you can run Python scripts but are **new to machine learning**—we explain every concept as we go.

---

## 1. Why We Need This Model

Teachers see dozens of raw metrics (word count, MTLD, grammar errors, etc.), but they need a **single proficiency indicator** aligned with the scales they already use (CEFR A1–C2 or IELTS 0–9). We will train a model that:

1. Takes the features the NLP service already extracts.
2. Learns from essays with known CEFR/IELTS labels.
3. Produces a predicted CEFR band and IELTS score for new essays.

---

## 2. Glossary of Key ML Concepts

Before we dive in, here are the main terms you will encounter:

| Term | Plain-language explanation |
|------|-----------------------------|
| **Feature** | A measurable property of an essay, e.g., `mtld` or `grammar_error_rate_p100w`. Features are the inputs to our model. |
| **Label** | The outcome we want to predict. Here, the label is the teacher’s CEFR band or IELTS score. |
| **Embedding** | A long numeric vector produced by a language model (e.g., RoBERTa) that captures the overall meaning of an essay. |
| **Mean pooling** | When you run a language model, you get a vector for every token. “Mean pooling” means we average those token vectors so we end up with one embedding per essay. |
| **Gradient-boosted decision trees** | A family of models that combine many small decision trees. Each new tree “boosts” the model by focusing on the mistakes of the previous trees. Popular implementations: XGBoost, LightGBM. They work very well on tabular (column-based) data. |
| **Feed-forward neural network** | The classic neural network: layers of neurons connected in sequence. “Small feed-forward network” means just a few layers and hundreds of parameters. We only consider this if boosted trees underperform. |
| **Classifier vs. regressor** | A classifier predicts categories (e.g., CEFR A1, A2, …). A regressor predicts continuous numbers (e.g., IELTS 6.5). We need both because CEFR is discrete while IELTS is continuous. |
| **Multi-task learning** | Training one model to perform multiple related tasks at once (here, CEFR classification and IELTS regression). Shared features help each task learn better. |
| **Fine-tuning** | Adjusting a pre-trained language model (like RoBERTa) on our specific dataset so it learns nuances of essays relevant to our scoring. |

---

## 3. Overview of the Workflow

1. **Collect labeled data** – essays with known CEFR/IELTS scores.
2. **Extract features** – the 50 engineered signals + LanguageTool metrics + RoBERTa embeddings.
3. **Prepare a training dataset** – one row per essay with features and labels.
4. **Train a baseline model** – gradient-boosted trees (XGBoost) that predict CEFR and IELTS simultaneously.
5. **Evaluate performance** – check accuracy and error metrics; inspect feature importance.
6. **Optional: fine-tune RoBERTa** – only if accuracy is not good enough.
7. **Package the model** – save model weights, scalers, and configuration.
8. **Integrate into RAS** – load the model after NLP metrics are stored and return predictions through the API.
9. **Monitor** – track drift, re-train periodically.

We will go step by step.

---

## 4. Step-by-Step Guide

### Step 1: Collect and Harmonize Labeled Essays

1. **Inventory available datasets**
   - CEFR-aligned corpora (e.g., learner corpora with A1–C2 labels).
   - IELTS essays with band scores (e.g., `chillies/IELTS-writing-task-2-evaluation`). Use only the **human-labelled overall band score** column; ignore AI-generated sub-score text.
   - Internal teacher-graded essays.

2. **Unify labels**
   - Map CEFR labels to integers (A1=0 … C2=5) for classification.
   - Keep IELTS as floating point numbers (e.g., 6.5) for regression.
   - If you only have CEFR, convert to approximate IELTS using published lookup tables for evaluation convenience.

3. **Split data**
   - Training set (70%), validation set (15%), test set (15%).
   - Stratify by label (each split should have similar label proportions).
   - Stratify by prompt where possible so the model doesn’t just memorize topics.

### Step 2: Extract Hand-engineered Features

Our dev team provided a 50-feature blueprint. Implement those helpers in the NLP service’s feature extractor (see TASK-052J/TASK-052I notes). For historical essays, run a backfill script that recalculates features and stores them in RAS.

> **Reminder:** The Hugging Face dataset includes AI-generated sub-score explanations. Do not train on those columns. Use only the human-scored band (`overall_band_score`).

**Why these features matter:**
- Grammar & mechanics (error rates) help detect correctness.
- Vocabulary range metrics (MTLD, Zipf) measure lexical variety.
- Syntactic complexity (mean sentence length, clause ratios) highlights structural sophistication.
- Cohesion metrics (sentence similarity, lexical overlap) identify flow.
- Readability and task alignment ensure the essay matches the prompt at the right level.

### Step 3: Generate RoBERTa Embeddings (Mean Pooled)

1. Use HuggingFace `roberta-large` (or a similar transformer) to encode each essay.
2. Tokenize the essay; run it through the model to get hidden states per token.
3. Mean pooling: average all token hidden states to produce a single 1024-dimensional vector per essay.
   - Why average? It gives us a fixed-size representation regardless of essay length and is simple yet effective.
4. Store embeddings alongside hand-engineered features (e.g., in Parquet files or a feature store).

### Step 4: Build the Training Dataset

Create a table where each row contains:
- Essay ID and metadata (for traceability).
- Z-scored hand features (mean=0, std=1). Use `sklearn.StandardScaler`.
- RoBERTa embedding (optionally reduce to 256–512 dimensions via PCA for stability).
- CEFR label (integer) + IELTS score (float).

Save the dataset to disk so training scripts can load it quickly.

### Step 5: Train the Baseline Model (XGBoost)

1. **Why gradient-boosted trees?**
   - They excel at tabular data with mixed feature scales.
   - Training is fast and does not require GPUs.
   - They provide feature importances, which we can translate into teacher-facing explanations.

2. **Training approach**
   - Use XGBoost’s scikit-learn API (`XGBClassifier`, `XGBRegressor`).
   - Multi-task setup: train a classifier for CEFR and a regressor for IELTS using the same feature matrix.
     - Sharing features is fine because both tasks use the same signals to interpret proficiency.
     - Keep two separate models (one classifier, one regressor) but train them in the same script.
   - Hyperparameters to start with:
     ```python
     params = {
         "max_depth": 6,
         "learning_rate": 0.05,
         "n_estimators": 500,
         "subsample": 0.8,
         "colsample_bytree": 0.8,
         "reg_lambda": 1.0,
     }
     ```
   - Use early stopping on the validation set to prevent overfitting.

3. **Evaluate**
   - For CEFR: accuracy, macro F1, quadratic weighted kappa (QWK).
   - For IELTS: root mean squared error (RMSE), mean absolute error (MAE).
   - Inspect confusion matrix to see which bands are confused.
   - Extract feature importances (`model.feature_importances_`). Share the top contributors with the pedagogy team for sanity checks.

4. **Calibration**
   - If CEFR probabilities are over/under-confident, fit a calibration layer (e.g., isotonic regression) on validation predictions.

### Step 6: Optional – Fine-tune RoBERTa

Only proceed if the tree baseline is not meeting accuracy goals.

1. **Why fine-tune?**
   - The pre-trained RoBERTa embedding may not capture learner-essay nuances (e.g., subtle grammar errors or prompt alignment). Fine-tuning can adapt it to our domain.

2. **How to fine-tune**
   - Use a GPU environment (local workstation or cloud VM).
   - Build a PyTorch Lightning or HuggingFace Trainer script that:
     - Loads essay text and prompt.
     - Applies multi-task loss: cross-entropy for CEFR classification + MSE for IELTS regression.
     - Keeps most transformer layers frozen initially; unfreeze gradually if needed.
   - Train for a few epochs, monitor validation metrics.

3. **Export**
   - Convert the fine-tuned model to ONNX or TorchScript for efficient inference.
   - Update the training dataset to use the new embeddings.
   - Re-train the XGBoost models on the updated features (or replace them with a shallow neural head if fine-tuned representations are strong enough).

### Step 7: Package the Model

For each artifact, save:
- `cefr_classifier.json` – XGBoost classifier (use `model.save_model()`).
- `ielts_regressor.json` – XGBoost regressor.
- `feature_scaler.pkl` – StandardScaler parameters.
- `embedding_config.json` – notes on embedding dimension, PCA, and encoder version.
- `metadata.json` – dataset version, training date, evaluation metrics.

Store them in a versioned artifact repository (e.g., `models/cefr/v1/`).

### Step 8: Integrate into Result Aggregator Service

1. Create a scorer module (`services/result_aggregator_service/implementations/cefr_scorer.py`).
2. Load artifacts at application startup (APP scope provider in DI).
3. When `EssayNlpCompletedV1` is processed:
   - Read feature row from DB.
   - Reconstruct feature vector (apply scaler, append embedding).
   - Run classifier to get CEFR probabilities.
   - Run regressor for IELTS estimate.
   - Persist predictions and confidence to the database.
4. Update RAS API responses to include `predicted_cefr_band`, `predicted_ielts`, and `confidence_breakdown`.
5. Add logging for inference latency and prediction summaries.

### Step 9: Monitoring & Retraining

1. **Backfill**
   - Run a one-time job scoring all historical essays.
   - Compare model outputs with human rubrics where available.

2. **Scheduled evaluation**
   - Set up a monthly CI job that re-runs training on the latest data snapshot.
   - If metrics drop below thresholds, alert the product/DS team.

3. **Drift monitoring**
   - Track feature distributions over time (e.g., mean MTLD, grammar error rates). Large shifts may indicate data drift or prompt changes.
   - Track prediction distribution by class; sudden spikes in a band may warrant investigation.

---

## 5. Frequently Asked Questions

**Q: Why not rely on RoBERTa alone?**  
A: Pure transformer models can reach high accuracy, but they act as black boxes. Our hand-engineered features keep the output interpretable and ensure signal quality even when essays contain unusual formatting.

**Q: Why train two models (classifier + regressor)?**  
A: CEFR bands are ordinal categories, while IELTS is a continuous scale. Training a classifier respects the band structure, while a regressor predicts precise band scores (e.g., 6.5). Sharing the same features keeps implementation simple.

**Q: When should we fine-tune RoBERTa?**  
A: Only after the boosted-tree baseline has been benchmarked. Fine-tuning is costlier and requires GPU infrastructure. If we already hit the accuracy/QWK targets with the baseline, there is no need to fine-tune.

**Q: How big is the final feature vector?**  
A: 50 engineered features + 1024 embedding dimensions = 1074 values (before any PCA). This is well within XGBoost’s sweet spot.

**Q: Can we explain predictions to teachers?**  
A: Yes. Boosted trees allow SHAP (SHapley Additive exPlanations) analysis. We can show that high MTLD and low grammar errors pushed a prediction toward C1, for example.

---

## 6. Checklist

- [ ] All 50 engineered metrics implemented in NLP extraction pipeline.
- [ ] Labeled datasets inventoried and split.
- [ ] Training dataset (features + labels) exported.
- [ ] XGBoost baseline trained and evaluated.
- [ ] Artifacts saved with metadata.
- [ ] RAS scorer module implemented and wired.
- [ ] Backfill job executed; monitoring dashboards set up.

With these steps complete, you will have a reproducible, explainable CEFR/IELTS scoring pipeline that aligns our NLP metrics with the standards teachers rely on.
