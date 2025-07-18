# Task: Clean Architectural Refactoring - Remove BOS Fallback from API Gateway

## Objective
Remove the Batch Orchestrator Service (BOS) fallback logic from the API Gateway and move it to the Result Aggregator Service where it belongs. The API Gateway should be a dumb proxy with no knowledge of service internals.

## Current Anti-Pattern
The API Gateway currently contains complex fallback logic that violates architectural boundaries:
- Lines 89-139 in `status_routes.py` implement BOS fallback when Result Aggregator returns 404
- API Gateway knows about BOS URL and internal data structures
- API Gateway performs data transformation from BOS format to RAS format
- This creates tight coupling and violates the principle of service encapsulation

## Target Architecture
- **API Gateway**: Simple proxy that forwards requests and enforces authentication/ownership
- **Result Aggregator Service**: Handles ALL consistency logic internally, including BOS fallback

## Implementation Plan

### Phase 1: Add BOS Client to Result Aggregator Service

#### 1.1 Update Result Aggregator Config
```python
# services/result_aggregator_service/config.py
# Add after line 82 (CACHE_ENABLED)

    # Service Dependencies
    BOS_URL: str = Field(
        default="http://batch_orchestrator_service:8000",
        description="Batch Orchestrator Service URL for fallback queries"
    )
    BOS_TIMEOUT_SECONDS: int = Field(
        default=10,
        description="Timeout for BOS queries"
    )
```

#### 1.2 Create BOS Client Protocol
```python
# services/result_aggregator_service/protocols.py
# Add after CacheManagerProtocol (line 184)

class BatchOrchestratorClientProtocol(Protocol):
    """Protocol for communicating with Batch Orchestrator Service."""

    async def get_pipeline_state(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline state from BOS for a batch."""
        ...
```

#### 1.3 Implement BOS Client
Create new file: `services/result_aggregator_service/implementations/bos_client_impl.py`
```python
"""Batch Orchestrator Service client implementation."""

from __future__ import annotations

from typing import Any, Dict, Optional

from httpx import AsyncClient, HTTPStatusError
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.protocols import BatchOrchestratorClientProtocol

logger = create_service_logger("result_aggregator.bos_client")


class BatchOrchestratorClientImpl(BatchOrchestratorClientProtocol):
    """HTTP client for Batch Orchestrator Service."""

    def __init__(self, http_client: AsyncClient, settings: Settings):
        """Initialize the BOS client."""
        self.http_client = http_client
        self.settings = settings

    async def get_pipeline_state(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline state from BOS for a batch."""
        try:
            url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"
            response = await self.http_client.get(url, timeout=self.settings.BOS_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug(f"Batch {batch_id} not found in BOS")
                return None
            logger.error(f"BOS query failed for batch {batch_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error querying BOS for batch {batch_id}: {e}")
            raise
```

