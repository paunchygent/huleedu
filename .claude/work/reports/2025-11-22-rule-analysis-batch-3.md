# Rule Analysis - Batch 3 (070-095)

**Analysis Date**: 2025-11-22
**Rules Analyzed**: 24 files
**Purpose**: Distill testing, observability, and tooling patterns for Pydantic schema

---

## Executive Summary

Batch 3 represents the **quality assurance and development infrastructure** layer of the HuleEdu rulebook. This batch differs fundamentally from batches 1-2:

- **Batch 1**: Service specifications (64.5% service-spec rules)
- **Batch 2**: Implementation patterns (43.5% implementation rules, 82.6% with code)
- **Batch 3**: Testing, observability, and tooling infrastructure (8 tooling rules, 5 observability sub-rules, 4 testing rules)

**Key Characteristics**:
- **Index Pattern Confirmed**: Rule 071 is an index (like 000) with 5 children (071.1-071.5)
- **Observability Hierarchy**: Technology-specific sub-rules (Prometheus, Jaeger, Loki, Grafana)
- **Tooling Concentration**: 8 consecutive rules (080-087) covering dev tooling ecosystem
- **Testing Methodologies**: 4 rules with parent-child relationships (070, 070.1, 075, 075.1)
- **Anti-Pattern Rule**: 077 documents negative guidance (what NOT to do)
- **CLI Documentation**: Heavy focus on command-line usage patterns (PDM, Ruff, Docker, Alembic)

**Frontmatter Compliance**: 91.7% (22/24 rules have frontmatter)
- Missing: 071.5, 075.1 (both sub-rules, pattern inconsistency)

**Code Examples**: 66.7% (16/24 rules contain code blocks)
- Lower than batch 2 (82.6%) due to index/reference rules (071, 072, 080)

---

## Rule Inventory

| ID | Purpose | Type | Scope | Enforcement | Artifacts | Has Examples | Parent |
|----|---------|------|-------|-------------|-----------|--------------|--------|
| 070 | Core testing standards and test runner patterns | testing | all | critical | tests, code | yes | - |
| 070.1 | Performance testing patterns with testcontainers | testing | backend | high | tests, metrics | yes | 070 |
| 071 | Index of observability patterns and sub-rules | observability | all | high | documentation | no | - |
| 071.1 | Core observability philosophy and correlation patterns | observability | all | critical | logs, metrics, traces | yes | 071 |
| 071.2 | Prometheus metrics patterns and service integration | observability | all | high | metrics | yes | 071 |
| 071.3 | Distributed tracing with Jaeger and OpenTelemetry | observability | all | high | traces | yes | 071 |
| 071.4 | Grafana dashboards and Loki log aggregation | observability | all | high | logs | yes | 071 |
| 071.5 | LLM debugging patterns using observability stack | observability | all | medium | logs, traces | yes | 071 |
| 072 | Grafana dashboard standards and operational patterns | observability | infrastructure | medium | documentation | yes | - |
| 073 | Health endpoint implementation for all service types | implementation | backend | critical | code | yes | - |
| 075 | Systematic test creation methodology (ULTRATHINK) | testing | all | critical | tests | yes | - |
| 075.1 | Parallel test creation with batch execution pattern | testing | all | high | tests | no | 075 |
| 077 | Critical anti-patterns that cause production failures | standards | all | critical | documentation | yes | - |
| 080 | Repository workflow with PDM and Git patterns | tooling | all | high | documentation | no | - |
| 081 | PDM dependency management standards | tooling | all | critical | config | yes | - |
| 082 | Ruff linting standards and VS Code integration | tooling | all | high | config | yes | - |
| 083 | PDM standards 2025 with modern dependency patterns | tooling | all | critical | config | yes | - |
| 084 | Docker containerization standards and import patterns | tooling | infrastructure | critical | infrastructure | yes | - |
| 084.1 | Docker Compose v2 command reference | tooling | infrastructure | high | documentation | yes | 084 |
| 085 | Database migration standards with Alembic | data | backend | critical | infrastructure | yes | - |
| 086 | MyPy configuration for monorepo type checking | tooling | all | high | config | yes | - |
| 087 | Docker development patterns and multi-stage builds | tooling | infrastructure | high | infrastructure | yes | - |
| 090 | Documentation standards and taxonomy | documentation | all | high | documentation | no | - |
| 095 | Textual TUI patterns correcting AI training data | implementation | all | low | code | yes | - |

---

## Detailed Distillations

### 070-testing-and-quality-assurance

**File**: `.claude/rules/070-testing-and-quality-assurance.md`
**Purpose**: Core testing standards including runner patterns and DI testing
**Type**: testing
**Scope**: all
**Enforcement**: critical
**Dependencies**: None explicit
**Artifacts**: tests, code
**Maintenance**: evolving
**Parent Rule**: None
**Child Rules**: 070.1
**Tech Stack**: pytest, Dishka, testcontainers, Prometheus
**Has Code Examples**: yes
**CLI Commands**: `pdm run pytest-root`, `pyp`, `pdmr pytest-root`
**Config Files**: pyproject.toml (MyPy section)

**Key Characteristics**:
- Test pyramid: Unit > Contract > Integration > E2E
- **CRITICAL**: `pdm run pytest-root` from repo root for path resolution
- DI/Protocol testing patterns with Dishka
- Database URL must be UPPERCASE (`DATABASE_URL` not `database_url`)
- Prometheus registry cleanup required in tests
- Timeout standard: ≤60s individual, 30s default for event-driven
- Forbids: `try/except pass`, wrong abstraction mocking, simplifying tests

**Frontmatter Implications**:
- `cli_commands` field needed for test runner variations
- `common_failures` enum (NoFactoryError, Prometheus conflicts)
- `anti_patterns` field for forbidden practices

---

### 070.1-performance-testing-methodology

**File**: `.claude/rules/070.1-performance-testing-methodology.md`
**Purpose**: Performance testing patterns and infrastructure testing guidelines
**Type**: testing
**Scope**: backend
**Enforcement**: high
**Dependencies**: 070
**Artifacts**: tests, metrics
**Maintenance**: evolving
**Parent Rule**: 070
**Child Rules**: None
**Tech Stack**: pytest, testcontainers, Redis, Kafka, PostgreSQL
**Has Code Examples**: yes
**CLI Commands**: None specific
**Config Files**: None

**Key Characteristics**:
- Testing strategy matrix: Unit/Integration/Performance/E2E
- Real infrastructure (testcontainers) for performance tests
- Mock LLM providers with `performance_mode=True`
- Performance targets: Redis <0.1s, Queue <0.2s, E2E P95 <5s
- Bulk operation testing patterns (concurrent, constraints, memory)
- Outbox pattern testing (unit, integration, business logic)
- DI container cleanup patterns (critical for resource management)

**Frontmatter Implications**:
- `performance_targets` field for benchmark thresholds
- `test_categories` enum (load, stress, endurance, bulk)
- `infrastructure_components` list (Redis, Kafka, PostgreSQL)

---

### 071-observability-index

