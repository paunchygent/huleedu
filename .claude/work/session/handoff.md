# HANDOFF: Current Session Context

## Purpose

This document contains ONLY current/next-session work. All completed tasks, architectural decisions, and patterns are documented in:

- **README_FIRST.md** - Architectural overview, decisions, service status
- **Service READMEs** - Service-specific patterns, error handling, testing
- **.claude/rules/** - Implementation standards and requirements
- **Documentation/OPERATIONS/** - Operational runbooks (see docs/operations/cj-assessment-foundation.md for CJ/LLM defaults & metrics)
- **TASKS/** - Detailed task documentation

---

## 🎯 ACTIVE WORK (2025-11-22)

### Infrastructure & Tooling Improvements (2025-11-22)

**Completed**:
- ✅ Task filtering system: `pdm run tasks`, `tasks-now`, `tasks-next` (`scripts/task_mgmt/filter_tasks.py`)
- ✅ PDM migration: PEP 735 dependency groups (removed legacy `[tool.pdm.dev-dependencies]`)
- ✅ AGENTS.md sync hook: Auto-sync to CLAUDE.md, CODEX.md, GEMINI.md on commit
- ✅ Task creation enforcement: Added to AGENTS.md (use `pdm run new-task`)
- ✅ Linting consolidation: Ruff per-file-ignores (11 entries → 8, wildcards, section headers)
- ✅ **MyPy Configuration Consolidation** (2025-11-22) - See `TASKS/infrastructure/MYPY_CONFIGURATION_INVESTIGATION_AND_CONSOLIDATION.md`
  - Investigated apparent conflict between global `exclude` and `[[tool.mypy.overrides]]` (no actual conflict found)
  - Removed ineffective overrides (`common_core.*`, `libs.*`) from pyproject.toml for clarity
  - Fixed `libs/mypy.ini`: Added missing `mypy_path` configuration (was broken, now working)
  - Fixed PDM scripts `new-task` and `tasks`: Changed from shell to cmd array (handles quoted args)
  - Documentation: Added Rule 086 section 6 explaining exclude/override interaction
  - **Result**: All typecheck scripts now functional (typecheck-all, typecheck-libs, typecheck-common-core, typecheck-service-libs)
  - **Files changed**: pyproject.toml, libs/mypy.ini, .claude/rules/086-mypy-configuration-standards.md

**Next**:
- Consider adding type checking to CI/CD workflows (typecheck-all + typecheck-libs)

---

### New Work: CJ Prompt Cache Template Builder (Phase 1 Complete)

**Status**: Phase 1 implementation complete, all tests passing, ready for integration

**New Files Created** (+3 files, ~1,150 lines):
- `services/cj_assessment_service/models_prompt.py` (134 lines) - PromptBlock data models
- `services/cj_assessment_service/cj_core_logic/prompt_templates.py` (317 lines) - Template builder
- `services/cj_assessment_service/tests/unit/test_prompt_templates.py` (499 lines) - Rule 075 compliant tests
- `TASKS/assessment/cj-prompt-cache-template-builder.md` - Full task documentation

**Key Deliverables**:
1. ✅ **Prompt Block Models**: `PromptBlock`, `CacheableBlockTarget`, `AnthropicCacheTTL`, `PromptBlockList`
   - SHA256 content hashing for cache fragmentation tracking
   - TTL validation (1h must precede 5m per Anthropic requirements)
   - `to_api_dict_list()` for LPS integration

2. ✅ **Template Builder**: Static/dynamic separation for cache optimization
   - `build_static_blocks()`: Assignment-level cacheable content
   - `render_dynamic_essays()`: Per-comparison non-cacheable content
   - `assemble_full_prompt()`: Full prompt with TTL ordering validation
   - `build_legacy_monolithic_prompt()`: Backward compatibility

3. ✅ **Comprehensive Tests**: 40 tests (16 parametrized), 100% passing
   - Hash stability across identical contexts
   - TTL mapping (5m default, 1h extended)
   - Block ordering and structure
   - Unicode handling (Swedish characters)
   - Empty context edge cases
   - Legacy format compatibility

**Anthropic API Compliance**:
- TTL values limited to `"5m"` or `"1h"` (strings, not seconds)
- 1h TTL blocks precede 5m TTL blocks
- Graceful handling of <1024 token threshold (API handles, no client logic)
- Multi-block user messages with selective cache_control

**Quality Gates**: All passed
- ✅ typecheck-all: 0 errors
- ✅ format-all + lint-fix: 0 issues
- ✅ pytest: 40/40 tests passing
- ✅ Rule 075 compliance: 16 parametrized tests, <500 LoC

**Next Session**:
- Phase 1.3: Integrate `PromptTemplateBuilder` with `pair_generation.py`
- Phase 2: Extend LPS for multi-block cache support

**Phase 1.3 Plan (2025-11-22)**:
- Wire `generate_comparison_tasks` to `PromptTemplateBuilder.assemble_full_prompt`, attaching `prompt_blocks` while keeping the legacy monolithic prompt for backward compatibility.
- Extend `ComparisonTask` / LLM interaction path to carry `prompt_blocks` through `BatchProcessor → LLMInteractionImpl → LLMProviderServiceClient` (dual-send: `prompt_blocks` + `user_prompt`).
- Add CJ config toggle for extended TTL usage (default 5m) and enforce TTL ordering validation before dispatch.
- Update unit coverage (pair_generation + client) to assert block structure, TTL ordering, and legacy prompt parity; prep fixture for Phase 2 LPS block handling tests.
- Measure cache hit rate/cost deltas using existing LPS metrics (`llm_provider_prompt_cache_events_total`, `llm_provider_prompt_cache_tokens_total`) after integration.
- Lowered default CJ global cap `MAX_PAIRWISE_COMPARISONS` to 150 (was 350); tests that assert defaults updated; explicit overrides in tests still in place.

**Phase 1.3 progress (2025-11-22)**:
- Replaced legacy `_build_comparison_prompt` with `PromptTemplateBuilder` in `pair_generation`; `ComparisonTask` now carries `prompt_blocks` plus a prompt string rendered from those blocks.
- Added render helper in `prompt_templates` to produce the monolithic string strictly from blocks (legacy template fully removed).
- Threaded `prompt_blocks` through `LLMInteractionImpl` → `LLMProviderServiceClient`; HTTP payload now includes `prompt_blocks` (dual-send for now).
- Updated unit + integration coverage for block payloads (`test_llm_provider_service_client`, `test_llm_payload_construction_integration`); string/block parity asserted.
- Default comparison cap set to 150; related test expectations updated.

**Phase 2 (LPS block handling) progress (2025-11-22)**:
- Anthropic provider now prefers `prompt_blocks`, builds system/user block arrays with `cache_control` + TTL validation (1h before 5m), and only falls back to legacy `user_prompt` when blocks are absent.
- API/queue/orchestrator/comparison processor propagate `prompt_blocks`; callback metadata retains prompt hashes; prompt cache usage metrics are surfaced in provider response metadata.
- Added unit coverage for cache_control payload + TTL ordering (`test_anthropic_prompt_blocks.py`) and prompt_blocks acceptance on request models.
- Added cache-sandbox CLI (6-essay, two-pass, 5m TTL) using Anthropic provider to report cache read/write tokens.
- Added `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS` flag (default false) so legacy/system/tool TTLs stay 5m unless explicitly extended; Anthropic TTL selection updated to honor the flag.
- New integration suite `services/llm_provider_service/tests/integration/test_anthropic_prompt_cache_blocks.py` (8 tests) covering block preference, legacy fallback, system/tool cache_control, TTL ordering pass/fail, callback cache usage propagation, and cache-bypass metrics.
- Warm-up acceptance criteria captured: seed exactly one request per prompt hash (cacheable static blocks + tool schema; essays stay non-cacheable), avoid concurrent first-writes (ordered/jittered), require post-seed miss rate per hash ≤20% converging to near-0, enforce TTL alignment with `USE_EXTENDED_TTL_FOR_SERVICE_CONSTANTS`, and include `prompt_sha256` + provider cache usage in callbacks without overwriting caller metadata. Metrics to watch: `llm_provider_prompt_cache_events_total` hit/miss/bypass and `llm_provider_prompt_cache_tokens_total`.
- Observability: added block-level metrics (blocks/tokens/scope), scope-aware Grafana panels, hit-rate alert now assignment-scoped (<40%), and new TTL-violation alert.

---

### CJ Stability & Validation Fixes (In Progress)

**Status**: Multiple high-priority fixes in progress across CJ service

**Active Tasks**:
- **Cj Assessment Code Hardening** (`TASKS/assessment/cj-assessment-code-hardening.md`)
- **Cj Llm Serial Bundle Validation Fixes** (`TASKS/assessment/cj-llm-serial-bundle-validation-fixes.md`)
- **Cj Batch State And Completion Fixes** (`TASKS/assessment/cj-batch-state-and-completion-fixes.md`)

See individual task documents for details.

**Latest (2025-11-22)**:
- Prompt block serialization now raises in non-production (falls back only in production) to surface template bugs; all `test_llm_interaction_impl_unit.py` cases green.

---

## 📋 READY FOR IMPLEMENTATION (Next Session)

### 1. ELS Transaction Boundary Violations (High Priority)

**Task Doc**: `TASKS/infrastructure/fix-els-transaction-boundary-violations.md` (migrated 2025-11-21)
**Status**: Investigation complete ✅, Task approved ✅, Ready for implementation

**Summary**: Systematic scan revealed 17 handler files creating multiple independent transaction blocks instead of single Unit of Work pattern. Violates architectural standard for Handler-Level Unit of Work with Transactional Outbox.

**Priority Files**:
- `batch_coordination_handler_impl.py` (7 transaction blocks - highest impact)
- Result handlers (4 files, 6 blocks)
- Command handlers (3 files, 3 blocks)

**Implementation Phases**:
1. Phase 1: Refactor batch_coordination_handler_impl.py
2. Phase 2: Refactor result and command handlers
3. Phase 3: Validate session propagation in collaborators
4. Phase 4: Integration tests and atomicity verification

**Architectural Reference**: `.claude/rules/042.1-transactional-outbox-pattern.md` (Lines 64-82, 137-143)
**Pattern Example**: `services/class_management_service/implementations/batch_author_matches_handler.py:126-192`

---

### 2. LPS Rate Limiting Implementation (Awaiting Approval)

**Task Doc**: `TASKS/infrastructure/lps-rate-limiting-implementation.md` (migrated 2025-11-21)
**Status**: Investigation complete ✅, 5 PRs defined, Awaiting implementation approval

**Summary**: No rate limiting enforcement exists. Queue processor sends requests as fast as it dequeues them. Can exceed Anthropic tier 1 limits (50 req/min, 40K tokens/min) under high load.

**Implementation Plan**: 5 PRs (2-3 weeks, 1 developer)

- **PR1 (P0)**: Token Bucket Rate Limiter - Dual-bucket algorithm (requests/min + tokens/min)
- **PR2 (P1)**: Rate Limit Header Reading - Parse `x-ratelimit-*` headers, dynamic adjustment
- **PR3 (P2)**: Configurable CJ Semaphore - Override hardcoded default=3
- **PR4 (P1)**: Inter-Request Delay - Add `inter_request_delay_ms` config (default: 100ms)
- **PR5 (P2)**: Startup Validation - Fail-fast if settings exceed tier limits

**Acceptance Criteria**: No 429 errors under normal load, configurable limits, graceful degradation, full test coverage

---

### 3. Prompt Amendment API (Uncommitted - Lint Blocking)

**Status**: Implementation complete, tests passing, lint errors blocking commit

**Completed**:
- ✅ Shared contract `BatchPromptAmendmentRequest` (common_core)
- ✅ BOS PATCH `/v1/batches/<batch_id>/prompt` with ownership + status guard
- ✅ API Gateway proxy PATCH `/v1/batches/{batch_id}/prompt`
- ✅ Tests passing
- ✅ Format passing

**Remaining**: Fix pre-existing F821 lint errors (`logger` undefined in multiple `*health_routes.py` files)

---

## ✅ RECENTLY COMPLETED (Reference Only)

- **2025-11-21 Task Migration Complete** - 36 files migrated from `.claude/work/tasks/` to `TASKS/` with proper frontmatter and domain organization. See `MIGRATION_SUMMARY_2025-11-21.md`
- **2025-11-21 CJ Completion Idempotency** - Guard + unique constraint migration applied, 6/6 tests passing. See `TASKS/assessment/cj-completion-event-idempotency.md`
- **2025-11-21 Database Enum Audit** - 9 services checked, 2 fixed (ELS, BOS), prevention implemented (`pdm run validate-enum-drift`). See `.claude/research/database-enum-audit-2025-11-21.md`
- **2025-11-21 CJ BatchMonitor Embed** - Monitor operational in app.py, stalled batch recovered, infra healthy
- **2025-11-21 PDM Skill Created** - Migration skill in `.claude/skills/pdm/` with Context7 integration
- **2025-11-21 ELS Slot Assignment Fix** - Lock-aware retries for Option B allocator, contention test passing
- **2025-11-20 Prompt Propagation Fix** - BOS → BCS batch_metadata propagation, committed
- **2025-11-19 Logging Infrastructure** - File persistence + Docker rotation (5 PRs). See `TASKS/infrastructure/logging-file-persistence-docker-rotation.md`
- **2025-11-19 Loki Cardinality Fix** - 7.5M → 25 streams (300,000x improvement), JSON parsing operational
- **2025-11-19 CJ Batch State Fixes** - Total budget tracking, completion denominator, position randomization (7 PRs)
- **2025-11-18 LLM Batch Strategy** - Serial bundle infrastructure complete (Phases 1-3). See `TASKS/integrations/llm-batch-strategy-checklist.md`
- **2025-11-17 HTTP API Contracts Migration** - CJ ↔ LPS cross-service imports eliminated (8 commits)

---

## 🎯 CJ E2E Test Latency Finding (2025-11-21)

**Context**: Not a bug, architectural observation from test run

**Observation**: Functional test `test_complete_cj_assessment_processing_pipeline` took ~3m56s despite 4 essays and 6 comparisons.

**Root Cause**: Completion gate uses percent-of-budget (95% of `total_budget=350`). For n=4 (nC2=6), completion_rate=6/350 (~1.7%) never satisfies gate. Batch stayed in WAITING_CALLBACKS until BatchMonitor sweep (5m interval) forced completion.

**Note**: Callbacks arrived within ~12s, scoring ran immediately once monitor triggered. No LLM/network slowness.

**Resolution**: Stability-first completion now implemented (addresses this issue). Completion denominator capped to nC2.

---

## 📚 INVESTIGATION RUNBOOKS (Appendix)

### Database Enum Drift Detection

**Context**: Two critical enum mismatches discovered 2025-11-21 (ELS `essay_status_enum`, BOS `batch_status_enum`) blocking 100% of pipeline flows.

**Status**: ✅ Audit complete, prevention implemented, no additional mismatches found

**Prevention Implemented**:
- CI/local check: `pdm run validate-enum-drift` (uses dev DBs)
- Startup validation: ELS and BOS fail-fast on enum mismatch (non-prod environments)
- Rule update: `.claude/rules/085-database-migration-standards.md` mandates enum drift guard

**Root Cause**: Bulk addition of expanded enums landed 2025-07-17 with no migrations. Divergence persisted until 2025-11-21 fixes.

**Services Audited**: 9 services with databases - no new mismatches found
- ✅ CJ, RAS, Email, Entitlements: enums match DB
- ✅ Spellchecker, File, NLP, Class Management: no status enums or non-status only

**Research Doc**: `.claude/research/database-enum-audit-2025-11-21.md`

---

### CJ Completion Event Debugging

**Validation Script**: `scripts/validate_duplicate_completion_events.sh`

**Purpose**: Detect duplicate `cj_assessment.completed` events in outbox

**Usage**:
```bash
./scripts/validate_duplicate_completion_events.sh
```

**What it checks**:
- Duplicate outbox entries for same `aggregate_id`
- Multiple completion events within short time windows (<5 min)
- Summary statistics: `total_events / unique_batches` ratio

**Research**: `.claude/research/cj-completion-event-validation-results-2025-11-21.md`

---

## 📝 NOTES FOR NEXT SESSION

1. **Uncommitted work is significant**: ~1570 additions across 36 files. Review carefully before committing.
2. **CJ completion logic substantially refactored**: Stability-first approach, major changes to workflow_continuation.py
3. **All quality gates passing**: typecheck ✅, format ✅, lint ✅ (except pre-existing F821s)
4. **Docker containers healthy**: No deployment issues, CJ service running 2 hours with embedded monitor
5. **ELS transaction boundary violations are next logical priority**: Architectural compliance, high impact on data consistency

---

## 🔍 Archived Work

**Location**: `.claude/archive/handoff-history/`

For reference, previous versions and completed work from 2025-11-18 to 2025-11-21 are preserved in:
- `handoff-2025-11-21-pre-cleanup.md` (full backup before this cleanup)
- `2025-11-18-to-2025-11-21-completed-work.md` (archived completed sections)