#### 1.4 Create BOS Data Transformer
Create new file: `services/result_aggregator_service/implementations/bos_data_transformer.py`
```python
"""Transform BOS pipeline state to Result Aggregator format."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from common_core.pipeline_models import PhaseName, PipelineExecutionStatus
from common_core.status_enums import BatchClientStatus, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.models_db import BatchResult, EssayResult

logger = create_service_logger("result_aggregator.bos_transformer")


def transform_bos_to_batch_result(bos_data: Dict[str, Any]) -> BatchResult:
    """Transform BOS pipeline state to BatchResult model."""
    pipeline_state = bos_data.get("pipeline_state", {})
    user_id = bos_data.get("user_id", "unknown")
    batch_id = bos_data.get("batch_id")
    
    # Extract pipeline states
    pipeline_states = _extract_pipeline_states(pipeline_state)
    
    # Derive status
    overall_status = _derive_batch_status(pipeline_states)
    
    # Calculate essay counts
    primary_pipeline = pipeline_states[0] if pipeline_states else {}
    essay_counts = primary_pipeline.get("essay_counts", {})
    
    # Create BatchResult (note: we can't populate essays from BOS data)
    return BatchResult(
        id=uuid4(),  # Generate a temporary ID
        batch_id=batch_id,
        user_id=user_id,
        overall_status=overall_status,
        essay_count=essay_counts.get("total", 0),
        completed_essay_count=_sum_successful_essays(pipeline_states),
        failed_essay_count=_sum_failed_essays(pipeline_states),
        requested_pipeline=",".join(pipeline_state.get("requested_pipelines", [])),
        current_phase=_derive_current_phase(pipeline_states),
        essays=[],  # Cannot populate from BOS - no individual essay data
        created_at=datetime.utcnow(),  # Not available from BOS
        last_updated=pipeline_state.get("last_updated", datetime.utcnow()),
        processing_started_at=_get_earliest_start_time(pipeline_states),
        processing_completed_at=_get_latest_completion_time(pipeline_states),
    )


def _extract_pipeline_states(pipeline_state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract valid pipeline states from BOS data."""
    pipeline_names = [
        PhaseName.SPELLCHECK.value,
        "nlp_metrics",  # BOS uses different naming
        PhaseName.AI_FEEDBACK.value,
        PhaseName.CJ_ASSESSMENT.value,
    ]
    states = []
    for name in pipeline_names:
        if name in pipeline_state and pipeline_state[name] is not None:
            states.append(pipeline_state[name])
    return states


def _derive_batch_status(pipeline_states: List[Dict[str, Any]]) -> str:
    """Derive BatchClientStatus from pipeline execution states."""
    in_progress_statuses = {
        PipelineExecutionStatus.DISPATCH_INITIATED.value,
        PipelineExecutionStatus.IN_PROGRESS.value,
        PipelineExecutionStatus.PENDING_DEPENDENCIES.value,
    }
    completed_statuses = {
        PipelineExecutionStatus.COMPLETED_SUCCESSFULLY.value,
        PipelineExecutionStatus.COMPLETED_WITH_PARTIAL_SUCCESS.value,
    }
    failed_statuses = {
        PipelineExecutionStatus.FAILED.value,
        PipelineExecutionStatus.CANCELLED.value,
    }
    
    statuses = [state.get("status") for state in pipeline_states]
    
    if any(status in in_progress_statuses for status in statuses):
        return BatchClientStatus.PROCESSING.value
    elif any(status in failed_statuses for status in statuses):
        # Note: BatchClientStatus doesn't have FAILED, using "FAILED" string
        return "FAILED"
    elif all(status in completed_statuses for status in statuses):
        return BatchClientStatus.AVAILABLE.value
    else:
        return BatchClientStatus.PROCESSING.value


def _derive_current_phase(pipeline_states: List[Dict[str, Any]]) -> Optional[str]:
    """Determine current processing phase from pipeline states."""
    phase_mapping = {
        0: PhaseName.SPELLCHECK,
        1: "nlp_metrics",
        2: PhaseName.AI_FEEDBACK,
        3: PhaseName.CJ_ASSESSMENT,
    }
    
    active_statuses = {
        PipelineExecutionStatus.DISPATCH_INITIATED.value,
        PipelineExecutionStatus.IN_PROGRESS.value,
    }
    
    for idx, state in enumerate(pipeline_states):
        if state.get("status") in active_statuses:
            phase = phase_mapping.get(idx)
            if isinstance(phase, PhaseName):
                return phase.value.upper()
            elif isinstance(phase, str):
                return phase.upper()
    
    return None


def _sum_successful_essays(pipeline_states: List[Dict[str, Any]]) -> int:
    """Sum successful essays across all pipelines."""
    return sum(state.get("essay_counts", {}).get("successful", 0) for state in pipeline_states)


def _sum_failed_essays(pipeline_states: List[Dict[str, Any]]) -> int:
    """Sum failed essays across all pipelines."""
    return sum(state.get("essay_counts", {}).get("failed", 0) for state in pipeline_states)


def _get_earliest_start_time(pipeline_states: List[Dict[str, Any]]) -> Optional[datetime]:
    """Extract earliest start time across pipelines."""
    start_times = []
    for state in pipeline_states:
        start_time = state.get("started_at")
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(start_time, datetime):
            start_times.append(start_time)
    return min(start_times) if start_times else None


def _get_latest_completion_time(pipeline_states: List[Dict[str, Any]]) -> Optional[datetime]:
    """Extract latest completion time across pipelines."""
    completion_times = []
    for state in pipeline_states:
        completion_time = state.get("completed_at")
        if isinstance(completion_time, str):
            try:
                completion_time = datetime.fromisoformat(completion_time.replace("Z", "+00:00"))
            except ValueError:
                continue
        if isinstance(completion_time, datetime):
            completion_times.append(completion_time)
    return max(completion_times) if completion_times else None
```