**File**: `.claude/rules/071-observability-index.md`
**Purpose**: Index of observability patterns and sub-rules
**Type**: observability
**Scope**: all
**Enforcement**: high
**Dependencies**: None (is index)
**Artifacts**: documentation
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: 071.1, 071.2, 071.3, 071.4, 071.5, 072
**Tech Stack**: Prometheus, Jaeger, Loki, Grafana
**Has Code Examples**: no
**CLI Commands**: `pdm run obs-up`, `pdm run obs-down`, `pdm run dc-ps`
**Config Files**: observability/docker-compose.observability.yml

**Key Characteristics**:
- **IS INDEX**: Similar to 000-rule-index.md pattern
- Lists 5 child rules (071.1-071.5) plus related 072
- Quick reference URLs: Grafana (3000), Prometheus (9091), Jaeger (16686), Loki (3100)
- Internal container URLs for Grafana datasources
- Infrastructure monitoring endpoints (Kafka, PostgreSQL, Redis, Node)
- Import order guidance (core → specific technology → apply)

**Frontmatter Implications**:
- `is_index: true` field required
- `child_rules: [071.1, 071.2, 071.3, 071.4, 071.5]`
- `stack_urls` object for service endpoints
- `cli_commands` for observability management

---

### 071.1-observability-core-patterns

**File**: `.claude/rules/071.1-observability-core-patterns.md`
**Purpose**: Core observability philosophy and principles for HuleEdu services
**Type**: observability
**Scope**: all
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: logs, metrics, traces
**Maintenance**: stable
**Parent Rule**: 071
**Child Rules**: None
**Tech Stack**: structlog, Prometheus, OpenTelemetry
**Has Code Examples**: yes
**CLI Commands**: None
**Config Files**: None

**Key Characteristics**:
- Philosophy: Business insights first, correlation over collection
- Standard patterns: service_name, service_version, environment, correlation_id
- Every service MUST: `/metrics`, `/healthz`, structured JSON logs, correlation_id
- Observability stack URLs (external + internal container access)
- Naming conventions: service-specific, business metrics, infrastructure
- Dashboard naming: System overview, service-specific, troubleshooting

**Frontmatter Implications**:
- `philosophy` field for observability principles
- `required_endpoints` list (/metrics, /healthz)
- `naming_conventions` object (metrics, dashboards)

---

### 071.2-prometheus-metrics-patterns

**File**: `.claude/rules/071.2-prometheus-metrics-patterns.md`
**Purpose**: Prometheus metrics patterns and implementation guidelines
**Type**: observability
**Scope**: all
**Enforcement**: high
**Dependencies**: 071.1
**Artifacts**: metrics
**Maintenance**: evolving
**Parent Rule**: 071
**Child Rules**: None
**Tech Stack**: Prometheus, Quart, FastAPI, Dishka
**Has Code Examples**: yes
**CLI Commands**: `curl http://localhost:9091/api/v1/query?query=...`
**Config Files**: None

**Key Characteristics**:
- Metric types: Counter (increases only), Histogram (distributions), Gauge (up/down)
- Service integration patterns: Quart (middleware), FastAPI (DI)
- Label strategy: Required (service, environment, version), Forbidden (user IDs, correlation IDs)
- Circuit breaker metrics via `StandardCircuitBreakerMetrics`
- Message processing metrics (header utilization, idempotency)
- Testing patterns: direct access, Prometheus queries

**Frontmatter Implications**:
- `metric_types` enum (counter, histogram, gauge)
- `label_strategy` object (required, forbidden)
- `integration_patterns` by framework (Quart, FastAPI)

---

### 071.3-jaeger-tracing-patterns

**File**: `.claude/rules/071.3-jaeger-tracing-patterns.md`
**Purpose**: Distributed tracing patterns with Jaeger and OpenTelemetry
**Type**: observability
**Scope**: all
**Enforcement**: high
**Dependencies**: 071.1
**Artifacts**: traces
**Maintenance**: stable
**Parent Rule**: 071
**Child Rules**: None
**Tech Stack**: Jaeger, OpenTelemetry, Quart, FastAPI
**Has Code Examples**: yes
**CLI Commands**: None
**Config Files**: None (environment variables)

**Key Characteristics**:
- Framework-specific imports (Quart vs FastAPI middleware)
- Initialization pattern: `init_tracing()` + `setup_tracing_middleware()`
- Environment config: OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME
- Trace propagation: HTTP (automatic via middleware), Events (inject/extract)
- Custom instrumentation: `trace_operation()` context manager
- Forbidden: PII in span attributes (user_email, user_name, content)
- Debugging workflow: X-Trace-ID → Jaeger UI → analyze dependencies

**Frontmatter Implications**:
- `propagation_patterns` enum (http, events)
- `forbidden_attributes` list (PII fields)
- `environment_variables` list (OTEL_*)

---

### 071.4-grafana-loki-patterns

**File**: `.claude/rules/071.4-grafana-loki-patterns.md`
**Purpose**: Grafana dashboards and Loki log aggregation patterns
**Type**: observability
**Scope**: all
**Enforcement**: high
**Dependencies**: 071.1
**Artifacts**: logs
**Maintenance**: evolving
**Parent Rule**: 071
**Child Rules**: None
**Tech Stack**: Grafana, Loki, Promtail, logcli
**Has Code Examples**: yes (LogQL queries)
**CLI Commands**: `logcli query`, `logcli --from --to --limit --output`
**Config Files**: observability/grafana/dashboards/, observability/prometheus/rules/

**Key Characteristics**:
- Dashboard structure: Service health, error rate, P95, request rate
- Time ranges: 1h/6h/24h/7d, refresh 30s (operational) / 5m (analytics)
- **CRITICAL LogQL patterns**: `{service="..."} | json | correlation_id="..."`
- Label strategy: LOW cardinality only (service, level) - indexed
- High cardinality in JSON body (correlation_id, logger_name, batch_id)
- **Rule**: >100 unique values/day MUST stay in JSON, not labels
- Programmatic access: logcli for LLM agents, export to JSONL, jq filtering
- Dashboard categories: System overview, service deep dive, troubleshooting

**Frontmatter Implications**:
- `label_strategy` object (indexed_labels, json_fields)
- `cardinality_rule` validation (>100 unique → JSON body)
- `programmatic_access` patterns (logcli, export, LLM integration)

---

### 071.5-llm-debugging-with-observability

**File**: `.claude/rules/071.5-llm-debugging-with-observability.md`
**Purpose**: LLM debugging patterns for HuleEdu observability
**Type**: observability
**Scope**: all
**Enforcement**: medium
**Dependencies**: 071.1, 071.3, 071.4
**Artifacts**: logs, traces
**Maintenance**: evolving
**Parent Rule**: 071
**Child Rules**: None
**Tech Stack**: Loki, Jaeger, logcli, jq
**Has Code Examples**: yes (bash scripts)
**CLI Commands**: `logcli query`, validation scripts
**Config Files**: None

**Key Characteristics**:
- **NO FRONTMATTER** (inconsistency vs other 071.X rules)
- Core pattern: Label-first filtering `{service="..."} | json | field="..."`
- Anti-patterns: High-cardinality label queries, multi-service docker logs, assuming trace context
- Debugging workflows: Trace request across services, export logs for analysis, correlation priority
- Field reference table: service/level (labels), correlation_id/trace_id/batch_id (JSON)
- Common scenarios: Batch stuck, high API errors, latency spike
- Performance optimization: Filter labels first (uses index), absolute time ranges, bound result sets
- Loki → Jaeger correlation workflow
- Validation script usage: `./scripts/validate_otel_trace_context.sh`

