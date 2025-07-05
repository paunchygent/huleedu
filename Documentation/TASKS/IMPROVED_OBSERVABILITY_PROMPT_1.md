📊 THINK VERY HARD: Complete HuleEdu Observability Stack Resolution -
  Dashboard Query Failures and Critical Architecture Gaps

  ⚡ CRITICAL: This task requires systematic analysis of persistent dashboard
  failures, metric collection inconsistencies, and architectural observability
  gaps. Use subagents extensively for research, validation, and implementation.
  Do not proceed without thorough analysis of all identified issues.

  Context and Problem Statement

  The HuleEdu observability stack has persistent critical issues that prevent
  effective operational monitoring:

  🚨 Immediate Issues (Blocking Operations)

  1. Dashboard Query Failures: Grafana panels showing "Status: 500. Message:
  parse error at line 1, col 166: syntax error: unexpected IDENTIFIER"
  2. No Data Panels: Service Deep Dive dashboard shows "No Data" despite
  services being UP
  3. Broken Recording Rules: Recording rules reference non-existent metrics
  4. Inconsistent Metric Collection: Only 3 out of 10+ services properly expose
  HTTP metrics to Prometheus

  🏗️ Critical Architecture Gaps (Systemic Issues)

  1. Metric Naming Inconsistency: Services use different metric name patterns
  (http_requests_total vs service_specific_http_requests_total)
  2. Incomplete Circuit Breaker Integration: Circuit breaker metrics defined but
   not collected by Prometheus
  3. Recording Rule Fragmentation: Recording rules assume metrics exist that
  services don't expose
  4. Service Discovery Gaps: 14 services UP in Prometheus, but only 3 have HTTP
  metrics
  5. Observability Pattern Violations: Services not following established
  observability standards

  Required Architecture Knowledge

  MUST READ these observability rules before implementation:

- .cursor/rules/071-observability-core-patterns.mdc - Core observability
  philosophy and requirements
- .cursor/rules/071.1-prometheus-metrics-patterns.mdc - Metric naming and
  collection standards
- .cursor/rules/072-grafana-playbook-rules.mdc - Dashboard creation and query
  standards
- .cursor/rules/044-service-debugging-and-troubleshooting.mdc - Service
  debugging patterns

  Validation Evidence and Troubleshooting Information

  ✅ Confirmed Working Components

- Prometheus Targets: 14/14 services showing UP status
- Loki Integration: Working with <http://loki:3100>, ingesting logs with
  correlation_id labels
- AlertManager: Working with <http://alertmanager:9093> (internal)
- Jaeger: Working with 8 services providing traces
- Infrastructure Exporters: Kafka (21 metrics), Redis (182 metrics),
  PostgreSQL, Node all operational

  ❌ Confirmed Broken Components

- HTTP Metrics Collection: Only 3 services (content_service, file_service,
  cj_assessment_service) expose HTTP metrics to Prometheus
- Recording Rules: Reference non-existent metrics like
  bos_http_requests_total, llm_provider_http_requests_total
- Dashboard Queries: All panels using
  huleedu:service_http_requests:rate5m{service="${service}"} fail with syntax
  errors
- Circuit Breaker Metrics: Defined in service code but not appearing in
  Prometheus scraping

  🔍 Diagnostic Evidence

  Prometheus Metrics Availability:

# Working metrics (confirmed in Prometheus)

  curl "<http://localhost:9091/api/v1/query?query=rate(http_requests_total[5m>])"

# 161 metrics from content_service

  curl "<http://localhost:9091/api/v1/query?query=rate(file_service_http_requests>
  _total[5m])" # 5 metrics
  curl "<http://localhost:9091/api/v1/query?query=rate(cj_assessment_http_request>
  s_total[5m])" # Available

# Missing metrics (not in Prometheus)

  curl
  "<http://localhost:9091/api/v1/query?query=rate(bos_http_requests_total[5m>])" #
   0 results
  curl "<http://localhost:9091/api/v1/query?query=rate(llm_provider_http_requests>
  _total[5m])" # 0 results

  Service Metrics Exposure vs. Prometheus Collection:

# Service exposes metrics but Prometheus doesn't collect them

  curl "<http://localhost:8090/metrics>" | grep "llm_provider_http_requests_total"

# EXISTS in service

  curl "<http://localhost:5001/metrics>" | grep "bos_http_requests_total" # EXISTS
   in service

# But not available in Prometheus queries - indicates scraping/naming issues

  Critical File References

  Broken Configuration Files

- observability/prometheus/rules/recording_rules.yml - Contains references to
  non-existent metrics
- observability/grafana/dashboards/HuleEdu_Service_Deep_Dive_Template.json -
  Contains broken PromQL queries
- observability/prometheus/prometheus.yml - May have incorrect service
  discovery or naming

  Service Metrics Implementation Files

- services/llm_provider_service/metrics.py - Contains 150+ metrics including
  HTTP requests (why not in Prometheus?)
- services/batch_orchestrator_service/metrics.py - Contains HTTP metrics (why
  not scraped?)