#### 1.5 Update AggregatorServiceImpl to Use BOS Fallback
Replace the entire `get_batch_status` method in `services/result_aggregator_service/implementations/aggregator_service_impl.py`:
```python
    async def get_batch_status(self, batch_id: str) -> Optional[BatchResult]:
        """Get comprehensive batch status with BOS fallback."""
        try:
            # First try to get from our database
            result = await self.batch_repository.get_batch(batch_id)
            
            if result:
                return result
            
            # If not found locally, check BOS
            logger.info(f"Batch {batch_id} not found locally, checking BOS")
            
            if not hasattr(self, 'bos_client'):
                # If no BOS client injected, return None (maintains backward compatibility)
                return None
                
            bos_data = await self.bos_client.get_pipeline_state(batch_id)
            
            if not bos_data:
                return None
            
            # Transform BOS data to our format
            from services.result_aggregator_service.implementations.bos_data_transformer import (
                transform_bos_to_batch_result
            )
            
            return transform_bos_to_batch_result(bos_data)

        except Exception as e:
            logger.error(
                "Failed to get batch status",
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise
```

Also update the `__init__` method to accept the BOS client:
```python
    def __init__(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        settings: Settings,
        bos_client: Optional[BatchOrchestratorClientProtocol] = None,
    ):
        """Initialize the service."""
        self.batch_repository = batch_repository
        self.cache_manager = cache_manager
        self.settings = settings
        self.bos_client = bos_client
```

#### 1.6 Update Result Aggregator models_db.py
Add a status constant to `services/result_aggregator_service/models_db.py` if not already present:
```python
# Add to imports
from common_core.status_enums import BatchClientStatus

# Ensure BatchResult.overall_status can handle FAILED status
# The field should already support this via the String type
```

#### 1.7 Update DI Configuration
Update `services/result_aggregator_service/di.py` to include the BOS client:

Add imports:
```python
from typing import Optional
from httpx import AsyncClient
from services.result_aggregator_service.implementations.bos_client_impl import BatchOrchestratorClientImpl
from services.result_aggregator_service.protocols import BatchOrchestratorClientProtocol
```

Add to the provider class:
```python
    @provide(scope=Scope.APP)
    def provide_http_client(self) -> AsyncClient:
        """Provide HTTP client for external service calls."""
        return AsyncClient()
    
    @provide(scope=Scope.APP)
    def provide_bos_client(
        self, http_client: AsyncClient, settings: Settings
    ) -> BatchOrchestratorClientProtocol:
        """Provide BOS client implementation."""
        return BatchOrchestratorClientImpl(http_client, settings)
```

Update the `provide_aggregator_service` method to include the BOS client:
```python
    @provide(scope=Scope.REQUEST)
    def provide_aggregator_service(
        self,
        batch_repository: BatchRepositoryProtocol,
        cache_manager: CacheManagerProtocol,
        settings: Settings,
        bos_client: BatchOrchestratorClientProtocol,
    ) -> BatchQueryServiceProtocol:
        """Provide aggregator service implementation."""
        return AggregatorServiceImpl(batch_repository, cache_manager, settings, bos_client)
```

### Phase 2: Clean Up API Gateway

#### 2.1 Remove BOS Configuration
Remove from `services/api_gateway_service/config.py`:
- Lines 76-79: `BOS_URL` field
- Lines 80-83: `HANDLE_MISSING_BATCHES` field