**Frontmatter Implications**:
- **MISSING FRONTMATTER** - should be added for consistency
- `debugging_workflows` enum (trace_request, export_logs, correlation)
- `anti_patterns` list (documented in detail)
- `field_reference` table (cardinality, type, query pattern)

---

### 072-grafana-playbook-rules

**File**: `.claude/rules/072-grafana-playbook-rules.md`
**Purpose**: Grafana dashboard standards and operational patterns
**Type**: observability
**Scope**: infrastructure
**Enforcement**: medium
**Dependencies**: 071
**Artifacts**: documentation
**Maintenance**: stable
**Parent Rule**: None (related to 071 but not child)
**Child Rules**: None
**Tech Stack**: Grafana, Prometheus, Loki
**Has Code Examples**: yes (JSON, PromQL)
**CLI Commands**: None
**Config Files**: observability/grafana/dashboards/

**Key Characteristics**:
- Dashboard naming: `HuleEdu - <Category> - <Specific Purpose>`
- Panel organization: Top (health), Middle (metrics), Bottom (logs/troubleshooting)
- Limit: Max 12 panels per dashboard
- Essential templates: System Health Overview, Service Deep Dive
- Query standards: Standard metrics library (request rate, error rate, P95)
- Query optimization: Use recording rules, avoid regex, limit time ranges
- Required variables: service, instance, range
- Alert integration: Alert panels, annotation integration
- Maintenance: Review monthly (operational), quarterly (analysis)
- Version control: Export JSON to observability/dashboards/
- Color standards: Green (0-80%), Yellow (80-90%), Red (>90%)
- Panel sizing: Single Stat (3x2), Time Series (6x4), Table (12x4), Logs (12x6)

**Frontmatter Implications**:
- `dashboard_templates` list (system_health, service_deep_dive, troubleshooting)
- `query_library` object (standard PromQL patterns)
- `color_standards` thresholds
- `maintenance_frequency` enum

---

### 073-health-endpoint-implementation

**File**: `.claude/rules/073-health-endpoint-implementation.md`
**Purpose**: Health endpoint implementation patterns for all service types
**Type**: implementation
**Scope**: backend
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: code
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Quart, FastAPI, PostgreSQL, Prometheus
**Has Code Examples**: yes
**CLI Commands**: None
**Config Files**: None

**Key Characteristics**:
- All services MUST: `/healthz`, `/metrics`
- PostgreSQL services MUST ALSO: `/healthz/database`, `/healthz/database/summary`
- Quart pattern: Blueprint with DatabaseHealthChecker
- FastAPI pattern: APIRouter
- Non-database services: Simple status check
- Metrics endpoint: Prometheus format via `generate_latest()`
- App setup: Store engine on `app.database_engine` for health checks
- Error handling: Never crash service, return 503 on failure
- Status codes: 200 (healthy), 503 (unhealthy)
- Response format: Consistent JSON across all services

**Frontmatter Implications**:
- `required_endpoints` by service type (all, postgresql)
- `status_codes` enum (200, 503)
- `framework_patterns` object (Quart, FastAPI)

---

### 075-test-creation-methodology

**File**: `.claude/rules/075-test-creation-methodology.md`
**Purpose**: Systematic test creation methodology following battle-tested patterns
**Type**: testing
**Scope**: all
**Enforcement**: critical
**Dependencies**: 000-rule-index.md, service-specific rules (020.X)
**Artifacts**: tests
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: 075.1
**Tech Stack**: pytest, Dishka, testcontainers
**Has Code Examples**: yes
**CLI Commands**: `pdm run typecheck-all`, `pdm run pytest-root`
**Config Files**: None

**Key Characteristics**:
- **ULTRATHINK protocol**: 6-step pre-implementation phase
- Read 8 mandatory architectural rules + service-specific rules first
- Study battle-tested pattern sources by service type
- File size: <500 LoC hard limit
- Test class organization: `class TestFunctionName` with clear docstrings
- Parametrized testing preferred: `@pytest.mark.parametrize`
- Behavioral testing: Actual behavior/side effects, method call assertions
- Domain-specific context: Swedish characters for NLP, currency for financial
- Mandatory validation: typecheck-all → pytest-root → 100% pass → root cause fixes
- Progressive enhancement: Start simple, build complexity, complete one file first
- DI testing: Protocol-based mocking, Dishka container overrides
- JWT testing: Use shared helpers from `huleedu_service_libs.testing.jwt_helpers`
- Anti-patterns: Large monolithic files, testing implementation details, skipping validation
- Service type adaptation: HTTP, Worker, Utility, Repository patterns

**Frontmatter Implications**:
- `pre_implementation_steps` list (6-step ULTRATHINK)
- `battle_tested_sources` by service type
- `validation_sequence` steps
- `service_type_patterns` object (HTTP, Worker, Utility, Repository)

---

### 075.1-parallel-test-creation-methodology

**File**: `.claude/rules/075.1-parallel-test-creation-methodology.md`
**Purpose**: Parallel test creation with batch execution pattern
**Type**: testing
**Scope**: all
**Enforcement**: high
**Dependencies**: 075
**Artifacts**: tests
**Maintenance**: evolving
**Parent Rule**: 075
**Child Rules**: None
**Tech Stack**: pytest, lead-dev-code-reviewer agent
**Has Code Examples**: no (procedural steps only)
**CLI Commands**: `grep -r "@patch|mock.patch"`, `pdm run pytest-root`, `pdm run typecheck-all`
**Config Files**: None

**Key Characteristics**:
- **NO FRONTMATTER** (inconsistency vs parent 075)
- Batch size: 3 test files per execution cycle
- Agent launch: Single tool call with 3 parallel test-engineer agents
- Target scope: Related components (handlers, repositories, schemas)
- **MANDATORY post-batch architect review** with lead-dev-code-reviewer
- Quality gate sequence: architect review → DI compliance → test execution → type safety
- Implementation bug protocol: Detect via tests, fix implementation first, re-validate
- Success criteria: 100% pass rate, zero DI violations, Rule 075 compliance

**Frontmatter Implications**:
- **MISSING FRONTMATTER** - should be added for consistency
- `batch_execution` object (size: 3, agent_type, target_scope)
- `quality_gates` sequence
- `agent_coordination` patterns

---

### 077-service-anti-patterns

**File**: `.claude/rules/077-service-anti-patterns.md`
**Purpose**: Critical anti-patterns that cause production failures and corrections
**Type**: standards
**Scope**: all
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: documentation
**Maintenance**: evolving
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Redis, Kafka, SQLAlchemy, Dishka, Prometheus
**Has Code Examples**: yes (wrong vs right patterns)
**CLI Commands**: None
**Config Files**: None

**Key Characteristics**:
- **NEGATIVE GUIDANCE**: Documents what NOT to do (unique among rules)
- Infrastructure client anti-patterns: Direct imports, missing lifecycle management
- Health endpoint anti-patterns: Inconsistent endpoints, hardcoded values
- Event processing anti-patterns: Missing idempotency, missing trace context
- Database anti-patterns: Shared engine instances (MissingGreenlet), direct session usage
- DI anti-patterns: Factory functions without scoping, missing protocol contracts
- Configuration anti-patterns: Hardcoded settings, missing environment prefixes
- Testing anti-patterns: Testing concrete implementations, missing Prometheus cleanup
- Critical production issues: MissingGreenlet, DetachedInstanceError, memory leaks, duplicate events

