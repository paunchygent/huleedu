---
id: smoketest-automation-design
title: 'TASK: Comprehensive Smoketest Automation Design'
type: task
status: proposed
priority: medium
domain: assessment
service: ''
owner_team: agents
owner: ''
program: ''
created: '2025-11-16'
last_updated: '2026-02-01'
related: []
labels: []
---
**Status**: 🔵 RESEARCH & PLANNING
**Priority**: HIGH
**Created**: 2025-11-13
**Type**: Infrastructure & Testing

## Purpose

Design and implement a comprehensive, automated smoketest suite that validates the HuleEdu platform's core functionality, service health, and integration points before deployments, after configuration changes, and as part of CI/CD pipelines.

## Context

Currently, the platform has:

- Individual service health checks (`/healthz` endpoints)
- Configuration validation (`scripts/validate_service_config.py`)
- Docker health checks in compose files
- Manual smoke testing references in handoff docs
- Integration tests in service directories
- ENG5 runner for end-to-end CJ validation

**Gap**: No unified, automated smoketest that validates the entire platform is functional and ready for use.

---

## Research Phase

### 1. Health Check Inventory & Patterns

**Question**: What health check capabilities do we currently have?

**Research Points**:

- [ ] Document all service `/healthz` endpoint implementations
  - What information do they return? (service name, status, dependencies, version?)
  - Do they check database connectivity?
  - Do they check external service dependencies?
  - Do they differentiate between "live" and "ready" states?
  - Pattern: Look at `services/*/api/health_routes.py`

- [ ] Catalog service-specific health endpoints
  - `/healthz` - basic health
  - `/healthz/database` - database connectivity
  - `/healthz/database/summary` - connection pool stats
  - `/healthz/live` - liveness probe (service is alive)
  - `/healthz/ready` - readiness probe (service can accept traffic)
  - Which services implement which patterns?

- [ ] Review docker-compose healthcheck configurations
  - What commands are used? (curl, pg_isready, custom scripts?)
  - What are the intervals, timeouts, retries, start_period?
  - Are they consistent across services?
  - File: `docker-compose.services.yml`

**Open Questions**:

- Should smoketest call internal health endpoints or external ports?
- How do we handle services that are slow to start? (grace periods)
- Should we distinguish between critical vs non-critical services?

---

### 2. Service Dependency Graph

**Question**: What are the critical paths and dependencies in our platform?

**Research Points**:

- [ ] Map service dependencies from docker-compose `depends_on`
  - Which services are foundational? (databases, kafka, redis)
  - Which services depend on which others?
  - What's the startup order?

- [ ] Identify external dependencies
  - Third-party APIs (Anthropic, OpenAI, etc.)
  - Infrastructure (Kafka, Redis, PostgreSQL)
  - Storage systems (MinIO, S3, file system)

- [ ] Document critical user paths
  - Admin authentication flow
  - Essay upload and processing
  - CJ assessment creation and execution
  - Result retrieval

**Open Questions**:

- What's the minimum viable set of services for basic functionality?
- Should we test service-to-service communication or just endpoints?
- How do we handle optional/feature-flagged services?

---

### 3. Test Coverage Analysis

**Question**: What existing tests can we leverage or learn from?

**Research Points**:

- [ ] Review existing integration tests
  - Location: `services/*/tests/integration/`
  - What do they test? (database, kafka, HTTP?)
  - Can we extract common patterns?

- [ ] Review end-to-end tests
  - Location: `scripts/tests/test_eng5_np_*.py`
  - What workflows do they validate?
  - What setup do they require?

- [ ] Review manual validation guides
  - File: `scripts/docs/manual_validation_guide.md`
  - What steps are currently manual?
  - Which can be automated?

- [ ] Check PDM test scripts
  - `test-all`, `test-parallel`, `test-financial`
  - What markers exist? (@pytest.mark.integration, @slow, @docker, @e2e)
  - Can we create a @smoketest marker?

**Open Questions**:

- Should smoketest be a pytest suite or a standalone script?
- How much overlap with existing tests is acceptable?
- Should we mock external APIs or test against real services?

---

### 4. Failure Detection & Diagnostics

**Question**: What information do we need when a smoketest fails?

**Research Points**:

- [ ] Review observability stack
  - Logging: structured logs, log levels
  - Metrics: Prometheus endpoints at `/metrics`
  - Tracing: Jaeger, correlation IDs
  - Where are logs stored? (docker logs, files, aggregator?)

