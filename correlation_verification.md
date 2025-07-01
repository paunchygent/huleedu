# Correlation ID Refactoring Verification Report

## Summary

- Files with issues: 13
- Total issues found: 19

## Issues by Type

- none_default: 17
- none_comparison: 2

## Detailed Findings

### services/batch_orchestrator_service/implementations/pipeline_phase_coordinator_impl.py

⚠️  correlation_id assigned None:
  - Line 52: `correlation_id: str,`
  - Line 118: `logger.info(message, extra={"correlation_id": correlation_id})`
  - Line 427: `extra={"correlation_id": correlation_id},`

### services/batch_orchestrator_service/protocols.py

⚠️  correlation_id assigned None:
  - Line 57: `correlation_id: uuid.UUID,`
  - Line 178: `correlation_id: uuid.UUID,`
  - Line 212: `correlation_id: str,`

### services/cj_assessment_service/event_processor.py

⚠️  correlation_id assigned None:
  - Line 81: `"correlation_id": str(envelope.correlation_id),`

### services/cj_assessment_service/protocols.py

⚠️  correlation_id assigned None:
  - Line 111: `event_correlation_id: str,`

### services/essay_lifecycle_service/core_logic.py

⚠️  correlation_id assigned None:
  - Line 15: `def generate_correlation_id() -> UUID:`

### services/essay_lifecycle_service/implementations/service_result_handler_impl.py

⚠️  correlation_id assigned None:
  - Line 121: `"correlation_id": str(correlation_id),`

### services/essay_lifecycle_service/protocols.py

⚠️  correlation_id assigned None:
  - Line 108: `self, essay_ref: EntityReference, status: EssayStatus, correlation_id: UUID`

### services/essay_lifecycle_service/tests/unit/test_cj_assessment_command_handler.py

⚠️  correlation_id assigned None:
  - Line 223: `command_data=cj_assessment_command_data, correlation_id=correlation_id`

### services/essay_lifecycle_service/tests/unit/test_spellcheck_command_handler.py

⚠️  correlation_id assigned None:
  - Line 216: `command_data=spellcheck_command_data, correlation_id=correlation_id`

### services/file_service/core_logic.py

⚠️  correlation_id assigned None:
  - Line 35: `main_correlation_id: uuid.UUID,`

### services/libs/huleedu_service_libs/error_handling/context_manager.py

⚠️  correlation_id assigned None:
  - Line 104: `correlation_id: str,`

### services/libs/huleedu_service_libs/middleware/frameworks/quart_middleware.py

⚠️  Checking if correlation_id is None:
  - Line 55: `if not correlation_id and hasattr(g, "request_id"):`
  - Line 59: `if not correlation_id:`

### services/spell_checker_service/event_processor.py

⚠️  correlation_id assigned None:
  - Line 76: `"correlation_id": str(request_envelope.correlation_id),`
  - Line 171: `extra={"correlation_id": str(request_envelope.correlation_id)},`

## Recommendations

2. Replace correlation_id=None with correlation_id=uuid4()
3. Remove None checks for correlation_id

## Missing UUID Imports

services/batch_orchestrator_service/models_db.py:
  - Missing imports: UUID

services/cj_assessment_service/models_db.py:
  - Missing imports: UUID

services/cj_assessment_service/tests/test_event_processor_overrides.py:
  - Missing imports: UUID

services/libs/huleedu_service_libs/event_utils.py:
  - Missing imports: UUID