**Frontmatter Implications**:
- `is_negative_guidance: true` field
- `anti_pattern_categories` enum (infrastructure, health, events, database, DI, config, testing)
- `production_issues` list with root causes

---

### 080-repository-workflow-and-tooling

**File**: `.claude/rules/080-repository-workflow-and-tooling.md`
**Purpose**: Read before any interaction with pyproject.toml or git commands
**Type**: tooling
**Scope**: all
**Enforcement**: high
**Dependencies**: None
**Artifacts**: documentation
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: PDM, Git, Docker
**Has Code Examples**: no (command reference only)
**CLI Commands**: `pdm add/update/remove`, `pdm run db-reset`, dev-workflow.sh
**Config Files**: pyproject.toml, docker-compose.yml, docker-compose.dev.yml

**Key Characteristics**:
- PDM as sole dependency manager: Use `pdm add/update/remove` to maintain lock
- Standard tasks defined as PDM scripts in pyproject.toml
- Branching strategy: Gitflow or Trunk-Based Development
- Commit messages: Conventional Commits recommended
- Code reviews mandatory for all changes
- Database reset: `pdm run db-reset` (destructive, wipes all dev databases)
- Monorepo structure: `common/` (shared), `services/` (service-specific)
- Docker workflow: dev vs production builds, development commands
- Performance: Incremental builds 4-6s, clean builds 5-7min, hot-reload instant
- Build optimization: Dependencies before code, multi-stage, dynamic lockfiles

**Frontmatter Implications**:
- `workflow_tools` list (PDM, Git, Docker)
- `cli_commands` by category (dependency, database, docker)
- `performance_targets` object

---

### 081-pdm-dependency-management

**File**: `.claude/rules/081-pdm-dependency-management.md`
**Purpose**: MUST READ whenever working on pdm resolution, versioning, and .toml files
**Type**: tooling
**Scope**: all
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: config
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: PDM
**Has Code Examples**: yes (TOML)
**CLI Commands**: `pdm lock --check`, `pdm update`, `pdm install`
**Config Files**: pyproject.toml, pdm.lock

**Key Characteristics**:
- Minimal configuration: `distribution = false` only
- **FORBIDDEN**: Custom resolution settings (use PDM defaults)
- Dependency version strategy: Let PDM handle versions (unconstrained specs)
- Version constraints only when necessary (breaking changes, incompatibilities, security)
- Validation commands: `pdm lock --check`, `pdm update`, `pdm install`
- Standard scripts: format-all, lint-all, lint-fix, typecheck-all, test-all

**Frontmatter Implications**:
- `minimal_config` requirements
- `forbidden_settings` list
- `validation_commands` sequence

---

### 082-ruff-linting-standards

**File**: `.claude/rules/082-ruff-linting-standards.md`
**Purpose**: Read whenever discussing linter settings
**Type**: tooling
**Scope**: all
**Enforcement**: high
**Dependencies**: None
**Artifacts**: config
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Ruff
**Has Code Examples**: yes (TOML, JSON)
**CLI Commands**: None
**Config Files**: pyproject.toml, .vscode/settings.json

**Key Characteristics**:
- Core settings: line-length 100, target py311, exclude patterns
- Lint rules: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort)
- Ignore: E203 (conflicts with black)
- Format: double quotes, space indent
- Per-file ignores: E402 for service entry points (after load_dotenv)
- VS Code integration: Modern settings for 2025 (ruff.nativeServer: auto)
- **FORBIDDEN**: Deprecated VS Code settings (ruff.format.args, ruff.lint.args)

**Frontmatter Implications**:
- `core_settings` object (line-length, target-version, exclude)
- `lint_rules` selected/ignored
- `vs_code_integration` modern/deprecated settings

---

### 083-pdm-standards-2025

**File**: `.claude/rules/083-pdm-standards-2025.md`
**Purpose**: CRITICAL: Must be applied when editing or discussing pdm and pyproject.toml
**Type**: tooling
**Scope**: all
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: config
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: PDM, Ruff, MyPy
**Has Code Examples**: yes (TOML, bash)
**CLI Commands**: `pdm lock --check`, `pdm update`, `pdm install`, `pdm run typecheck-all`
**Config Files**: pyproject.toml

**Key Characteristics**:
- **OVERRIDES conflicting training data** (explicit in header)
- Tool version minimums: PDM ≥2.22.0, Ruff ≥0.11.11, MyPy ≥1.15.0
- Standard `[tool.pdm]`: distribution=false, package-type=application
- **MANDATORY resolution strategy**: inherit_metadata, direct_minimal_versions
- Dependency groups: dev, test, lint, monorepo-tools
- Standard scripts: format-all, lint-all, lint-fix, typecheck-all, test-all
- **MyPy execution from root only**: Absolute imports, cross-service validation
- Validation: `pdm lock --check`, `pdm update`, `pdm install`
- MyPy missing stubs: Add to external libraries section with `ignore_missing_imports`
- **FORBIDDEN**: Creating py.typed markers, deprecated Ruff VS Code settings

**Frontmatter Implications**:
- `minimum_versions` object (PDM, Ruff, MyPy)
- `mandatory_config` sections
- `validation_sequence` steps

---

### 084-docker-containerization-standards

**File**: `.claude/rules/084-docker-containerization-standards.md`
**Purpose**: Rules for correct docker containerization patterns
**Type**: tooling
**Scope**: infrastructure
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: infrastructure
**Maintenance**: evolving
**Parent Rule**: None
**Child Rules**: 084.1
**Tech Stack**: Docker, PDM, Python
**Has Code Examples**: yes (bash, Dockerfile snippets)
**CLI Commands**: docker exec, curl health endpoints, dev-build, dev-start
**Config Files**: Dockerfile.deps, Dockerfile, docker-compose.yml

**Key Characteristics**:
- **CRITICAL**: `PYTHONPATH=/app` in Dockerfiles for module resolution
- Import pattern flexibility: Runtime (Docker) can use mixed, Tests require absolute
- Service configuration priority: Check PYTHONPATH, health ports, env vars, DI, framework config
- Shared dependency image: Dockerfile.deps with hash-based rebuilding
- Service Dockerfiles: Generated via update_service_dockerfiles.py
- **FORBIDDEN**: Per-service `pdm install`, recreating appuser, legacy **pypackages** mounts
- Dual-mode services: Expose both HTTP and worker entry points
- Environment config: Port mapping, required env vars, prefix consistency
- Development vs container consistency: Both pdm run and python app.py must work
- Build commands: dev-build (cached), dev-build-clean (force), dev-start, dev-recreate
- Dependency order: Infrastructure → Topic setup → Core → Dependent services
- Validation: Health endpoints, metrics, container status, DI resolution
- Troubleshooting: Configuration first (PYTHONPATH, ports, DI), then imports

**Frontmatter Implications**:
- `critical_requirements` list (PYTHONPATH, Dockerfile.deps pattern)
- `import_contexts` object (runtime, test)
- `build_commands` reference
- `troubleshooting_priority` sequence

