# HANDOFF: Current Session Context

## Purpose

This document contains ONLY what the next developer needs to pick up work.
All completed work, patterns, and decisions live in:

- **TASKS/** – Detailed task documentation with full implementation history
- **readme-first.md** – Sprint-critical patterns, ergonomics, quick start
- **AGENTS.md** – Workflow, rules, and service conventions
- **.agent/rules/** – Implementation standards

## Editing Rules (Do Not Ignore)

- Treat this file as **append-only** for active workstreams.
- Do **not** change the `status:` frontmatter of any `TASKS/**` file unless that task is **in the current session scope** or the user explicitly asks.
- **Only completed tasks** may be removed, and only from the **RECENTLY COMPLETED** section.
- Before removing/compressing anything under **RECENTLY COMPLETED**, first decide if it is
  **critical sprint developer knowledge**; if yes, compact/migrate it into
  `.claude/work/session/readme-first.md` instead of deleting it.

---

## CURRENT FOCUS (2025-12-12)

### Teacher Dashboard Live Data Integration

- Next story: Phase 5 `TASKS/programs/teacher_dashboard_integration/bff-extended-dashboard-fields.md`
- Programme hub: `TASKS/programs/teacher_dashboard_integration/HUB.md`

---

## CURRENT FOCUS (2026-02-01)

### Whitebox Essay Scoring Research Build (Standalone)

- Task: `TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md`
- Scope: Research pipeline only (no Kafka/outbox/DI/service wiring).
- Added: `scripts/ml_training/essay_scoring/` modular pipeline (dataset loader, splitters,
  tiered feature extractors, embeddings, feature combiner, XGBoost trainer/eval,
  SHAP artifacts, grade-scale report) + CLI entrypoint.
- PDM script: `essay-scoring-research` → `python -m scripts.ml_training.essay_scoring.cli`
- Dependencies: new `ml-research` group in `pyproject.toml` (xgboost, torch,
  transformers, shap, spacy, sentence-transformers, textdescriptives, wordfreq,
  lexical-diversity, langdetect, gensim, nltk, etc.).
- Added `tiktoken` + `sentencepiece` to `ml-research` for DeBERTa tokenizer support.
- Note: macOS requires OpenMP runtime for XGBoost (`brew install libomp`).
- Update: Tier 1 readability now uses TextDescriptives (spaCy) and a shared spaCy
  `nlp` instance is wired through `FeaturePipeline` for Tier 1 + Tier 2 extractors.
- Docs aligned to TextDescriptives for readability indices in EPIC/ADR references.
  - Renamed non-kebab files in `docs/research/` to satisfy docs validator.
- Added Matplotlib cache setup to avoid unwritable home cache warnings.
- Added Rich logging for research runs (console + per-run `run.log`).
- Ruff now excludes `output/` to avoid linting cached LanguageTool files.

Update (2026-02-04):
- Added CV-first follow-up tasks for prediction power improvements:
  - `TASKS/assessment/essay-scoring-cv-ensembling-ellipse-cv-first.md`
  - `TASKS/assessment/essay-scoring-ordinal-custom-objective-experiments-qwk.md`
  - `TASKS/assessment/essay-scoring-construct-validity-audit--feature-candidates.md`
- Prepared ELLIPSE (200–1000 words) artifacts + reusable CV splits for the CV-first story:
  - Prepared dataset: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_train_prepared.csv`
  - Prepared dataset: `output/essay_scoring/20260204_135541_ellipse_prep_200_1000/artifacts/datasets/ellipse_test_prepared.csv`
  - Splits JSON: `output/essay_scoring/20260204_135554_ellipse_splits_200_1000/artifacts/splits.json`
  - Next: run CV baselines (`scheme=stratified_text` + `scheme=prompt_holdout`) using this splits file.
- Added machine-readable progress monitoring for long runs:
  - New file per run dir: `progress.json` (substage processed/total + ETA).
  - Tracking task: `TASKS/assessment/essay-scoring-progressjson-counters-for-long-runs.md`
  - Runbook note: `docs/operations/ml-nlp-runbook.md`
- CV-first Gate A (ablation) + Gate B (drop-column) completed on ELLIPSE (200–1000 words):
  - Story hub: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
  - Drop-column metrics: `output/essay_scoring/20260204_180603_ellipse_drop_column_combined_stratified_text_20260204_190546/artifacts/drop_column_importance.json`
  - Next: Gate C residual diagnostics by prompt + grade band.
- Update (2026-02-04): Gate C residual diagnostics implementation landed (CV now writes per-record
  residuals + `reports/residual_diagnostics.md`). Next: rerun the baseline CV
  (`feature_set=combined`, `scheme=prompt_holdout`) with `--reuse-cv-feature-store-dir` and record
  the produced report path back into the story hub + Gate C task.

Update (2026-02-04, later):
- Gate C baseline CV residual diagnostics run completed (combined + prompt_holdout, feature-store reuse):
  - `output/essay_scoring/20260204_193204_ellipse_cv_combined_prompt_holdout_residuals_20260204_203200/reports/residual_diagnostics.md`
- Two follow-up tasks created based on Gate C findings (grade compression / tail bias + feature-discipline validation):
  - `TASKS/assessment/essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout.md`
  - `TASKS/assessment/essay-scoring-tail-calibration--grade-band-imbalance-mitigation.md`
- Story hub updated to group work into single-axis tracks (avoid combinatorics):
  - `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- CV now supports pruned handcrafted predictor tests (column filtering; no re-extraction):
  - CLI flags: repeatable `--predictor-handcrafted-keep <feature_name>` (allowlist) and
    `--predictor-handcrafted-drop <feature_name>` (denylist) for `cv` runs
  - Artifacts:
    - `artifacts/predictor_feature_selection.json`
    - `artifacts/cv_metrics.json` includes `predictor_feature_selection`
    - `reports/cv_report.md` prints predictor selection summary lines
- Gate B prompt-holdout pruned predictor run started (denylist v1; reuses baseline CV feature store):
  - Run dir: `output/essay_scoring/20260204_204456_ellipse_cv_combined_prompt_holdout_pruned_handcrafted_20260204_214450/`
  - Driver log: `output/essay_scoring/ellipse_cv_combined_prompt_holdout_pruned_handcrafted_20260204_214450.driver.log`
  - Selection artifact (already written): `output/essay_scoring/20260204_204456_ellipse_cv_combined_prompt_holdout_pruned_handcrafted_20260204_214450/artifacts/predictor_feature_selection.json`
- Gate B prompt-holdout pruning validated (decision-ready):
  - Adopt “drop 3” predictor prune: `has_conclusion`, `clause_count`, `flesch_kincaid`
  - Evidence run dir: `output/essay_scoring/20260204_204929_ellipse_cv_combined_prompt_holdout_prune_drop3_20260204_214922/`
  - Task closed out: `TASKS/assessment/essay-scoring-validate-pruned-handcrafted-subset-under-prompt-holdout.md`

Update (2026-02-05):
- CV now supports an explicit training-mode switch for ordinal experiments:
  - `pdm run essay-scoring-research cv --training-mode regression|ordinal_multiclass_expected|ordinal_multiclass_argmax`
  - Code: `scripts/ml_training/essay_scoring/training/training_modes.py` + wiring in CV runner.
  - Task context: `TASKS/assessment/essay-scoring-ordinal-custom-objective-experiments-qwk.md`
- Gate D tail calibration / imbalance mitigation tooling added (CV-only):
  - Training-time weighting flags:
    - `--grade-band-weighting {none,sqrt_inv_freq}`
    - `--grade-band-weight-cap <float>`
  - Post-hoc mapping flag:
    - `--prediction-mapping {round_half_band,qwk_cutpoints_lfo}` (leave-one-fold-out cutpoints; leak-safe)
  - Calibration artifacts (when enabled):
    - `artifacts/calibration_cutpoints_by_fold.json`
    - `artifacts/calibration_summary.json`
- Gate D experiment matrix completed (prompt_holdout CV, combined, drop-3 predictor, feature-store reuse):
  - A baseline: `output/essay_scoring/20260205_163458_ellipse_gate_d_baseline_prompt_holdout_drop3_20260205_173454/` (QWK: 0.62210 ± 0.01743)
  - B weighting-only: `output/essay_scoring/20260205_170701_ellipse_gate_d_weighting_prompt_holdout_drop3_20260205_180657/` (QWK: 0.63516 ± 0.01650)
  - C calibration-only: `output/essay_scoring/20260205_170843_ellipse_gate_d_calibration_prompt_holdout_drop3_20260205_180838/` (QWK: 0.68615 ± 0.01029)
  - D weighting+calibration: `output/essay_scoring/20260205_171050_ellipse_gate_d_weighting_calibration_prompt_holdout_drop3_20260205_181046/` (QWK: 0.68360 ± 0.01470)
- Gate D decision: adopt weighting+calibration as the default for CV-first selection (best high-tail adjacent accuracy; QWK within noise vs calibration-only).
- Gate E XGBoost hyperparameter sweep completed (prompt_holdout; combined; drop-3; weighting+calibration; feature-store reuse):
  - Sweep dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/`
  - Best config: `config_id=97e84d798d` (max_depth=4, min_child_weight=20, reg_lambda=2.0, reg_alpha=0.0)
  - Best run dir: `output/essay_scoring/20260205_192751_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746/variants/20260205_194952_ellipse_gate_e_xgb_sweep_prompt_holdout_drop3_wcal_20260205_202746_97e84d798d/`
  - Stratified_text sanity check run: `output/essay_scoring/20260205_202126_ellipse_gate_e_xgb_bestparams_stratified_text_20260205_212122/`

Update (2026-02-05):
- Gate F CV ensembling implemented:
  - `pdm run essay-scoring-research cv --ensemble-size <N>` trains N models per fold (seed ensemble) and averages
    predictions before metrics + residual diagnostics.
  - Code: `scripts/ml_training/essay_scoring/cross_validation.py`, `scripts/ml_training/essay_scoring/cv_shared.py`,
    `scripts/ml_training/essay_scoring/cli.py`, `scripts/ml_training/essay_scoring/reports/cv_report.py`
  - Tests: `scripts/ml_training/essay_scoring/tests/test_cv_ensembling.py`
- Prompt-holdout experiments (combined; drop-3; weighting+calibration; best XGB params; feature-store reuse):
  - `ensemble_size=1` run: `output/essay_scoring/20260205_213805_ellipse_gate_f_cv_ensemble1_prompt_holdout_drop3_wcal_bestparams_20260205_223800/`
    - CV val QWK mean±std: `0.68460 ± 0.01659`
    - High tail adjacent_acc (`y_true>=4.0`): `0.87907`
  - `ensemble_size=3` run: `output/essay_scoring/20260205_213920_ellipse_gate_f_cv_ensemble3_prompt_holdout_drop3_wcal_bestparams_20260205_223917/`
    - CV val QWK mean±std: `0.68573 ± 0.01755`
    - High tail adjacent_acc (`y_true>=4.0`): `0.83411` (regression)
  - `ensemble_size=5` run: `output/essay_scoring/20260205_214118_ellipse_gate_f_cv_ensemble5_prompt_holdout_drop3_wcal_bestparams_20260205_224115/`
    - CV val QWK mean±std: `0.68946 ± 0.01533`
    - High tail adjacent_acc (`y_true>=4.0`): `0.85271` (regression)
- Decision: keep `ensemble_size=1` as best-current. Ensembling increases mean QWK but degrades high-tail adjacent
  accuracy (primary yardstick / guardrail).
- Task closed out: `TASKS/assessment/essay-scoring-cv-ensembling-ellipse-cv-first.md`

Local verification (2026-02-01):
- `pdm lock -G ml-research`
- `pdm install -G ml-research`
- `brew install libomp`
- `pdm run pytest-root scripts/ml_training/tests -v`
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`
- `pdm run typecheck-all`

Additional verification (2026-02-01):
- `pdm lock -G ml-research`
- `pdm install -G ml-research`
- `pdm run essay-scoring-research --help` (warned about non-writable matplotlib/fontconfig caches; suggests setting `MPLCONFIGDIR`)
- `pdm run essay-scoring-research run --help`
- `pdm run essay-scoring-research ablation --dataset-path /tmp/ielts_small_ablation.csv` (downloaded LanguageTool + model weights; long-running)
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`
- `pdm run typecheck-all`
- `pdm run validate-tasks`
- `pdm run python scripts/task_mgmt/index_tasks.py --root "$(pwd)/TASKS" --out "/tmp/huleedu_tasks_index.md" --fail-on-missing`
- `pdm run python scripts/docs_mgmt/validate_docs_structure.py --verbose`

Additional verification (2026-02-01, later run):
- `pdm install -G ml-research` (installed `tiktoken`, `sentencepiece`)
- `pdm run essay-scoring-research ablation --dataset-path /tmp/ielts_small_ablation.csv`
  - Outputs:
    - `output/essay_scoring/20260201_091815_handcrafted`
    - `output/essay_scoring/20260201_092125_embeddings`
    - `output/essay_scoring/20260201_092230_combined` (SHAP PNGs + grade report)

### Hemma Offload (LanguageTool + DeBERTa/spaCy) — Planning + Docs (2026-02-01)

- Tasks:
  - `TASKS/infrastructure/hemma-operations-runbooks-huleedu--gpu.md`
  - `TASKS/infrastructure/huleedu-devops-codex-skill-for-hemma-server.md`
  - `TASKS/assessment/offload-deberta--spacy-features-to-hemma-binary-embedding-service.md`
- Runbooks:
  - `docs/operations/hemma-server-operations-huleedu.md`
  - `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`
- ADR:
  - `docs/decisions/0025-hemma-hosted-nlp-feature-offload-for-essay-scoring-research-binary-protocol.md`
- Codex skill source:
  - `scripts/codex_skills/huledu-devops-hemma/SKILL.md`

Implementation progress (2026-02-01):
- Added research-scoped embedding offload server:
  - `scripts/ml_training/essay_scoring/offload/server.py`
  - `scripts/ml_training/essay_scoring/offload/Dockerfile`
- Wired research pipeline to optionally use Hemma via tunnel:
  - `scripts/ml_training/essay_scoring/config.py` (`OffloadConfig`)
  - CLI flags: `--embedding-service-url`, `--language-tool-service-url`
- Updated runbooks:
  - `docs/operations/hemma-alpha-rollout-days-1-3.md`
  - `docs/operations/hemma-server-operations-huleedu.md`
- Enforced “public surface = API/BFF/WS only” via config:
  - `docker-compose.hemma.research.yml` binds `language_tool_service` to `127.0.0.1:8085`
  - Optional compose profile `research-offload` adds `essay_embed_offload` bound to `127.0.0.1:9000`
- Reduced Hemma image bloat for offload:
  - `pyproject.toml` adds `offload-runtime` dependency group (no training deps)
  - `scripts/ml_training/essay_scoring/offload/Dockerfile` exports only `offload-runtime` (`pdm export --no-default`)

Hemma deploy verified (2026-02-01):
- Git sync (canonical): `~/apps/huleedu` reset to `origin/main` at `2c3e4008` (no scp drift).
- Shared infra confirmed present:
  - external docker network: `hule-network`
  - shared DB container: `shared-postgres`
  - shared observability containers: `nginx-proxy`, `jaeger`, `loki`, `grafana`, `prometheus`
- Production `.env` generated/updated on Hemma (no secrets committed):
  - `HULEEDU_ENVIRONMENT=production`, `ENVIRONMENT=production`
  - `HULEEDU_DB_USER=huleedu_user`, `HULEEDU_PROD_DB_HOST=shared-postgres`, `HULEEDU_PROD_DB_PASSWORD=<set>`
  - DBs created for all services; `pg_trgm` enabled in `huleedu_spellchecker`
- KRaft infra up and healthy:
  - `huleedu_kafka` (`apache/kafka:3.8.0`) healthy, localhost-bound
  - `huleedu_redis` healthy, localhost-bound
  - `kafka_topic_setup` created 71 topics successfully
- Research services (localhost-only) up:
  - `huleedu_language_tool_service` healthy at `127.0.0.1:8085`
  - `huleedu_essay_embed_offload` healthy at `127.0.0.1:9000`
- Hemma deploy validation (2026-02-01):
  - Copied `.env` to `~/apps/huleedu/.env` (prod DB password still missing; required for full prod deploy)
  - Deployed `language_tool_service` with:
    - `sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml up -d --build language_tool_service`
  - Verified on Hemma:
    - `curl -fsS http://127.0.0.1:8085/healthz` → `status=healthy`
    - `curl -fsS http://127.0.0.1:9000/healthz` → `status=ok` (existing `huleedu-embed-offload` container)
  - Verified from Mac via tunnels:
    - `ssh -L 18085:127.0.0.1:8085 -N hemma` + `curl http://127.0.0.1:18085/healthz`
    - `ssh -L 19000:127.0.0.1:9000 -N hemma` + `curl http://127.0.0.1:19000/healthz`

Update (2026-02-01):
- Hemma `~/apps/huleedu/.env` is now production-valid (script: `./scripts/validate-production-config.sh`).
- `kafka_topic_setup` completed successfully (71 topics created).
- Offload container is compose-managed as `huleedu_essay_embed_offload` (old ad-hoc `huleedu-embed-offload` removed).
- Recommendation: set `HF_TOKEN` in Hemma `.env` to avoid Hugging Face Hub rate limiting for model downloads.

### TASKS Lifecycle v2 (Stories: review gate, status: done) — Implemented (2026-02-01)

- Decision: `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`
- Reference: `docs/reference/ref-tasks-lifecycle-v2.md`
- Changes:
  - `TASKS/` status enum is now work-state only (`proposed|in_review|approved|in_progress|blocked|paused|done|archived`).
  - `status: research` removed (research is now `docs/research/`).
  - Stories are review-gated (`in_review` → `approved`); tasks remain lean (no review gate).
- Tooling:
  - `pdm run validate-docs`
  - `pdm run index-tasks`
  - `pdm run migrate-task-statuses-v2 [--root <path>] --write`

---

## RECENTLY COMPLETED

- 2026-02-01: Kafka infra migrated to KRaft + Hemma shared-infra alignment (story: `TASKS/infrastructure/migrate-kafka-infra-to-kraft-and-align-hemma-shared-infra.md`, ADR: `docs/decisions/0028-kafka-infra-move-to-kraft-drop-zookeeper-and-align-hemma-shared-deployment.md`).
- 2026-02-01: Hemma research services (LanguageTool + embedding offload) deployed localhost-only via compose layering (runbooks: `docs/operations/hemma-server-operations-huleedu.md`, `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md`).
- 2026-02-01: TASKS lifecycle v2 implemented (ADR: `docs/decisions/0027-tasks-lifecycle-v2-story-review-gate-done-status-research-docs.md`).

---

## UPDATE (2026-02-02)

### Whitebox Essay Scoring: Hemma Offload Stability (macOS crash fix)

- Root issue: macOS Python process segfaulted in `libtorch_cpu` during Tier2 sentence embedding (`sentence-transformers`) calls.
- Fix: Tier2 now offloads all embedding work to Hemma when `--embedding-service-url` is provided (no local torch/sentence-transformers).
- Tier2 batching: embeddings are computed as one deduped batch per split (still chunked by request size inside the client).
- Tier3: reuse shared spaCy `nlp` from `FeaturePipeline` to avoid repeated spaCy model loads.
- Offload server tuning: `OFFLOAD_EMBEDDING_BATCH_SIZE` default set to 32 and exposed in `docker-compose.hemma.research.yml` (requires Hemma rebuild/redeploy to take effect).
- Log noise: filtered SWIG DeprecationWarnings (`swigvarlink` / `SwigPyObject` / `SwigPyPacked`) at import time.

### Verification: Full dataset run (Option A, feature-set=combined, Hemma offload)

- Health checks (Mac, via tunnels):
  - `curl -fsS http://127.0.0.1:18085/healthz`
  - `curl -fsS http://127.0.0.1:19000/healthz`

---

## UPDATE (2026-02-04)

### ENG5 NP Runner: R7 content upload caching

- Added disk-backed Content Service upload cache at `.claude/research/data/eng5_np_2016/content_upload_cache.json` plus `--force-reupload` to refresh storage IDs.
- Cache is ignored (and rewritten) when `--content-service-url` changes.
- Focused validation:
  - `pdm run pytest-root scripts/tests/test_eng5_np_manifest_caching.py scripts/cj_experiments_runners/eng5_np/tests/unit/test_execute_handler.py scripts/cj_experiments_runners/eng5_np/tests/unit/test_anchor_align_handler.py -v` ✅
- Status: `TASKS/programs/eng5/eng5-runner-assumption-hardening.md` is now **DONE** (R1–R7).
- Command:
  - `pdm run essay-scoring-research run --feature-set combined --dataset-path data/cefr_ielts_datasets/ielts_writing_dataset.csv --language-tool-service-url http://127.0.0.1:18085 --embedding-service-url http://127.0.0.1:19000 --run-name ielts_full_combined_hemma_tier2offload`
- Output dir:
  - `output/essay_scoring/20260201_235520_ielts_full_combined_hemma_tier2offload`
- Metrics (QWK):
  - train: 0.99888
  - val: 0.55534
  - test: 0.62423
- Grade-scale report (confirms 1.0–9.0 scale; predictions not clipped to 7.5):
  - `output/essay_scoring/20260201_235520_ielts_full_combined_hemma_tier2offload/reports/grade_scale_report.md`

---

## UPDATE (2026-02-03)

### Whitebox Essay Scoring: Fix “silent stall” observability (Tier2 Stage 1)

Root cause (confirmed via `run.log` timestamps):
- The perceived “stall at Tier1 item ~3328” was a short per-item hiccup (~11s).
- The real “no activity for minutes” gap was **Tier2 Stage 1** (spaCy parse + syntactic feature loop + unique-text collection) which previously had **no progress logging** until `Tier2 embeddings start`.

Changes (observability, no algorithm changes):
- Tier2 now logs:
  - Stage1 parse start + periodic progress + completion timing
  - Stage2 unique-text collection start + periodic progress (including `unique_texts` size) + completion timing
  - Existing embed start/complete + per-100 progress retained
  - Code: `scripts/ml_training/essay_scoring/features/tier2_syntactic_cohesion.py`
- Tier1 now logs:
  - start (mode=local/remote + concurrency + cache dir)
  - explicit “awaiting LanguageTool results” marker
  - completion timing
  - Code: `scripts/ml_training/essay_scoring/features/tier1_error_readability.py`
- Pipeline logs explicit tier start/complete timings:
  - Code: `scripts/ml_training/essay_scoring/features/pipeline.py`
- Run-level stage markers now write `status.json` (start/complete) during feature extraction + training/eval/SHAP/report:
  - CV feature store: `scripts/ml_training/essay_scoring/cv_shared.py`
  - Run/featurize: `scripts/ml_training/essay_scoring/runner.py`
- Runbook updated to document `run.log` + `status.json` and tier-stage logging:
  - `docs/operations/ml-nlp-runbook.md`

Verification (local):
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`
- `pdm run typecheck-all`
- `pdm run pytest-root scripts/ml_training/tests -v`

---

## UPDATE (2026-02-03)

### ML Research Pipeline: Test Coverage + Integration

- Added integration-style tests to cover the full research pipeline surface (CLI + runner + stores),
  while keeping heavy feature extraction off the critical test path.
- Key new tests (all under `scripts/ml_training/tests/`):
  - `test_feature_store_roundtrip.py` (persist/load + schema/dataset fingerprint validation)
  - `test_runner_reuse_feature_store.py` (end-to-end run via `reuse_feature_store_dir`)
  - `test_cli_smoke.py` (Typer CLI `--help` + `run` via reused feature store)
  - `test_remote_embedding_client_http.py` (real HTTP roundtrip against in-process offload server)
  - `test_drop_column_importance_integration.py` (drop-column using reused CV feature store)
  - `test_grade_scale_report.py` + `test_shap_explainability_smoke.py` (artifact generation smoke tests)
  - `test_spacy_pipeline.py` + `test_tier3_structure.py` (core plumbing/heuristics)
- Suppressed noisy SWIG DeprecationWarnings in pytest config:
  - `pyproject.toml` → `[tool.pytest.ini_options].filterwarnings`

Verification (2026-02-03):
- `source .env && pdm run pytest -c pyproject.toml -m "" scripts/ml_training/tests -q --cov=scripts/ml_training/essay_scoring --cov-report=term`
  - `41 passed`, coverage `84%` for `scripts/ml_training/essay_scoring`
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`
- `pdm run typecheck-all`

### ML Research Pipeline: Ports/Adapters seams (no monkeypatch)

- Refactored grade-scale report + SHAP artifact generator to accept injected dependencies
  (ports), removing the need for test-time monkeypatching and improving SRP/DDD/CC alignment:
  - `scripts/ml_training/essay_scoring/reports/grade_scale_report.py`
    - New optional `word_count_fn` (default: `count_words` from `text_processing.py`)
    - Removes hard dependency on loading spaCy for report word counts
  - `scripts/ml_training/essay_scoring/training/shap_explainability.py`
    - New `TreeExplainerProtocol` + `SummaryPlotProtocol`
    - New optional `explainer_factory` + `summary_plot_fn` with sensible defaults (lazy `import shap`)
- Tests updated to use dependency injection instead of monkeypatching:
  - `scripts/ml_training/tests/test_grade_scale_report.py`
  - `scripts/ml_training/tests/test_runner_reuse_feature_store.py`
  - `scripts/ml_training/tests/test_shap_explainability_smoke.py`

Verification (2026-02-03):
- `source .env && pdm run pytest -c pyproject.toml -m "" scripts/ml_training/tests -q`
- `pdm run format-all`
- `pdm run lint-fix --unsafe-fixes`
- `pdm run typecheck-all`

### Whitebox Essay Scoring: ELLIPSE train/test dataset support + “drop letter prompts” policy

- Dataset kind: `ellipse` (pre-split train/test CSVs in `data/ELLIPSE_TRAIN_TEST/`).
- Loader: `load_ellipse_train_test_dataset()` filters by prompt name and rejects identical-essay leakage across train/test.
- Policy: drop entire prompts that are letter-dominated; keep all essays for prompts that are not excluded (no per-essay “letter detection” filtering).
- Default excluded prompts (config `ellipse_excluded_prompts`):
  - `Community service`
  - `Grades for extracurricular activities`
  - `Cell phones at school`
  - `Letter to employer`

Verification (2026-02-03 local time):
- `source .env && pdm run pytest-root scripts/ml_training/tests -v` (15 passed)

---

## UPDATE (2026-02-04)

### Hemma Offload: single combined feature endpoint (one tunnel, no fallbacks)

- Implemented `POST /v1/extract` on the research offload server (`scripts/ml_training/essay_scoring/offload/server.py`).
  - Response is `application/zip` with `meta.json` + optional `embeddings.npy` / `handcrafted.npy`.
  - Includes `schema_version` + `server_fingerprint`; fingerprint includes `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION`.
- Mac-side Hemma mode is now single-tunnel:
  - CLI: `--backend hemma --offload-service-url http://127.0.0.1:19000`
  - `backend=hemma` fails fast if URL missing and forbids `embedding_service_url` / `language_tool_service_url`.
- Offload runtime + compose:
  - `docker-compose.hemma.research.yml` sets `OFFLOAD_LANGUAGE_TOOL_URL=http://language_tool_service:8085` and requires `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION`.
  - `pyproject.toml` `offload-runtime` now includes `spacy`, `textdescriptives`, and pinned `en_core_web_sm`.
- Artifacts:
  - `artifacts/offload_metrics.json` now includes `extract` request/cache metrics.
  - `artifacts/offload_extract_meta.json` is written for reproducibility when using Hemma backend.

Verification (2026-02-04):
- `source .env && pdm run format-all`
- `source .env && pdm run lint-fix --unsafe-fixes`
- `source .env && pdm run typecheck-all`
- `source .env && pdm run pytest-root scripts/ml_training/tests -q` (46 passed)
- `source .env && pdm run format-all` (clean)
- `source .env && pdm run lint-fix --unsafe-fixes` (clean)
- `source .env && pdm run typecheck-all` (clean)

### Whitebox Essay Scoring: Gold-standard ELLIPSE dataset prep + CV (Overall, 200–1000 words)

- New research CLI commands:
  - `pdm run essay-scoring-research prepare-dataset` (writes prepared train/test CSVs + integrity report)
  - `pdm run essay-scoring-research make-splits` (writes `splits.json` + split report; includes stratified_text + prompt_holdout)
  - `pdm run essay-scoring-research cv` (runs CV from `splits.json`, reuses a CV feature store to avoid re-extracting features)
- Filtering standard:
  - Drop letter-dominated prompts via `ellipse_excluded_prompts` (config default list).
  - Apply word-count window 200–1000 to **both** train and test.
- Artifacts:
  - Dataset prep: `<run_dir>/artifacts/datasets/*.csv` + `<run_dir>/reports/dataset_integrity_report.md`
  - Splits: `<run_dir>/artifacts/splits.json` + `<run_dir>/reports/splits_report.md`
  - CV: `<run_dir>/artifacts/cv_metrics.json` + `<run_dir>/reports/cv_report.md`
  - CV feature store: `<run_dir>/cv_feature_store/` (reusable via `--reuse-cv-feature-store-dir`)

Verification (2026-02-03 local time):
- `source .env && pdm run pytest-root scripts/ml_training/tests -v` (19 passed)
- `source .env && pdm run format-all` (clean)
- `source .env && pdm run lint-fix --unsafe-fixes` (clean)
- `source .env && pdm run typecheck-all` (clean; fixed CJ unit test mock to satisfy updated repository protocols)

### Whitebox Essay Scoring Research: Warm-cache feature store + 1.0–9.0 scale alignment (2026-02-02)

- New CLI command: `pdm run essay-scoring-research featurize` writes a reusable feature store under the run dir (`<run_dir>/feature_store/manifest.json`).
- `pdm run essay-scoring-research run` supports:
  - `--reuse-feature-store-dir <run_dir-or-feature_store_dir>` to skip feature extraction
  - `--skip-shap` and `--skip-grade-scale-report` for fast hyperparameter sweeps
- Feature extraction speedups:
  - Tier1 now uses `nlp.pipe(...)` + single-pass doc stats (no repeated `nlp(text)` per metric).
  - Tier3 now uses a single `Doc` for sentence overlap + POS counts (intro token count uses tokenizer-only `nlp.make_doc`).
  - Tier2/Tier3 now use a readability-free spaCy pipeline; Tier1 keeps TextDescriptives readability.
- Dataset loader now assigns stable per-row `record_id` (supports deterministic feature-store splits without dropping duplicated essays).
- Docs aligned to 1.0–9.0 IELTS Overall scale (ADR-0021 + EPIC-010).
- Tracking task: `TASKS/assessment/essay-scoring-research-warm-cache-feature-store--10-90-scale-alignment.md`

### ENG5 NP Runner Assumption Hardening (R4/R5 next)

- Task: `TASKS/programs/eng5/eng5-runner-assumption-hardening.md` (R1–R3 ✅; R4/R5 pending).
- Decision (grade-scale ownership): runner resolves `grade_scale` from CJ `assessment_instructions` and supports `--expected-grade-scale` assertion only; `--grade-scale` removed.
- Known drift: `.agent/rules/020.19-eng5-np-runner-container.md` still states execute-time anchor registration; R4 intentionally removes this and requires a rule update when implemented.

---

## UPDATE (2026-02-03)

### CI Security Hardening: Remove Gemini GitHub Actions

- Repo is public; removed Gemini-based GitHub Actions workflows to avoid running LLM automation against untrusted issue/comment input.
- Tracking: `TASKS/infrastructure/remove-gemini-github-actions-workflows.md`

### ML/NLP docs: canonical runbook + dataset policy

- Added canonical experiment runbook: `docs/operations/ml-nlp-runbook.md`
  - Canonical dataset (current): ELLIPSE train/test (`data/ELLIPSE_TRAIN_TEST/`)
  - IELTS dataset in repo is blocked pending source/licensing validation (no metrics/claims)
- Updated docs to stop recommending IELTS dataset for reported experiments:
  - `docs/operations/hemma-alpha-rollout-days-1-3.md` (ELLIPSE smoke example + runbook pointer)
  - `docs/decisions/0021-ml-scoring-integration-in-nlp-service.md` (training data section aligned)
  - `docs/product/epics/ml-essay-scoring-pipeline.md` (dataset policy aligned)
  - `docs/how-to/cefr-ielts-model-howto.md` (blocked notice + runbook pointer)
  - `docs/operations/ielts-task2-dataset-preparation.md` (blocked notice; historical reference)
- Verification: `pdm run validate-docs` (pass)

### Whitebox Essay Scoring: per-100-words Tier1 error densities + drop-column CLI

- Tier 1 word counting now excludes punctuation tokens, so:
  - `grammar_density`, `spelling_density`, `punctuation_density` are truly **per 100 words** (not per 100 tokens).
  - `word_count`, `avg_word_length`, `avg_sentence_length`, `ttr` now reflect word tokens (not punctuation).
  - Code: `scripts/ml_training/essay_scoring/features/tier1_error_readability.py`
  - Test: `scripts/ml_training/tests/test_tier1_word_count.py`
- Added drop-column importance CLI to support leakage-safe feature selection on handcrafted features:
  - CLI: `pdm run essay-scoring-research drop-column` (see `docs/operations/ml-nlp-runbook.md`)
  - Module: `scripts/ml_training/essay_scoring/drop_column_importance.py`
  - Outputs: `drop_column_importance.json` + `drop_column_importance.md`
- Cache correctness: bumped feature-store schema versions to force regeneration after the Tier1 change:
  - `scripts/ml_training/essay_scoring/cv_feature_store.py` schema_version: 2
  - `scripts/ml_training/essay_scoring/feature_store.py` schema_version: 4
- Refactor: extracted shared CV helpers to keep modules under size limits:
  - New: `scripts/ml_training/essay_scoring/cv_shared.py`
  - Updated: `scripts/ml_training/essay_scoring/cross_validation.py`

Verification (2026-02-03 local time):
- `source .env && pdm run pytest-root scripts/ml_training/tests -v` (22 passed)
- `source .env && pdm run format-all` (clean)
- `source .env && pdm run lint-fix --unsafe-fixes` (clean)
- `source .env && pdm run typecheck-all` (clean)

---

## UPDATE (2026-02-03)

### ENG5 NP runner + CJ assignment-owned prompt/rubric hardening (done)

- Task: `TASKS/assessment/assignment-owned-prompt-rubric-locking-context-origin.md`
- `assessment_instructions` is now the source of truth for assignment-bound runs:
  - Missing instruction row for `assignment_id` is a hard fail in CJ.
  - Runner `execute` no longer uploads student prompt when `--assignment-id` is used; prompt must
    exist in CJ (`student_prompt_storage_id`).
- Rubric A/B: runner supports `--rubric` (forwarded as `LLMConfigOverrides.judge_rubric_override`)
  only when `assessment_instructions.context_origin != canonical_national`.

### ENG5 NP runner docs alignment (runbook + architecture)

- Updated docs to reflect current EXECUTE semantics:
  - CJ admin preflight + anchor precondition (no execute-time anchor registration).
  - Assignment-owned prompt handling (runner does not upload prompts in assignment runs).
  - Execute examples now include `--assignment-id`/`--course-id` and optional `--auto-extract-eng5-db`.

### ENG5 NP runner anchor grade metadata research (R6)

- Research artefact captured at:
  - `.claude/research/data/eng5_np_2016/eng5-anchor-grade-metadata-findings-2026-02-03.md`
- Summary:
  - `assessment_instructions.grade_scale` owns grade semantics and is immutable.
  - Anchor grades validated via `common_core.grade_scales` during CJ anchor registration.
  - Anchor grades persist in `anchor_essay_references` and propagate through
    `CJAnchorMetadata` into grade projection.

---

## UPDATE (2026-02-03)

### Hemma offload: single combined feature endpoint (planned)

- Tracking task: `TASKS/assessment/hemma-offload-combined-extract-endpoint.md`
- Goal: collapse the research pipeline to a single Mac tunnel (`:19000`) by adding `POST /v1/extract`
  that returns embeddings + spaCy/TextDescriptives handcrafted features + LanguageTool-derived
  Tier1 densities in one zipped response.
- Non-negotiable: when `backend=hemma`, there are zero local fallbacks (no local spaCy, no local
  LanguageTool calls, no local torch/transformers embeddings).
- Architecture intent: single endpoint for the client, SRP modular server internals (embedding
  provider, spaCy runtime, LanguageTool client, zip bundle writer, fingerprinted metadata).

---

## UPDATE (2026-02-04)

### Essay scoring research: crash/stall diagnostics logs

- Each run dir now also contains:
  - `stderr.log` (captured stderr for the run)
  - `fault.log` (faulthandler output: segfault traces + periodic hang stack dumps)
- Implementation: `scripts/ml_training/essay_scoring/logging_utils.py` (`run_file_logger`)
- Verification:
  - `pdm run pytest-root scripts/ml_training/tests -v` (47 passed)
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`

### Essay scoring research: sensible progress logs for Hemma extraction

- Console logging defaults to INFO when stdout/stderr are redirected (nohup/CI), so `*.driver.log`
  contains useful progress output. Override with `ESSAY_SCORING_CONSOLE_LOG_LEVEL=INFO|DEBUG|...`.
- Hemma `/v1/extract` client now logs:
  - cache scan summary (ready/missing, hit/miss counts)
  - periodic progress (ready/total, fetched/missing, batches, throughput, ETA)
- Implementation:
  - `scripts/ml_training/essay_scoring/logging_utils.py` (`configure_console_logging`)
  - `scripts/ml_training/essay_scoring/offload/extract_client.py`
  - `scripts/ml_training/essay_scoring/features/pipeline.py`
- Tracking task: `TASKS/assessment/essay-scoring-sensible-progress-logs-for-feature-extraction.md`
- Verification:
  - `pdm run pytest-root scripts/ml_training/tests/test_remote_extract_client_http.py -v`
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`

### Hemma offload observability: GPU + request metrics

- Offload server now exposes:
  - `/metrics` (Prometheus text format): GPU availability + per-endpoint request counts + latency
  - `/healthz` enriched with `gpu` + `metrics` JSON snapshots
- Implementation:
  - `scripts/ml_training/essay_scoring/offload/http_app.py`
  - `scripts/ml_training/essay_scoring/offload/handlers_observability.py`
  - `scripts/ml_training/essay_scoring/offload/observability.py`
- Docs:
  - `docs/operations/hemma-server-operations-huleedu.md` (health + metrics curl examples)
  - `docs/operations/ml-nlp-runbook.md` (Hemma-side metrics pointer)
  - `docs/operations/gpu-ai-workloads-on-hemma-huleedu.md` (metrics endpoint reference)
- Verification:
  - `pdm run pytest-root scripts/ml_training/tests -v` (49 passed)
  - `pdm run validate-docs`

### Hemma offload: redeploy + live verification (single tunnel, /v1/extract)

- Hemma:
  - Repo synced to `d9d26dae` (fast-forward pull).
  - `.env` set: `OFFLOAD_LANGUAGE_TOOL_JAR_VERSION=6.6` (required for `server_fingerprint` stability).
  - Redeploy:
    - `sudo docker compose -f docker-compose.hemma.yml -f docker-compose.prod.yml -f docker-compose.hemma.research.yml --profile research-offload up -d --build essay_embed_offload`
  - Verified:
    - `curl -fsS http://127.0.0.1:9000/healthz` returns `status=ok` and `extract` config (N=64, request/response limits, `language_tool_url=http://language_tool_service:8085`, `language_tool_jar_version=6.6`).
    - `/v1/extract` smoke succeeds for `feature_set=combined` and returns zip with `meta.json`, `embeddings.npy`, `handcrafted.npy`.
- Mac:
  - Single tunnel confirmed active: `ssh hemma -L 19000:127.0.0.1:9000 -N`.
  - Live run (Hemma backend; no fallbacks):
    - `source .env && pdm run essay-scoring-research run --dataset-kind ellipse --feature-set combined --ellipse-train-path /tmp/ellipse_train_smoke.csv --ellipse-test-path /tmp/ellipse_test_smoke.csv --backend hemma --offload-service-url http://127.0.0.1:19000 --skip-shap --skip-grade-scale-report --run-name hemma_extract_smoke`
    - Output: `output/essay_scoring/20260204_005102_hemma_extract_smoke`
    - `artifacts/offload_extract_meta.json` includes `schema_version=1`, `server_fingerprint`, and `language_tool.jar_version=6.6`.
  - Warm-cache check:
    - Second run: `output/essay_scoring/20260204_005206_hemma_extract_smoke_cached`
    - Offload `/metrics` counters for `/v1/extract` did not increase across the second run (cache hit).

### Essay-scoring research runner: status.json on SIGINT/SIGTERM (2026-02-04)

- Problem: long-running runs could be terminated mid-stage and leave `status.json` stuck at `state=running`, making it indistinguishable from a hang.
- Fix:
  - Install SIGINT/SIGTERM handlers in the run logger context to best-effort mark `status.json` as `state=failed` with `failure_reason=signal` and `signal=SIGINT|SIGTERM`.
  - Ensure stage-level exception handling does not overwrite an existing signal failure marker (preserve `signal`, add `elapsed_seconds` if missing).
- Tracking task: `TASKS/assessment/essay-scoring-runner-mark-statusjson-failed-on-sigint-sigterm.md`

### Hemma offload: throughput tuning under sustained load (2026-02-04)

- Tracking task: `TASKS/assessment/optimize-hemma-offload-throughput.md`
- Live full run started (ELLIPSE, Hemma offload, `feature_set=combined`):
  - Driver log: `output/essay_scoring/ellipse_full_hemma_20260204_061926.driver.log`
- Changes focused on stable throughput without increasing client request timeouts:
  - Offload server supports multi-worker `/v1/extract` while avoiding unsafe cross-thread spaCy reuse.
  - Client fetches missing records with bounded in-flight request concurrency (progress logs include rate/ETA).

### Hemma offload: restart full run in detached screen (2026-02-04)

- Previous full run stopped logging at `2026-02-04 06:23:13 CET` without emitting an exception.
- Restarted full run in a detached `screen` session to avoid session teardown killing the process:
  - Screen session: `essay_scoring_ellipse_full_hemma_20260204_071238`
  - Driver log: `output/essay_scoring/ellipse_full_hemma_20260204_071238.driver.log`
- Run completed successfully (ELLIPSE full, Hemma backend, `feature_set=combined`):
  - output: `output/essay_scoring/20260204_061242_ellipse_full_hemma_20260204_071238/`
  - status: `status.json` `state=completed`
  - results (QWK): train `0.99295`, val `0.64241`, test `0.65552`
  - throughput: `4.04` essays/s (feature extraction total; see `artifacts/offload_metrics.json`)
  - docs updated with a concrete example entry: `docs/operations/ml-nlp-runbook.md`
  - post-run analysis report: `.claude/work/reports/essay-scoring/2026-02-04-ellipse-full-hemma-post-run-analysis.md`
  - SHAP follow-up run (reused feature store):
    - output: `output/essay_scoring/20260204_072318_ellipse_full_hemma_with_shap_20260204_082316/`
    - key artifacts:
      - `output/essay_scoring/20260204_072318_ellipse_full_hemma_with_shap_20260204_082316/shap/shap_summary.png`
      - `output/essay_scoring/20260204_072318_ellipse_full_hemma_with_shap_20260204_082316/shap/shap_summary_bar.png`
      - `output/essay_scoring/20260204_072318_ellipse_full_hemma_with_shap_20260204_082316/reports/grade_scale_report.md`
  - Full-test SHAP default (no sampling):
    - decision: `docs/decisions/0029-essay-scoring-shap-uses-full-test-set-by-default.md`
    - verified run output: `output/essay_scoring/20260204_072809_ellipse_full_hemma_with_shap_full_20260204_082806/`
    - `shap_values.npy` shape: `2430 x 793` (full ELLIPSE test split)

### Next: improve prediction power (CV-first) (2026-02-04)

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Planned slices (tasks):
  - `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`
  - `TASKS/assessment/essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse.md`
  - `TASKS/assessment/essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse.md`
  - `TASKS/assessment/essay-scoring-drop-column-importance-for-handcrafted-features-cv.md`
  - `TASKS/assessment/essay-scoring-xgboost-hyperparameter-sweep-cv-selected.md`
  - `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Feature naming clarity: Tier1 error-rate features renamed to include units (per 100 words):
  - task: `TASKS/assessment/essay-scoring-tier1-error-rates-per-100-words-naming.md`
  - decision: `docs/decisions/0030-essay-scoring-tier1-error-rate-feature-names-include-units.md`

### Decision gate: experiment optimization dependencies (2026-02-06)

- ADR (proposed): `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- New tasks (decision + options):
  - Decision gate: `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
  - Optuna (CV-selected): `TASKS/assessment/essay-scoring-optuna-hyperparameter-optimization-cv-selected.md`
  - HF fine-tuning + prompt invariance: `TASKS/assessment/essay-scoring-transformer-fine-tuning--prompt-invariance-experiments.md`
  - statsmodels + CatBoost baseline: `TASKS/assessment/essay-scoring-statsmodels-diagnostics--catboost-baseline.md`
- Research notes doc:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`