#### 2.2 Simplify Status Route
Replace the entire `get_batch_status` function in `services/api_gateway_service/routers/status_routes.py` (lines 29-159):
```python
@router.get("/batches/{batch_id}/status", response_model=BatchStatusResponse)
async def get_batch_status(
    request: Request,
    batch_id: str,
    http_client: FromDishka[AsyncClient],
    metrics: FromDishka[GatewayMetrics],
    user_id: str = Depends(auth.get_current_user_id),
):
    """Get batch status - simple proxy to Result Aggregator Service."""
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
    endpoint = f"/batches/{batch_id}/status"

    logger.info(
        f"Batch status request: batch_id='{batch_id}', user_id='{user_id}', correlation_id='{correlation_id}'"
    )

    with metrics.http_request_duration_seconds.labels(method="GET", endpoint=endpoint).time():
        try:
            # Simple proxy to Result Aggregator
            aggregator_url = (
                f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{batch_id}/status"
            )

            # Time the downstream service call
            with metrics.downstream_service_call_duration_seconds.labels(
                service="result_aggregator", method="GET", endpoint="/internal/v1/batches/status"
            ).time():
                response = await http_client.get(aggregator_url)
                response.raise_for_status()
                data = response.json()

            # Record downstream service call
            metrics.downstream_service_calls_total.labels(
                service="result_aggregator",
                method="GET",
                endpoint="/internal/v1/batches/status",
                status_code=str(response.status_code),
            ).inc()

            # Enforce ownership check
            if data.get("user_id") != user_id:
                logger.warning(
                    f"Ownership violation: batch '{batch_id}' does not belong to user '{user_id}'."
                )
                metrics.http_requests_total.labels(
                    method="GET", endpoint=endpoint, http_status="403"
                ).inc()
                metrics.api_errors_total.labels(endpoint=endpoint, error_type="access_denied").inc()
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

            # Remove internal user_id from client response
            data.pop("user_id", None)
            
            # Extract status from data - Result Aggregator should provide it
            client_status = data.get("overall_status", BatchClientStatus.PROCESSING.value)
            
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="200"
            ).inc()
            return BatchStatusResponse(status=client_status, details=data)

        except HTTPException:
            # Re-raise HTTPException without catching it
            raise
        except HTTPStatusError as e:
            # Handle all HTTP errors uniformly
            logger.error(f"Aggregator service error for batch {batch_id}: {e}")
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status=str(e.response.status_code)
            ).inc()
            metrics.api_errors_total.labels(
                endpoint=endpoint, error_type="downstream_service_error"
            ).inc()
            raise HTTPException(status_code=e.response.status_code, detail=e.response.text) from e

        except Exception as e:
            logger.error(f"Unexpected error for batch {batch_id}: {e}", exc_info=True)
            metrics.http_requests_total.labels(
                method="GET", endpoint=endpoint, http_status="500"
            ).inc()
            metrics.api_errors_total.labels(endpoint=endpoint, error_type="internal_error").inc()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error"
            ) from e
```

#### 2.3 Remove ACL Transformer
Delete the entire file: `services/api_gateway_service/acl_transformers.py`

Remove the import from `status_routes.py` (line 15):
```python
# Remove this line:
from ..acl_transformers import transform_bos_state_to_ras_response
```

#### 2.4 Update README
Update `services/api_gateway_service/README.md`:
- Line 82: Remove reference to "ACL Transformation: Converts BOS `ProcessingPipelineState` to RAS `BatchStatusResponse` during fallback"
- Line 29: Update to remove "ACL transformation" mention
- Line 22: Remove "Anti-Corruption Layer" from features list

#### 2.5 Update Tests
Update `services/api_gateway_service/tests/test_status_routes.py`:
- Remove all tests related to BOS fallback behavior
- Remove `test_get_batch_status_fallback_to_bos_success`
- Remove `test_get_batch_status_fallback_to_bos_forbidden`
- Remove `test_get_batch_status_both_services_return_404`
- Update remaining tests to expect simple proxy behavior

Delete the entire file: `services/api_gateway_service/tests/test_acl_transformers.py`

#### 2.6 Summary of All Files to Modify in API Gateway

**Files to Delete:**
- `services/api_gateway_service/acl_transformers.py`
- `services/api_gateway_service/tests/test_acl_transformers.py`

**Files to Modify:**
- `services/api_gateway_service/config.py` - Remove BOS_URL and HANDLE_MISSING_BATCHES
- `services/api_gateway_service/routers/status_routes.py` - Remove import and simplify function
- `services/api_gateway_service/tests/test_status_routes.py` - Remove BOS-related tests
- `services/api_gateway_service/README.md` - Remove ACL transformation references

### Phase 3: Testing Plan

1. **Unit Tests for Result Aggregator**:
   - Test BOS client implementation
   - Test data transformation logic
   - Test fallback behavior in AggregatorServiceImpl

2. **Integration Tests**:
   - Test Result Aggregator returns consistent responses whether data is local or from BOS
   - Test API Gateway correctly proxies requests without any BOS knowledge

3. **End-to-End Tests**:
   - Verify batch status queries work correctly through the full stack
   - Verify ownership enforcement still works

## Benefits of This Refactoring

1. **Clean Architecture**: Each service has clear, well-defined responsibilities
2. **Reduced Coupling**: API Gateway no longer knows about BOS internals
3. **Simplified Gateway**: API Gateway code is much simpler and easier to maintain
4. **Single Responsibility**: Result Aggregator is the single source of truth for batch status
5. **Better Testability**: Each component can be tested in isolation

## Rollback Plan

If issues are discovered, the changes can be reverted by:
1. Restoring the original API Gateway files
2. Removing the BOS client from Result Aggregator Service
3. No data migration or compatibility layer needed - this is a clean cut

## Success Criteria

- API Gateway has NO references to BOS
- Result Aggregator handles all batch status queries internally
- All existing batch status queries continue to work
- Ownership enforcement remains intact
- No performance degradation