---

### 084.1-docker-compose-v2-command-reference

**File**: `.claude/rules/084.1-docker-compose-v2-command-reference.md`
**Purpose**: ALWAYS activate when using Docker or Docker commands. This is the correct v2 syntax
**Type**: tooling
**Scope**: infrastructure
**Enforcement**: high
**Dependencies**: 084
**Artifacts**: documentation
**Maintenance**: stable
**Parent Rule**: 084
**Child Rules**: None
**Tech Stack**: Docker Compose v2
**Has Code Examples**: yes (bash, Python, YAML)
**CLI Commands**: All `docker compose` (space) commands
**Config Files**: None

**Key Characteristics**:
- **Key change**: `docker-compose` (hyphen) → `docker compose` (space)
- Command transformations: up, down, ps, build, logs, exec
- GitHub Actions: No setup required (built into Ubuntu runners)
- Python subprocess: `["docker", "compose", "up", "-d"]` not `["docker-compose", ...]`
- Health check: `docker compose version` not `command -v docker-compose`

**Frontmatter Implications**:
- `v1_to_v2_mappings` object
- `github_actions_note` (no setup required)

---

### 085-database-migration-standards

**File**: `.claude/rules/085-database-migration-standards.md`
**Purpose**: Database migration standards for HuleEdu microservices
**Type**: data
**Scope**: backend
**Enforcement**: critical
**Dependencies**: None
**Artifacts**: infrastructure
**Maintenance**: evolving
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Alembic, PostgreSQL, Docker
**Has Code Examples**: yes (bash, SQL, Python)
**CLI Commands**: `../../.venv/bin/alembic upgrade/current/stamp/revision`, `pdm run db-reset`
**Config Files**: alembic.ini, env.py, config.py

**Key Characteristics**:
- **MANDATORY pre-migration analysis**: Check state with `alembic current` and `\dt`
- State scenarios: Schema exists (stamp then upgrade) vs clean state (direct upgrade)
- Migration commands: Use monorepo venv directly from service directory
- Recommended dev reset: `pdm run db-reset` (destructive, wipes all dev databases)
- **MANDATORY automated safety checks**: Service-level smoke test with ephemeral PostgreSQL
- Enum drift guard: Create matching migrations in affected services, CI/pre-commit checks
- Enum creation policy: Prefer SQLAlchemy-managed enums, use `create_type=False` if manual
- **FORBIDDEN**: PDM service-specific commands, service-specific venv, PYTHONPATH hacks, manual SQL
- Post-migration verification: `alembic current`, database access patterns
- Database name mapping table (9 services with ports)
- **MANDATORY secure config pattern**: Load .env with `find_dotenv`, never hardcode secrets
- Operational services verified: 7 operational + secure, 1 in setup

**Frontmatter Implications**:
- `mandatory_checks` list (pre-migration analysis, automated safety, enum drift)
- `database_mapping` table (service, container, database, port)
- `secure_config_pattern` requirements
- `state_scenarios` enum

---

### 086-mypy-configuration-standards

**File**: `.claude/rules/086-mypy-configuration-standards.md`
**Purpose**: MyPy configuration and monorepo type checking standards
**Type**: tooling
**Scope**: all
**Enforcement**: high
**Dependencies**: None
**Artifacts**: config
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: MyPy, PDM
**Has Code Examples**: yes (TOML, INI, bash)
**CLI Commands**: `pdm run typecheck-all`, `mypy huleedu_service_libs`
**Config Files**: pyproject.toml, libs/mypy.ini

**Key Characteristics**:
- Problem: PDM editable installs create dual import paths (libs.X vs X)
- Solution: Dual configuration pattern (root excludes libs, libs has isolated mypy.ini)
- Root MyPy: Exclude `libs/huleedu_service_libs/` in pyproject.toml
- Library MyPy: Isolated `libs/mypy.ini` with explicit_package_bases, namespace_packages
- Usage: `pdm run typecheck-all` (root), `cd libs && mypy huleedu_service_libs` (libs)
- Troubleshooting: Clear cache after config changes
- **MUST**: Exclude libs/ in root, isolated mypy.ini for service libs
- Discovery phase vs import following: exclude controls discovery, overrides control imports
- HuleEdu pattern: Root scans services/tests, libs validated ~98-99% via import following
- **DO NOT**: Create overrides for excluded paths (ineffective)
- **DO**: Create overrides for discovered modules
- Verification: Verbose output shows excluded paths and silenced imports

**Frontmatter Implications**:
- `dual_config_pattern` explanation
- `discovery_vs_import` phases
- `verification_commands` with expected output

---

### 087-docker-development-patterns

**File**: `.claude/rules/087-docker-development-patterns.md`
**Purpose**: Docker development patterns - multi-stage builds, layer optimization, workflow commands
**Type**: tooling
**Scope**: infrastructure
**Enforcement**: high
**Dependencies**: None
**Artifacts**: infrastructure
**Maintenance**: evolving
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Docker, PDM, Quart, FastAPI
**Has Code Examples**: yes (Dockerfile, YAML, bash)
**CLI Commands**: docker build, pdm run dev-start/logs/build-clean/recreate/check
**Config Files**: Dockerfile, Dockerfile.dev, docker-compose.dev.yml

**Key Characteristics**:
- Multi-stage build structure: base → development → production
- Base stage: Environment vars, system deps, dependency files first, shared libs, install deps
- Development stage: Create user, copy service code, volume mounts for hot-reload
- Production stage: Copy service code, create user, optimized for deployment
- Development workflow commands: dev-start, dev-logs, dev-build-clean, dev-recreate, dev-check
- Layer caching strategy: System deps (longest) → PDM → dependency files → shared libs → service code (shortest)
- Performance targets: Dev builds <10s, incremental 4-6s, cache hit >95%, code change <3s
- docker-compose.dev.yml: Volume mounts for source code, exclude build artifacts
- Environment variables: Framework-specific (Quart vs FastAPI), service-specific
- Port management: HTTP 7001-7020, Prometheus HTTP+2092, Database 5441-5460
- Security: Non-root user pattern, minimal system dependencies
- **MUST**: Dependencies before code, multi-stage builds, dynamic lockfiles, layer separation
- **MUST NOT**: --no-cache for dev, source before deps, dependencies in final stage only, skip volume mounts
- Service-specific patterns: HTTP (expose ports, health checks), Worker (no ports, logging)
- Implementation status: 6 optimized services, template for remaining

**Frontmatter Implications**:
- `multi_stage_pattern` object (base, development, production)
- `layer_caching_order` list
- `performance_targets` object
- `security_requirements` list

---

### 090-documentation-standards

**File**: `.claude/rules/090-documentation-standards.md`
**Purpose**: Read before any updates to documentation and rules
**Type**: documentation
**Scope**: all
**Enforcement**: high
**Dependencies**: docs/DOCS_STRUCTURE_SPEC.md, TASKS/_REORGANIZATION_PROPOSAL.md, 000-rule-index.md
**Artifacts**: documentation
**Maintenance**: stable
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Markdown
**Has Code Examples**: no
**CLI Commands**: None
**Config Files**: None

