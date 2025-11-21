---
id: unscoped-items
title: Unscoped Items
type: task
status: archived
priority: low
domain: architecture
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: ''
owner: ''
program: ''
related: []
labels: []
---

# TODO report – UNSCOPED

Generated: 2025-11-14 18:51:21 UTC

| File | Line | Note |
| --- | --- | --- |
| `scripts/tests/test_eng5_np_assignment_preflight.py` | 31 | implement using HTTP client mocking (e.g., responses or httpx_mock) |
| `services/batch_orchestrator_service/di.py` | 227 | Note: In production, this would be registered with the app lifecycle |
| `services/batch_orchestrator_service/implementations/ai_feedback_initiator_impl.py` | 125 | Command will be queued until AI Feedback Service is implemented |
| `services/batch_orchestrator_service/implementations/batch_validation_errors_handler.py` | 151 | Emit metrics for monitoring |
| `services/batch_orchestrator_service/implementations/essay_lifecycle_client_impl.py` | 30 | Implement actual HTTP call to ELS API |
| `services/batch_orchestrator_service/implementations/essay_lifecycle_client_impl.py` | 52 | Implement actual HTTP call to ELS API |
| `services/batch_orchestrator_service/implementations/essay_lifecycle_client_impl.py` | 74 | Implement actual HTTP call to Essay Lifecycle Service |
| `services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py` | 578 | Track actual essay-level success/failure counts from ELSBatchPhaseOutcomeV1 |
| `services/batch_orchestrator_service/kafka_consumer.py` | 93 | Add subscription to ExcessContentProvisionedV1 topic for handling |
| `services/cj_assessment_service/kafka_consumer.py` | 24 | To be implemented by Agent Beta |
| `services/entitlements_service/api/admin_routes.py` | 452 | In Phase 2, inject RateLimiterProtocol directly |
| `services/entitlements_service/api/entitlements_routes.py` | 285 | Get org_id from user context/token |
| `services/essay_lifecycle_service/implementations/service_request_dispatcher.py` | 277 | Implement when AI Feedback Service is available |
| `services/file_service/di.py` | 129 | Note: In production, this would be registered with the app lifecycle |
| `services/identity_service/domain_handlers/authentication_handler.py` | 376 | When email service is implemented, E2E tests can verify real email delivery |
| `services/llm_provider_service/TODO_COST_TRACKING.md` | 1 | (no description) |
| `services/llm_provider_service/TODO_COST_TRACKING.md` | 14 | Implement Cost Tracking Event Publishing |
| `services/llm_provider_service/TODO_COST_TRACKING.md` | 129 | Add Cost Tracking Consumer |
| `services/llm_provider_service/implementations/resilient_queue_manager_impl.py` | 289 | This is a simple cleanup - in production might want more sophisticated tracking |
| `services/result_aggregator_service/implementations/state_store_redis_impl.py` | 76 | Consider adding user_id to batch events or maintaining a batch->user mapping |
| `services/spellchecker_service/startup_setup.py` | 77 | Add additional service initialization here |
| `services/spellchecker_service/startup_setup.py` | 92 | Add cleanup logic here |
| `services/spellchecker_service/tests/test_event_router.py` | 8 | ARCHITECTURAL REFACTOR - This test file (455 lines) will be split to align |
| `services/spellchecker_service/tests/test_event_router.py` | 9 | with 'event_router.py' refactoring. Per HULEDU-ARCH-001, tests will be reorganized into: |
| `services/spellchecker_service/tests/test_event_router.py` | 10 | test_event_processor.py (for message processing logic) |
| `services/spellchecker_service/tests/test_event_router.py` | 11 | test_protocol_implementations/ (for individual protocol implementation tests) |
| `tests/functional/test_service_health.py` | 63 | Add container integration tests |
| `tests/functional/test_service_health.py` | 64 | Add end-to-end workflow tests |
| `tests/functional/test_service_health.py` | 65 | Add service dependency validation |
