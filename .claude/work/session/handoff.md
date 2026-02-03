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