**Key Characteristics**:
- **Normative rule**: Canonical for all documentation location, structure, content, formatting
- Normative references: DOCS_STRUCTURE_SPEC, _REORGANIZATION_PROPOSAL, 000-rule-index
- Documentation taxonomy: Architectural, Service, Contract, Code-level, Rules, Task/Programme
- Project layout: All under docs/ with specific taxonomy (overview, architecture, services, operations, etc.)
- Naming: .md extension, kebab-case (new), SCREAMING_SNAKE_CASE (legacy, migrate when touched)
- Service READMEs: **MANDATORY** for every service, MUST update with behavior changes
- Library READMEs: More detailed than services (overview, API, integration, testing, migration, config)
- Contract documentation: Pydantic models are source of truth, auto-generate where possible
- Development rules: .claude/rules/ (.md), .windsurf/rules/ (.md equivalents)
- Rule index: 000-rule-index.md MUST be updated with any rule file changes
- Content style: Concise, technical, lists over narrative, optimized for AI (high info density)
- Task documentation: TASKS/ governed by _REORGANIZATION_PROPOSAL, compress completed tasks
- Documentation as work: REQUIRED part of any task changing behavior/contracts/architecture
- Maintenance: Documentation is versioned code, periodic reconciliation tasks

**Frontmatter Implications**:
- `normative_references` list
- `documentation_taxonomy` enum
- `naming_standards` object (new: kebab-case, legacy: SCREAMING_SNAKE_CASE)
- `mandatory_sections` by doc type (service, library, contract)

---

### 095-textual-tui-patterns

**File**: `.claude/rules/095-textual-tui-patterns.md`
**Purpose**: Textual TUI development patterns and corrections to AI training data
**Type**: implementation
**Scope**: all
**Enforcement**: low
**Dependencies**: None
**Artifacts**: code
**Maintenance**: evolving
**Parent Rule**: None
**Child Rules**: None
**Tech Stack**: Textual (6.5.0+)
**Has Code Examples**: yes
**CLI Commands**: `pdm run python -c "import ..."` (verification)
**Config Files**: None

