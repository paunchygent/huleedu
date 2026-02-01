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