- [ ] Identify common failure modes
  - Service not starting (docker exit codes)
  - Service started but not healthy (health check fails)
  - Service healthy but endpoint fails (500 errors)
  - Service works but slow (performance degradation)
  - Configuration issues (missing env vars, wrong values)
  - Integration issues (can't connect to dependency)

- [ ] Review existing diagnostic tools
  - `scripts/trace_search.py` - correlation ID tracing
  - `docker logs` with grep patterns
  - Database query tools
  - Kafka topic inspection

**Open Questions**:

- How verbose should smoketest output be? (summary vs detailed)
- Should we capture logs on failure automatically?
- Should we include performance thresholds? (response time SLAs)
- How do we differentiate between expected dev issues vs critical failures?

---

### 5. Environment Considerations

**Question**: Where will smoketest run and how should it adapt?

**Research Points**:

- [ ] Document environment types
  - Development (local docker-compose)
  - CI/CD (GitHub Actions, Jenkins?)
  - Staging/Production (cloud deployment)
  - Developer laptop (limited resources)

- [ ] Review configuration patterns
  - Environment detection: `ENVIRONMENT` env var
  - Configuration files: `.env`, docker-compose overrides
  - Service discovery: hardcoded ports vs DNS

- [ ] Check resource constraints
  - Can all services run on a developer laptop?
  - What's the minimum RAM/CPU needed?
  - Are there services that can be skipped in dev?

**Open Questions**:

- Should there be different smoketest levels? (minimal, standard, comprehensive)
- How do we handle cloud-only services in local dev?
- Should we support "offline" mode with mocks?

---

### 6. Integration with Existing Tools

**Question**: How does smoketest fit into existing workflows?

**Research Points**:

- [ ] Review existing validation scripts
  - `scripts/validate_service_config.py` - configuration validation
  - `scripts/prod.sh health` - production health check
  - `scripts/dev.sh` commands

- [ ] Check CI/CD integration points
  - Look for `.github/workflows/` or similar
  - What tests currently run in CI?
  - Where would smoketest fit?

- [ ] Review PDM scripts organization
  - File: `pyproject.toml` [tool.pdm.scripts]
  - Naming conventions: `dev-*`, `prod-*`, `test-*`, `validate-*`
  - Where should `smoketest` live?

**Open Questions**:

- Should smoketest be part of `pdm run dev-start` or separate?
- Should it run automatically or require explicit invocation?
- Should we integrate with pre-commit hooks?
- Should there be a `pdm run smoketest-dev` vs `pdm run smoketest-prod`?

---

### 7. Test Data & Fixtures

**Question**: What test data do we need and how do we manage it?

**Research Points**:

- [ ] Review test data locations
  - `test_uploads/` - sample essays and prompts
  - `scripts/seed-dev-data.sh` - database seeding
  - Service-specific fixtures in `tests/fixtures/`

- [ ] Check identity/auth requirements
  - Admin user creation
  - JWT token generation
  - Role-based access testing

- [ ] Review database reset patterns
  - `scripts/reset-dev-databases.sh`
  - `scripts/db_reset.sh`
  - `scripts/reset_test_environment.sh`

**Open Questions**:

- Should smoketest create its own test data or use existing fixtures?
- Should it clean up after itself or leave artifacts for debugging?
- How do we handle test data isolation? (unique IDs, timestamps)
- Should we test against empty databases or pre-seeded data?

---

### 8. Performance & Speed Requirements

**Question**: How fast should smoketest be?

**Research Points**:

- [ ] Measure current test execution times
  - Health check response times (curl timing)
  - Service startup times (docker-compose up timing)
  - Integration test durations

- [ ] Review Docker optimization strategies
  - Image caching
  - Volume mounts vs COPY
  - Parallel container startup

- [ ] Check test parallelization options
  - pytest-xdist for parallel tests
  - Docker compose parallel starts
  - Async HTTP requests

**Open Questions**:

- What's acceptable smoketest duration? (30s? 2min? 5min?)
- Should we optimize for speed or comprehensiveness?
- Can we run checks in parallel safely?
- Should we have "quick" vs "full" smoketest modes?

---

### 9. Reporting & Output

**Question**: What format should smoketest results take?

**Research Points**:

- [ ] Review existing report formats
  - pytest output (verbose, summary, junit XML)
  - `scripts/validate_service_config.py` output (emoji, colored text)
  - Docker health check status

- [ ] Check CI/CD reporting requirements
  - Exit codes (0 = success, non-zero = failure)
  - Structured logs (JSON, XML)
  - Human-readable summaries

- [ ] Review notification needs
  - Console output for developers
  - Log files for debugging
  - Metrics for dashboards
  - Alerts for failures

**Open Questions**:

- Should we generate HTML reports?
- Should results be stored for historical comparison?
- Should we integrate with monitoring systems?
- Should there be different output formats for dev vs CI?

---

### 10. Failure Recovery & Retry Logic

**Question**: How should smoketest handle transient failures?

**Research Points**:

- [ ] Review retry patterns in codebase
  - HTTP client retry logic
  - Kafka consumer retry configuration
  - Database connection retry attempts

- [ ] Check timeout configurations
  - Health check timeouts in docker-compose
  - HTTP request timeouts in services
  - Database query timeouts

- [ ] Review circuit breaker patterns
  - How do services handle dependency failures?
  - Are there graceful degradation strategies?

**Open Questions**:

- Should smoketest retry failed checks? (how many times?)
- Should there be exponential backoff?
- Should we distinguish between retryable vs fatal failures?
- How do we avoid false negatives from slow starts?

---

## Design Considerations

### Architecture Options

**Option A: Pytest-based Suite**

- Pros: Leverages existing test infrastructure, good IDE integration, markers, fixtures
- Cons: Requires pytest dependencies, might be slower, more complex

**Option B: Standalone Python Script**

- Pros: Simple, fast, minimal dependencies, easy to run anywhere
- Cons: Less structured, harder to extend, no test framework features

**Option C: Shell Script**

- Pros: Very fast, no Python dependencies, easy to read
- Cons: Limited error handling, harder to maintain, platform-dependent

**Option D: Hybrid Approach**

- Core validation: Fast shell script for basic checks
- Extended validation: Pytest suite for integration tests
- Both callable via PDM scripts

### Scope Levels

**Level 1: Configuration & Infrastructure (< 10s)**

- [ ] Configuration validation (`validate-config`)
- [ ] Docker services running (`docker ps`)
- [ ] Port availability checks

**Level 2: Service Health (< 30s)**

- [ ] All `/healthz` endpoints respond 200
- [ ] Database connectivity checks
- [ ] Redis connectivity
- [ ] Kafka broker reachable

**Level 3: Critical Paths (< 2min)**

- [ ] Admin authentication flow
- [ ] Content upload (small file)
- [ ] Health with database summary
- [ ] Metrics endpoints responding

**Level 4: Integration Workflows (< 5min)**

- [ ] End-to-end CJ assessment (minimal)
- [ ] Inter-service communication
- [ ] Event publishing and consumption
- [ ] Storage operations

---

## Success Criteria

A successful smoketest implementation should:

- ✅ Detect configuration issues before runtime (JWT keys, database URLs, etc.)
- ✅ Verify all critical services are running and healthy
- ✅ Validate core user workflows function correctly
- ✅ Complete in reasonable time (< 2 minutes for standard checks)
- ✅ Provide clear, actionable error messages on failure
- ✅ Run consistently across dev, CI, and staging environments
- ✅ Integrate seamlessly with existing development workflows
- ✅ Require minimal maintenance as platform evolves

---

## Next Steps

1. **Complete Research Phase**: Answer all open questions above
2. **Review & Discuss**: Share findings with team, align on priorities
3. **Design Document**: Create detailed design based on research
4. **Prototype**: Implement minimal viable smoketest
5. **Iterate**: Expand based on feedback and real-world usage
6. **Document**: Update `scripts/README.md` and relevant guides
7. **Integrate**: Add to CI/CD and development workflows

---

## Related Documents

- `TASKS/002-eng5-cli-validation.md` - End-to-end validation patterns
- `scripts/validate_service_config.py` - Configuration validation patterns
- `scripts/prod.sh` - Production health check implementation
- `docker-compose.services.yml` - Service health check definitions
- `.agent/rules/075-test-creation-methodology.md` - Testing standards

---

## Notes

This task intentionally starts with research and open questions rather than implementation assumptions. The goal is to understand what we actually need before building it, avoiding the trap of creating tools based on incomplete context.

**Key Principle**: Measure twice, cut once. Invest time in understanding requirements before writing code.