- services/*/metrics.py - All service metric implementations need analysis

  Working Examples for Reference

- services/content_service/ - HTTP metrics working in Prometheus
- services/file_service/ - HTTP metrics working in Prometheus
- services/cj_assessment_service/ - HTTP metrics working in Prometheus

  MANDATORY RESEARCH QUESTIONS - Answer with Evidence Before Implementation

  Use subagents to systematically answer these questions:

  1. Metric Collection Gap Analysis

- Why do only 3 out of 14 services have HTTP metrics in Prometheus when all
  services expose /metrics endpoints?
- What is the exact metric naming pattern each service uses vs. what recording
   rules expect?
- Are there Prometheus scraping configuration issues preventing metric
  collection?
- What is the discrepancy between service metric exposure and Prometheus
  ingestion?

  2. Dashboard Query Syntax Analysis

- What is the exact character at position 166 causing the parse error in
  PromQL queries?
- How do the current dashboard queries violate PromQL syntax rules?
- What are the correct PromQL patterns for the available metrics?
- Why do service variable substitutions cause syntax errors?

  3. Recording Rule Architecture Review

- Which recording rules reference metrics that don't exist in Prometheus?
- How should recording rules be restructured to work with actual available
  metrics?
- What is the correct pattern for service-specific metric aggregation?
- Should recording rules use different approaches (union queries vs.
  individual service queries)?

  4. Circuit Breaker Integration Analysis

- Why are circuit breaker metrics defined in service code but not collected by
   Prometheus?
- What is preventing circuit breaker state metrics from appearing in
  Prometheus targets?
- How should circuit breaker registry integration work with Prometheus
  scraping?
- What is the correct implementation pattern for circuit breaker
  observability?

  5. Service Discovery and Naming Consistency

- What are the naming pattern discrepancies between service job names and
  metric prefixes?
- How should service discovery be configured to properly collect all service
  metrics?
- What standardization is needed across service metric naming patterns?
- Are there port or endpoint configuration issues preventing metric
  collection?

  Implementation Strategy with Subagent Usage

  Phase 1: Deep Diagnostic Analysis (Use Multiple Subagents)

  1. Metrics Collection Audit Subagent: Systematically audit metric availability
   across all 14 services
  2. PromQL Syntax Analysis Subagent: Analyze exact syntax errors in dashboard
  queries
  3. Recording Rules Validation Subagent: Validate all recording rules against
  actual available metrics
  4. Service Discovery Analysis Subagent: Analyze Prometheus service discovery
  and scraping configuration

  Phase 2: Architecture Gap Identification

  1. Identify all metric naming inconsistencies across services
  2. Map service metric exposure vs. Prometheus collection gaps
  3. Document circuit breaker integration failures
  4. Analyze recording rule architecture problems

  Phase 3: Systematic Resolution

  1. Prometheus Configuration Fix: Correct service discovery and scraping issues
  2. Recording Rules Reconstruction: Rebuild recording rules with actual
  available metrics
  3. Dashboard Query Correction: Fix all PromQL syntax errors with working
  queries
  4. Circuit Breaker Integration: Implement proper circuit breaker metric
  collection
  5. Service Metrics Standardization: Establish consistent patterns across
  services

  Success Criteria

  Immediate Resolution (Critical)

- ✅ All dashboard panels show data without syntax errors
- ✅ Service variable dropdown works correctly with all 14 services
- ✅ Recording rules execute without referencing non-existent metrics
- ✅ HTTP request rate, error rate, and latency panels functional for all
  services

  Architecture Excellence (Strategic)

- ✅ All 14 services properly expose HTTP metrics to Prometheus
- ✅ Circuit breaker metrics collected and visualized across all services with
   circuit breakers
- ✅ Consistent metric naming patterns across all services
- ✅ Recording rules efficiently aggregate metrics without performance issues
- ✅ Service Deep Dive dashboard provides actionable operational insights for
  every service

  Observability Maturity (Long-term)

- ✅ Complete service health visibility across all HuleEdu microservices
- ✅ Circuit breaker monitoring provides proactive operational awareness
- ✅ Business metrics correlation with technical metrics for all services
- ✅ Dashboard performance optimized with efficient PromQL queries
- ✅ Observability patterns standardized and documented for future services

  Anti-Patterns to Avoid

  DO NOT:

- Create quick fixes that bypass proper metric collection architecture
- Ignore metric naming standardization across services
- Use complex PromQL workarounds instead of fixing root collection issues
- Implement dashboard solutions that don't address underlying service metrics
  gaps
- Skip validation of circuit breaker integration across all applicable
  services
- Create recording rules that aggregate non-existent or inconsistent metrics

  Critical Success Dependencies

  This task requires:

- Systematic Analysis: Complete understanding of metric collection flow from
  service → Prometheus → dashboard
- Subagent Utilization: Use subagents for comprehensive audit, validation, and
   implementation
- Architecture Focus: Address systemic issues, not just dashboard symptom
  fixes
- Evidence-Based Solutions: All changes must be based on concrete analysis of
  metric availability
- End-to-End Validation: Verify complete observability chain from service
  metrics to dashboard visualization

  ⚡ REMEMBER: THINK VERY HARD about the complete observability architecture.
  This is not just a dashboard fix - it's a comprehensive resolution of critical
   gaps in the HuleEdu observability foundation. The platform's operational
  excellence depends on getting this right.

  Files Requiring Investigation and Potential Modification

  Configuration Files

- observability/prometheus/prometheus.yml
- observability/prometheus/rules/recording_rules.yml
- observability/grafana/dashboards/HuleEdu_Service_Deep_Dive_Template.json
- observability/grafana/dashboards/HuleEdu_System_Health_Overview.json

  Service Metrics Implementations

- services/*/metrics.py (all service metrics files)
- services/*/api/*_routes.py (metrics endpoint implementations)
- services/libs/huleedu_service_libs/resilience/registry.py (circuit breaker
  metrics)

  Service Configuration

- services/*/config.py (service configuration including metrics exposure)
- services/*/di.py (dependency injection including metrics providers)

  Documentation and Rules

- .cursor/rules/071*.mdc (all observability rules)
- documentation/user_guides/grafana-dashboard-import-guide.md

  This comprehensive task ensures that the HuleEdu observability stack will
  provide reliable, actionable operational insights across all microservices
  while maintaining architectural excellence and performance.