**Key Characteristics**:
- **CORRECTS AI TRAINING DATA**: Explicit corrections throughout
- Container types: VerticalScroll (scrollable), HorizontalGroup (single-row)
- **FORBIDDEN**: Vertical with overflow-y hack (doesn't work)
- Select widget: Height auto (native), no SelectCurrent CSS selector
- App title: Uppercase TITLE class variable
- Button layout: Equal distribution with 1fr widths
- **FORBIDDEN**: Overriding background/border on Input/Select (conflicts with focus)
- TextLog wrapping: Manual wrapping before write (no wrap parameter)
- Spacing: margin (outside) vs padding (inside)
- Documentation priority: Official docs > source code > AI training data
- **CRITICAL worker patterns**: `from textual import work` NOT `from textual.worker import work`
- Worker decorator: `@work(thread=True, exclusive=True, exit_on_error=False)`
- Thread safety: MUST use `call_from_thread()` for UI updates
- Log widget family: Log (plain text, write_line), RichLog (markup, write only)
- Text display: write() ignores newlines, write_line() creates new lines
- Text wrapping: CSS `text-wrap: wrap` + write_line() (modern), not manual textwrap
- Import verification protocol: Official docs → test in shell → NEVER trust training data
- Known training data errors: work import path, Log markup parameter, RichLog write_line, Log wrap

**Frontmatter Implications**:
- `corrects_training_data: true` field
- `training_data_errors` list
- `widget_comparison` table (Log vs RichLog)
- `import_verification_protocol` steps
- `documentation_urls` for Textual 6.5.0

---

## Pattern Analysis

### 1. Rule Type Distribution

| Type | Count | Percentage | Examples |
|------|-------|------------|----------|
| tooling | 8 | 33.3% | 080-087 series |
| observability | 7 | 29.2% | 071 index + 5 children + 072 |
| testing | 4 | 16.7% | 070, 070.1, 075, 075.1 |
| standards | 1 | 4.2% | 077 (anti-patterns) |
| implementation | 2 | 8.3% | 073, 095 |
| data | 1 | 4.2% | 085 |
| documentation | 1 | 4.2% | 090 |

**New types confirmed from batch 3**:
- `testing` (4 rules)
- `observability` (7 rules)
- `tooling` (8 rules)
- `data` (1 rule - database migrations)

**Comparison to batches 1-2**:
- Batch 1: 64.5% service-spec, 25% implementation
- Batch 2: 43.5% implementation, 0% service-spec
- Batch 3: 33.3% tooling, 29.2% observability, 16.7% testing

**Trend**: Increasing specialization and infrastructure focus

---

### 2. Observability Hierarchy (071.X series)

**Parent**: 071-observability-index (is_index: true)

**Children**:
- 071.1: observability-core-patterns (philosophy, correlation, naming)
- 071.2: prometheus-metrics-patterns (metrics types, service integration, labels)
- 071.3: jaeger-tracing-patterns (OpenTelemetry, trace propagation, debugging)
- 071.4: grafana-loki-patterns (dashboards, log queries, datasource config)
- 071.5: llm-debugging-with-observability (LLM debugging workflows)

**Related (not child)**:
- 072: grafana-playbook-rules (operational patterns)

**Pattern**: Technology-specific sub-rules under index
- Index provides quick reference URLs, stack access, import order
- Each child focuses on specific technology in observability stack
- Enforcement: Index (high), Core (critical), Specific tech (high), LLM debugging (medium)

**Frontmatter consistency issue**:
- 071, 071.1, 071.2, 071.3, 071.4, 072: Have frontmatter ✅
- 071.5: **NO frontmatter** ❌ (inconsistency)

---

### 3. Testing Methodology Hierarchy (070.X, 075.X)

**Testing standards**:
- 070: testing-and-quality-assurance (core standards, runner patterns)
  - 070.1: performance-testing-methodology (testcontainers, performance targets)

**Testing methodology**:
- 075: test-creation-methodology (ULTRATHINK, systematic creation)
  - 075.1: parallel-test-creation-methodology (batch execution, architect review)

**Pattern**: Methodology-specific sub-rules
- 070 series: What to test and how to run tests
- 075 series: How to create tests systematically
- Both have parent-child relationships

**Frontmatter consistency issue**:
- 070, 070.1, 075: Have frontmatter ✅
- 075.1: **NO frontmatter** ❌ (inconsistency)

---

### 4. Docker Standards Hierarchy (084.X)

**Parent**: 084-docker-containerization-standards

**Child**:
- 084.1: docker-compose-v2-command-reference

**Pattern**: Core standards + command reference
- Parent: Architectural patterns (PYTHONPATH, Dockerfile.deps, build commands)
- Child: Syntax transformation reference (v1 → v2)

**Both have frontmatter** ✅

---

### 5. Development Tooling Concentration (080-087)

**8 consecutive rules on dev tooling ecosystem**:
- 080: repository-workflow-and-tooling (PDM, Git, Docker workflow)
- 081: pdm-dependency-management (minimal config, version strategy)
- 082: ruff-linting-standards (core settings, VS Code integration)
- 083: pdm-standards-2025 (overrides training data, mandatory minimums)
- 084: docker-containerization-standards (PYTHONPATH, Dockerfile.deps)
- 084.1: docker-compose-v2-command-reference (syntax transformation)
- 085: database-migration-standards (Alembic, secure config)
- 086: mypy-configuration-standards (dual config pattern)
- 087: docker-development-patterns (multi-stage builds, layer optimization)

**Observation**: Tightly coupled tooling ecosystem
- PDM (081, 083): Dependency management
- Ruff (082): Linting/formatting
- MyPy (086): Type checking
- Docker (084, 084.1, 087): Containerization
- Alembic (085): Database migrations
- Git (080): Version control

**All 9 rules have frontmatter** ✅ (100% compliance in tooling cluster)

**CLI commands heavily documented**: 8/9 rules document CLI usage patterns

---

### 6. Index Pattern Emergence

**Confirmed indexes**:
1. **000-rule-index**: Master rule index (all rules)
2. **071-observability-index**: Observability patterns (5 children + 1 related)

**Index characteristics**:
- Have `is_index: true` (should be in schema)
- List child rules with location and purpose
- Provide quick reference (URLs, commands, import order)
- Lower code example percentage (indexes are navigation/reference)

**Frontmatter**: Both indexes have frontmatter ✅

---

### 7. Anti-Pattern Rules

**Single anti-pattern rule**: 077-service-anti-patterns

**Characteristics**:
- **Negative guidance**: Documents what NOT to do
- Enforcement: critical (despite being "don't do this")
- Categories: Infrastructure, health, events, database, DI, config, testing
- Format: ❌ WRONG vs ✅ RIGHT code examples
- Production issues: MissingGreenlet, DetachedInstanceError, memory leaks

**Unique among all rules analyzed**: Only rule with primarily negative guidance

**Frontmatter**: Has frontmatter ✅, should include `is_negative_guidance: true`

---

## Schema Evolution from Batches 1+2

### New Rule Types Confirmed

**From batch 3**:
- `testing` (070, 070.1, 075, 075.1)
- `observability` (071.X series, 072)
- `tooling` (080-087 series)
- `data` (085)

**Complete taxonomy so far** (batches 1-3):
- foundation, architecture, service-spec (batch 1)
- implementation, standards, operations (batches 1-2)
- testing, observability, tooling, data, documentation (batch 3)

**Awaiting batch 4**:
- Frontend rules (200-210 series likely)
- Agent-specific rules (110.X series)
- Meta-rules (999)

---

### New Fields Needed

**From batch 3 analysis**:

1. **is_index**: bool
   - Applies to: 000, 071
   - Indexes list child rules with navigation guidance

2. **child_rules**: list[str]
   - Applies to: 000 (all rules), 071 (071.1-071.5), 070 (070.1), 075 (075.1), 084 (084.1)
   - Lists immediate children only

3. **cli_commands**: list[str] | None
   - Applies to: 18/24 rules in batch 3 (75%)
   - Examples: `pdm run pytest-root`, `logcli query`, `docker compose up`, `../../.venv/bin/alembic upgrade`

4. **config_files**: list[str] | None
   - Applies to: 15/24 rules in batch 3 (62.5%)
   - Examples: pyproject.toml, docker-compose.yml, alembic.ini, libs/mypy.ini

5. **is_negative_guidance**: bool
   - Applies to: 077 only (so far)
   - Indicates rule documents anti-patterns (what NOT to do)

6. **stack_urls**: object | None
   - Applies to: 071 (observability stack URLs)
   - Format: `{service_name: url, internal_service_name: internal_url}`

7. **performance_targets**: object | None
   - Applies to: 070.1, 080, 087
   - Format: `{metric_name: target_value}` (e.g., `redis_ops: "<0.1s"`)

8. **normative_references**: list[str] | None
   - Applies to: 090 (documentation standards)
   - Lists canonical specification documents this rule references

9. **corrects_training_data**: bool
   - Applies to: 083, 095
   - Indicates rule explicitly overrides AI training data

10. **minimum_versions**: object | None
    - Applies to: 083 (tool minimums)
    - Format: `{tool_name: version}` (e.g., `PDM: "2.22.0"`)

---

### New Artifact Types

**From batch 3**:
- `tests` (testing rules)
- `metrics` (Prometheus)
- `logs` (Loki)
- `traces` (Jaeger)
- `config` (pyproject.toml, mypy.ini, etc.)
- `infrastructure` (Docker, Alembic)

**Complete artifact types** (batches 1-3):
- code, config, contracts, documentation (batches 1-2)
- tests, metrics, logs, traces, infrastructure (batch 3)
- mixed (all batches)

---

### Validation Rules Discovered

**From batch 3**:

1. **Index rules** (`is_index: true`) should list `child_rules`
   - Verified: 000, 071 both have children

2. **Tooling rules** should document `cli_commands`
   - Verified: 8/9 tooling rules (080-087) document CLI usage

3. **Observability rules** should specify `artifact_type`
   - 071.1: logs, metrics, traces
   - 071.2: metrics
   - 071.3: traces
   - 071.4, 071.5: logs

4. **Parent-child consistency**:
   - If rule has child, child's parent field should match
   - If rule has parent, parent's child_rules should include it
   - **Issue found**: 071.5 and 075.1 missing frontmatter (can't validate parent)

5. **Sub-rule numbering**:
   - Pattern: `{parent}.{child}` (e.g., 071.1, 071.2)
   - Max depth observed: 1 level (no 071.1.1 or deeper)

6. **Frontmatter compliance**:
   - **Should be mandatory** for all rules
   - Current: 91.7% (22/24) in batch 3
   - Missing: 071.5, 075.1 (both sub-rules)

---

### Technology Stack Taxonomy

**Observability Stack (071.X)**:
- Prometheus (metrics)
- Jaeger (traces)
- Grafana (dashboards)
- Loki (logs)
- Promtail (log ingestion)
- OpenTelemetry (instrumentation)

**Development Tools (080-087)**:
- PDM (dependency management)
- Ruff (linting/formatting)
- MyPy (type checking)
- Docker (containerization)
- Docker Compose v2 (orchestration)
- Alembic (migrations)
- Git (version control)

**Testing Stack (070, 075)**:
- pytest (test framework)
- testcontainers (integration tests)
- Dishka (DI mocking)

**Service Frameworks**:
- Quart (HTTP services)
- FastAPI (client-facing)
- Textual (TUI)

**Infrastructure**:
- PostgreSQL (database)
- Redis (caching/queues)
- Kafka (events)

---

## Comparison Across Batches

| Metric | Batch 1 | Batch 2 | Batch 3 | Trend |
|--------|---------|---------|---------|-------|
| Total Rules | 31 | 23 | 24 | Consistent (~25/batch) |
| Service-Spec | 64.5% | 0% | 0% | Declining (front-loaded) |
| Implementation | 25% | 43.5% | 8.3% | Peaked in batch 2 |
| Testing | 0% | 0% | 16.7% | New in batch 3 |
| Observability | 0% | 0% | 29.2% | New in batch 3 |
| Tooling | 0% | 0% | 33.3% | New in batch 3 |
| Has Frontmatter | 80% | 34.8% | 91.7% | U-shaped (low in batch 2) |
| Has Code Examples | ~30% | 82.6% | 66.7% | Peaked in batch 2 |
| Parent-Child Hierarchies | 1 (020.X) | 4 | 5 | Increasing complexity |
| Index Rules | 1 (000) | 0 | 1 (071) | Indexes at boundaries |
| CLI Documentation | Low | Medium | **High** (18/24) | Increasing |
| Config File References | Low | Medium | **High** (15/24) | Increasing |

**Key observations**:
- **Batch 1**: Service specifications (what services do)
- **Batch 2**: Implementation details (how to build services)
- **Batch 3**: Development infrastructure (how to test, observe, deploy)

**Frontmatter anomaly in batch 2**: Only 34.8% vs 80% (batch 1) and 91.7% (batch 3)
- Likely due to rapid implementation rule creation without frontmatter discipline
- Batch 3 shows recovery to high compliance

**Code examples**: Highest in batch 2 (implementation-heavy), moderate in batch 3 (index/reference rules dilute percentage)

**Hierarchies**: Increasing complexity
- Batch 1: 1 hierarchy (020.X service types)
- Batch 2: 4 hierarchies (041.X async, 042.X DI, 050.X event, 051.X contracts)
- Batch 3: 5 hierarchies (070.X testing, 071.X observability, 075.X methodology, 084.X docker)

---

## Frontmatter Issues Found

### Missing Frontmatter

**2 rules without frontmatter** (91.7% compliance):

1. **071.5-llm-debugging-with-observability.md**
   - Has header but no YAML frontmatter
   - Inconsistent with siblings (071.1-071.4 all have frontmatter)
   - Should add: `description`, `globs`, `alwaysApply: false`

2. **075.1-parallel-test-creation-methodology.md**
   - Has header but no YAML frontmatter
   - Inconsistent with parent (075 has frontmatter)
   - Should add: `description`, `globs`, `alwaysApply: false`

**Pattern**: Both missing frontmatter rules are **sub-rules** (071.5, 075.1)
- May indicate less discipline for child rules
- Should be fixed for consistency

---

### Frontmatter ID Mismatches

**None found in batch 3** (unlike batch 2 which had several)

All 22 rules with frontmatter have correct `description` fields matching filename/purpose.

---

### Frontmatter Compliance by Rule Type

| Rule Type | Total | With Frontmatter | Compliance |
|-----------|-------|------------------|------------|
| testing | 4 | 3 | 75% (missing: 075.1) |
| observability | 7 | 6 | 85.7% (missing: 071.5) |
| tooling | 8 | 8 | **100%** ✅ |
| standards | 1 | 1 | **100%** ✅ |
| implementation | 2 | 2 | **100%** ✅ |
| data | 1 | 1 | **100%** ✅ |
| documentation | 1 | 1 | **100%** ✅ |

**Observation**: Tooling rules have perfect frontmatter compliance (8/8)
- Likely due to tooling-focused developers being more systematic
- Testing and observability rules have gaps (both at sub-rule level)

---

### AlwaysApply Patterns

**alwaysApply: true** (6 rules):
- 070: testing-and-quality-assurance (critical for all work)
- 077: service-anti-patterns (avoid production failures)
- 085: database-migration-standards (critical for DB work)
- 087: docker-development-patterns (globs match Dockerfile/docker-compose)
- 090: documentation-standards (critical for all docs)

**alwaysApply: false** (16 rules):
- All observability rules (071.X, 072) - activate when working on observability
- All sub-methodology rules (070.1, 075, 075.1) - activate for specific test types
- All tooling config rules (081, 082, 083, 086) - activate when editing configs
- Docker v2 reference (084.1) - activate when using docker commands
- Textual TUI (095) - activate for TUI development

**Pattern**: Core standards have alwaysApply: true, specialized rules have false

---

## Recommendations for Batch 4

Batch 4 (100-999) should cover:
- **100**: Terminology (glossary)
- **110.X series**: AI agent interaction modes (7 rules expected based on index)
- **111**: Cloud VM execution
- **200-210**: Frontend rules (React, TypeScript, etc.)
- **999**: Rule management (meta-rule)

**Watch For**:

1. **Frontend vs Backend Scope Split**
   - Expect new `scope: frontend` rules (200-210)
   - Possible new rule types: `frontend`, `ui`, `client`
   - Tech stack: React, TypeScript, Vite, Tailwind

2. **Agent-Specific Rules (110.X)**
   - Likely 7 children under 110 (agent interaction modes)
   - May introduce `agent_type` field
   - Possible new artifact types: `prompts`, `agent_config`

3. **Meta-Rules (999)**
   - Rule for managing rules themselves
   - May introduce `meta: true` field
   - Likely `is_negative_guidance` patterns for rule anti-patterns

4. **Terminology (100)**
   - Glossary rule, possibly index-like structure
   - May introduce `is_glossary: true` field
   - Likely `terms` array with definitions

**Schema Refinements Before Batch 4**:

1. **Finalize rule type taxonomy**
   - Add: frontend, ui, client, meta, glossary
   - Confirm complete list after batch 4

2. **Confirm artifact type enums**
   - Current: code, config, contracts, documentation, tests, metrics, logs, traces, infrastructure, mixed
   - Add from batch 4: prompts, agent_config, ui_components

3. **Validate technology stack list**
   - Current observability: Prometheus, Jaeger, Loki, Grafana
   - Current dev tools: PDM, Ruff, MyPy, Docker, Alembic
   - Current frameworks: Quart, FastAPI, Textual
   - Add from batch 4: React, TypeScript, Vite, etc.

4. **Establish index rule pattern**
   - Confirmed: `is_index: true`, `child_rules: [...]`
   - Expect: 110 (agent modes index), possibly 200 (frontend index)

5. **Fix frontmatter gaps**
   - **BEFORE batch 4**: Add frontmatter to 071.5, 075.1
   - Target: 100% frontmatter compliance for batches 1-3

6. **Document CLI command patterns**
   - 75% of batch 3 rules have CLI commands
   - Establish `cli_commands` field in schema
   - Categorize by tool (PDM, Docker, Alembic, etc.)

7. **Validate parent-child relationships**
   - After fixing 071.5, 075.1 frontmatter
   - Ensure bidirectional consistency (parent lists child, child references parent)

---

## Summary

Batch 3 completes the **development infrastructure layer** of the HuleEdu rulebook:

- **Testing**: 4 rules covering standards, performance, and systematic creation
- **Observability**: 7 rules (index + 5 children + playbook) covering Prometheus, Jaeger, Loki, Grafana
- **Tooling**: 8 consecutive rules covering PDM, Ruff, MyPy, Docker, Alembic
- **Standards**: 1 anti-pattern rule (negative guidance)
- **Implementation**: 2 rules (health endpoints, Textual TUI)
- **Documentation**: 1 normative rule governing all documentation

**Key patterns discovered**:
1. Index pattern (071 like 000)
2. Technology-specific hierarchies (observability, testing, docker)
3. CLI command documentation (75% of rules)
4. Config file references (62.5% of rules)
5. Negative guidance rule (077)
6. Training data corrections (083, 095)

**Frontmatter status**: 91.7% compliance (22/24), gaps at sub-rule level (071.5, 075.1)

**Batch 4 preview**: Frontend (200-210), agent modes (110.X), meta-rules (999), terminology (100)

**Schema ready for**: All batch 3 patterns captured, additional fields identified, validation rules established.
