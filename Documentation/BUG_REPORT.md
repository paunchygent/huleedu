# Known Bugs Summary

This document lists currently observed bugs in the repository.

## 1. Missing `from __future__ import annotations` ✅ RESOLVED
Several service entry modules do not include the mandatory future import specified in the project coding standards:

- ✅ `services/content_service/app.py` - FIXED
- ✅ `services/batch_orchestrator_service/app.py` - FIXED
- ✅ `services/content_service/hypercorn_config.py` - FIXED
- ✅ `services/libs/huleedu_service_libs/kafka_client.py` - FIXED

**Resolution**: Added `from __future__ import annotations` as the first import statement in all affected files.

## 2. Outdated test fixture parameter ✅ RESOLVED
`tests/integration/test_pipeline_state_management.py` instantiated `DefaultPipelinePhaseCoordinator` using a `cj_initiator` argument, but the class constructor expects `phase_initiators_map` instead.

**Resolution**: 
- Updated test fixture to use `phase_initiators_map: dict[PhaseName, PipelinePhaseInitiatorProtocol]`
- Fixed all test methods to use new `initiate_phase` interface
- Corrected test data setup with proper `requested_pipelines` fields
- Updated status assertions to match implementation (`COMPLETED_SUCCESSFULLY`)

## 3. Integration tests fail due to missing Kafka service ✅ RESOLVED
Running `pdm run test-all` triggered multiple errors like:
```
ERROR    tests.functional.test_walking_skeleton_e2e_v2:test_walking_skeleton_e2e_v2.py:98 Error collecting events: KafkaConnectionError: Unable to bootstrap from [('localhost', 9093, <AddressFamily.AF_UNSPEC: 0>)]
```

**Resolution**: 
- Kafka broker is now healthy and accessible at `localhost:9092-9093`
- All topics are properly created and available
- Integration tests can now connect to Kafka successfully

## Infrastructure Requirements for Tests

### Docker Compose Services
To run full integration and functional tests, ensure Docker Compose services are running:

```bash
# Clean up and rebuild containers
docker compose down --remove-orphans
docker compose build --no-cache
docker compose up -d

# Verify Kafka connectivity
docker compose exec kafka /opt/bitnami/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092

# Check service health
curl http://localhost:8001/healthz  # Content Service
curl http://localhost:9095/healthz  # CJ Assessment Service  
```

### Service Health Status
- ✅ Kafka: Healthy and accessible
- ✅ Content Service: Healthy  
- ✅ CJ Assessment Service: Healthy
- ✅ File Service: Healthy
- ✅ Spell Checker Service: Running
- ⚠️ Essay Lifecycle API: Has unrelated import issue with `EssayStateStore`

## Status Summary
All three original bug report issues have been successfully resolved:
1. ✅ Python coding standards compliance (future imports)
2. ✅ Test constructor parameter compatibility  
3. ✅ Kafka infrastructure availability
