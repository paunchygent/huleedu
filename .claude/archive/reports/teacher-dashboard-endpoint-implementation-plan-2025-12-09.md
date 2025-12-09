# Investigation Report: Teacher Dashboard Endpoint Implementation Plan

**Date**: 2025-12-09
**Investigator**: Research/Planning Agent
**Scope**: BFF Teacher Service `/bff/v1/teacher/dashboard` endpoint

---

## 1. Investigation Summary

### 1.1. Problem Statement
Plan the implementation of the `/bff/v1/teacher/dashboard` endpoint in the BFF Teacher Service that aggregates data from RAS (Result Aggregator Service) and CMS (Class Management Service) into a screen-optimized response for the Vue 3 frontend.

### 1.2. Scope
- BFF Teacher Service (`services/bff_teacher_service/`)
- Target services: RAS, CMS
- Phases: Service clients, dashboard endpoint, tests

### 1.3. Methodology
- Analyzed existing BFF service structure
- Examined RAS and CMS API endpoints and models
- Studied existing HTTP client patterns in API Gateway
- Reviewed DI patterns with Dishka
- Verified error handling patterns for FastAPI

---

## 2. Current State Assessment

### 2.1. BFF Service Structure (Exists)

**Directory**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/bff_teacher_service/`

| File | Lines | Status |
|------|-------|--------|
| `app.py` | 168 | Complete - FastAPI app with static serving |
| `config.py` | 69 | Stub - Missing backend service URLs |
| `api/v1/teacher_routes.py` | 31 | Stub - Returns empty response |
| `dto/teacher_v1.py` | 24 | Stub - Generic dict type |
| `clients/__init__.py` | 10 | Scaffold only |

**Current Dashboard Endpoint** (`api/v1/teacher_routes.py:21-30`):
```python
@router.get("/dashboard", response_model=TeacherDashboardResponseV1)
async def get_teacher_dashboard() -> TeacherDashboardResponseV1:
    """Stub implementation returns empty dashboard."""
    return TeacherDashboardResponseV1(batches=[], total_count=0)
```

**Current DTO** (`dto/teacher_v1.py:15-24`):
```python
class TeacherDashboardResponseV1(BaseModel):
    batches: list[dict] = Field(default_factory=list)  # Needs proper type
    total_count: int = 0
```

**Missing Files**:
- `di.py` - Dishka DI providers
- `protocols.py` - Client protocols
- `clients/ras_client.py` - RAS HTTP client
- `clients/cms_client.py` - CMS HTTP client
- `tests/` - Test directory does not exist

### 2.2. RAS Endpoints Available

**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/result_aggregator_service/api/query_routes.py`

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `/internal/v1/batches/{batch_id}/status` | GET | X-Internal-API-Key, X-Service-ID | `BatchStatusResponse` |
| `/internal/v1/batches/user/{user_id}` | GET | X-Internal-API-Key, X-Service-ID | `{batches: [], pagination: {}}` |

**RAS Authentication** (lines 27-50):
- Requires `X-Internal-API-Key` header
- Requires `X-Service-ID` header
- Validates via `SecurityServiceProtocol.validate_service_credentials()`

**GET /internal/v1/batches/user/{user_id}** Query Parameters:
- `limit` (int, default 20)
- `offset` (int, default 0)
- `status` (str, optional)

**BatchStatusResponse** (`models_api.py:41-67`):
```python
class BatchStatusResponse(BaseModel):
    batch_id: str
    user_id: str
    assignment_id: Optional[str] = None
    overall_status: BatchClientStatus
    essay_count: int
    completed_essay_count: int
    failed_essay_count: int
    requested_pipeline: Optional[str] = None
    current_phase: Optional[PhaseName] = None
    essays: List[EssayResultResponse] = Field(default_factory=list)
    created_at: datetime
    last_updated: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    student_prompt_ref: Optional[Dict[str, Any]] = None
```

### 2.3. CMS Endpoints Available

**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/class_management_service/api/class_routes.py`

| Endpoint | Method | Auth | Response |
|----------|--------|------|----------|
| `/v1/classes/` | GET | X-User-ID | `{classes: [], pagination: {}}` |
| `/v1/classes/{class_id}` | GET | X-User-ID | Class details |
| `/v1/classes/{class_id}/roster` | GET | None | `{students: []}` |

**GET /v1/classes/** Query Parameters:
- `limit` (int, default 20)
- `offset` (int, default 0)

**CMS Authentication**:
- Requires `X-User-ID` header (injected by API Gateway)
- No internal API key needed for public routes

**Class Response Format** (lines 61-75):
```python
{
    "id": str(cls.id),
    "name": cls.name,
    "course_code": cls.course.course_code if cls.course else None,
    "student_count": len(cls.students),
    "created_at": cls.created_at.isoformat() if cls.created_at else None,
}
```

### 2.4. BatchClientStatus Enum

**Location**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/common_core/src/common_core/status_enums.py:135-162`

```python
class BatchClientStatus(str, Enum):
    PENDING_CONTENT = "pending_content"
    READY = "ready"
    PROCESSING = "processing"
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

---

## 3. Existing Patterns to Follow

### 3.1. HTTP Client Pattern (API Gateway)

**Protocol** (`/Users/olofs_mba/Documents/Repos/huledu-reboot/services/api_gateway_service/protocols.py:18-53`):
```python
class HttpClientProtocol(Protocol):
    async def post(self, url: str, *, data: dict | None = None, ...) -> httpx.Response: ...
    async def get(self, url: str, *, headers: dict[str, str] | None = None, ...) -> httpx.Response: ...
    async def patch(self, url: str, *, json: dict | None = None, ...) -> httpx.Response: ...
```

**Implementation** (`/Users/olofs_mba/Documents/Repos/huledu-reboot/services/api_gateway_service/implementations/http_client.py`):
- Wraps `httpx.AsyncClient`
- Returns raw `httpx.Response` objects

### 3.2. DI Provider Pattern (API Gateway)

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/api_gateway_service/app/di.py`

```python
class ApiGatewayProvider(Provider):
    scope = Scope.APP

    @provide
    def get_config(self) -> Settings:
        return settings

    @provide(scope=Scope.APP)
    async def get_http_client(self, config: Settings, ...) -> AsyncIterator[HttpClientProtocol]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(...)) as httpx_client:
            yield ApiGatewayHttpClient(httpx_client)
```

### 3.3. Error Handling Pattern (FastAPI)

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/libs/huleedu_service_libs/src/huleedu_service_libs/error_handling/fastapi_handlers.py`

```python
from huleedu_service_libs.error_handling.fastapi import register_error_handlers

# In app.py
register_error_handlers(app)
```

Already integrated in BFF app.py (line 16, 61).

### 3.4. Test Provider Pattern

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/api_gateway_service/tests/test_provider.py`

- `AuthTestProvider`: Provides mock user_id, correlation_id, org_id
- `InfrastructureTestProvider`: Provides mock HTTP client, Redis, Kafka
- Uses `respx` for HTTP mocking in tests

---

## 4. Implementation Plan

### ⚠️ Phase 0 (PRE-REQUISITE): CMS Internal Endpoint

**BLOCKING DEPENDENCY**: This endpoint must be implemented in CMS before BFF can proceed.

#### 4.0. File: `services/class_management_service/api/internal_routes.py` (UPDATE)

Add new endpoint to existing internal routes:

```python
@bp.route("/batches/class-info", methods=["GET"])
@inject
async def get_batch_class_info(
    service: FromDishka[ClassManagementServiceProtocol],
) -> Response | tuple[Response, int]:
    """Get class info for multiple batches.

    Query params:
        batch_ids: Comma-separated list of batch UUIDs

    Returns:
        {batch_id: {class_id: str, class_name: str} | null}
        Batches without class associations return null.

    Internal endpoint - requires X-Internal-API-Key header.
    """
    # Validate internal API key
    api_key = request.headers.get("X-Internal-API-Key")
    if not api_key or api_key != settings.INTERNAL_API_KEY:
        return jsonify({"error": "Unauthorized"}), 401

    batch_ids_param = request.args.get("batch_ids", "")
    if not batch_ids_param:
        return jsonify({}), 200

    batch_ids = [UUID(bid.strip()) for bid in batch_ids_param.split(",") if bid.strip()]

    # Query EssayStudentAssociation for batch→class mappings
    result = await service.get_class_info_for_batches(batch_ids)
    return jsonify(result), 200
```

#### 4.0.1. File: `services/class_management_service/protocols.py` (UPDATE)

Add to `ClassManagementServiceProtocol`:

```python
async def get_class_info_for_batches(
    self, batch_ids: list[UUID]
) -> dict[str, dict[str, str] | None]:
    """Get class info for multiple batches via EssayStudentAssociation.

    Returns dict mapping batch_id (str) to class info or None.
    """
    ...
```

#### 4.0.2. File: `services/class_management_service/implementations/class_management_service_impl.py` (UPDATE)

Add implementation:

```python
async def get_class_info_for_batches(
    self, batch_ids: list[uuid.UUID]
) -> dict[str, dict[str, str] | None]:
    """Get class info for multiple batches."""
    result: dict[str, dict[str, str] | None] = {}

    for batch_id in batch_ids:
        associations = await self.repo.get_batch_student_associations(batch_id)
        if not associations:
            result[str(batch_id)] = None
            continue

        # All associations for a batch belong to same class
        class_id = associations[0].class_id
        user_class = await self.get_class_by_id(class_id)

        if user_class:
            result[str(batch_id)] = {
                "class_id": str(class_id),
                "class_name": user_class.name,
            }
        else:
            result[str(batch_id)] = None

    return result
```

---

### Phase 3: Internal Service Clients

#### 4.1. File: `services/bff_teacher_service/protocols.py` (NEW)

```python
"""Protocol definitions for BFF Teacher Service DI."""
from typing import Protocol, Any

class RASClientProtocol(Protocol):
    async def get_batches_for_user(
        self, user_id: str, *, limit: int = 20, offset: int = 0, status: str | None = None
    ) -> list[dict[str, Any]]: ...

    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None: ...

class CMSClientProtocol(Protocol):
    async def get_batch_class_info(
        self, batch_ids: list[str]
    ) -> dict[str, dict[str, str | None]]:
        """Get class info for multiple batches.

        Args:
            batch_ids: List of batch IDs to look up

        Returns:
            Dict mapping batch_id -> {class_id: str | None, class_name: str | None}
            Batches without class associations return empty dict or None values.
        """
        ...
```

#### 4.2. File: `services/bff_teacher_service/clients/ras_client.py` (NEW)

```python
"""RAS HTTP client for BFF Teacher Service."""
from __future__ import annotations
from typing import Any
import httpx

class RASClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient, api_key: str) -> None:
        self._base_url = base_url
        self._client = client
        self._api_key = api_key
    
    def _internal_headers(self) -> dict[str, str]:
        return {
            "X-Internal-API-Key": self._api_key,
            "X-Service-ID": "bff_teacher_service",
        }
    
    async def get_batches_for_user(
        self, user_id: str, *, limit: int = 20, offset: int = 0, status: str | None = None
    ) -> list[dict[str, Any]]:
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        
        response = await self._client.get(
            f"{self._base_url}/internal/v1/batches/user/{user_id}",
            headers=self._internal_headers(),
            params=params,
        )
        response.raise_for_status()
        return response.json().get("batches", [])
    
    async def get_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        response = await self._client.get(
            f"{self._base_url}/internal/v1/batches/{batch_id}/status",
            headers=self._internal_headers(),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
```

#### 4.3. File: `services/bff_teacher_service/clients/cms_client.py` (NEW)

```python
"""CMS HTTP client for BFF Teacher Service."""
from __future__ import annotations
from typing import Any
import httpx

class CMSClient:
    def __init__(self, base_url: str, client: httpx.AsyncClient, api_key: str) -> None:
        self._base_url = base_url
        self._client = client
        self._api_key = api_key

    def _internal_headers(self) -> dict[str, str]:
        return {
            "X-Internal-API-Key": self._api_key,
            "X-Service-ID": "bff_teacher_service",
        }

    async def get_batch_class_info(
        self, batch_ids: list[str]
    ) -> dict[str, dict[str, str | None]]:
        """Get class info for multiple batches from CMS internal endpoint.

        Calls CMS internal endpoint that queries EssayStudentAssociation table.
        """
        if not batch_ids:
            return {}

        response = await self._client.get(
            f"{self._base_url}/internal/v1/batches/class-info",
            headers=self._internal_headers(),
            params={"batch_ids": ",".join(batch_ids)},
        )
        response.raise_for_status()
        return response.json()  # {batch_id: {class_id, class_name} | null}
```

#### 4.4. File: `services/bff_teacher_service/config.py` (UPDATE)

Add backend service URLs:

```python
# Add after existing fields
RAS_BASE_URL: str = Field(
    default="http://result_aggregator_service:4003",
    description="Result Aggregator Service base URL",
    validation_alias=AliasChoices("BFF_TEACHER_SERVICE_RAS_URL", "RESULT_AGGREGATOR_SERVICE_URL"),
)
CMS_BASE_URL: str = Field(
    default="http://class_management_service:5002",
    description="Class Management Service base URL",
    validation_alias=AliasChoices("BFF_TEACHER_SERVICE_CMS_URL", "CLASS_MANAGEMENT_SERVICE_URL"),
)

# HTTP client timeout
HTTP_CLIENT_TIMEOUT_SECONDS: int = Field(default=10, description="HTTP client timeout")
```

#### 4.5. File: `services/bff_teacher_service/di.py` (NEW)

```python
"""Dishka DI providers for BFF Teacher Service."""
from __future__ import annotations
from collections.abc import AsyncIterator
import httpx
from dishka import Provider, Scope, provide

from services.bff_teacher_service.config import BFFTeacherSettings, settings
from services.bff_teacher_service.protocols import RASClientProtocol, CMSClientProtocol
from services.bff_teacher_service.clients.ras_client import RASClient
from services.bff_teacher_service.clients.cms_client import CMSClient

class BFFTeacherProvider(Provider):
    scope = Scope.APP

    @provide
    def provide_settings(self) -> BFFTeacherSettings:
        return settings

    @provide(scope=Scope.APP)
    async def provide_http_client(self, config: BFFTeacherSettings) -> AsyncIterator[httpx.AsyncClient]:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(config.HTTP_CLIENT_TIMEOUT_SECONDS, connect=5.0)
        ) as client:
            yield client

    @provide(scope=Scope.APP)
    def provide_ras_client(
        self, config: BFFTeacherSettings, client: httpx.AsyncClient
    ) -> RASClientProtocol:
        return RASClient(
            base_url=config.RAS_BASE_URL,
            client=client,
            api_key=config.get_internal_api_key(),
        )

    @provide(scope=Scope.APP)
    def provide_cms_client(
        self, config: BFFTeacherSettings, client: httpx.AsyncClient
    ) -> CMSClientProtocol:
        return CMSClient(base_url=config.CMS_BASE_URL, client=client)
```

### Phase 4: Dashboard Endpoint

#### 4.6. File: `services/bff_teacher_service/dto/teacher_v1.py` (UPDATE)

```python
"""Teacher BFF v1 DTOs."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field
from common_core.status_enums import BatchClientStatus

class BatchSummaryV1(BaseModel):
    """Summary of a batch for dashboard list."""
    batch_id: str
    class_id: str | None = None
    class_name: str | None = None
    status: BatchClientStatus
    essay_count: int
    completed_essay_count: int
    failed_essay_count: int
    created_at: datetime
    last_updated: datetime
    requested_pipeline: str | None = None

class TeacherDashboardResponseV1(BaseModel):
    """Dashboard view: list of batches for teacher."""
    batches: list[BatchSummaryV1] = Field(default_factory=list)
    total_count: int = 0
```

#### 4.7. File: `services/bff_teacher_service/api/v1/teacher_routes.py` (UPDATE)

```python
"""Teacher BFF API v1 routes."""
from __future__ import annotations
import asyncio
from fastapi import APIRouter, Header
from dishka.integrations.fastapi import FromDishka
import httpx

from services.bff_teacher_service.dto.teacher_v1 import (
    TeacherDashboardResponseV1,
    BatchSummaryV1,
)
from services.bff_teacher_service.protocols import RASClientProtocol, CMSClientProtocol
from huleedu_service_libs.error_handling import raise_external_service_error

router = APIRouter()

@router.get("/dashboard", response_model=TeacherDashboardResponseV1)
async def get_teacher_dashboard(
    ras_client: FromDishka[RASClientProtocol],
    cms_client: FromDishka[CMSClientProtocol],
    x_user_id: str = Header(..., alias="X-User-ID"),
    x_correlation_id: str = Header(default="", alias="X-Correlation-ID"),
) -> TeacherDashboardResponseV1:
    """Get teacher dashboard: list of all batches with status and progress.

    Aggregates data from RAS (batch statuses) and CMS (class info via batch_id).
    """
    try:
        # Step 1: Get batches from RAS
        batches_data = await ras_client.get_batches_for_user(x_user_id, limit=50)

        # Step 2: Get batch→class mapping from CMS (new internal endpoint)
        batch_ids = [b["batch_id"] for b in batches_data]
        batch_class_map = await cms_client.get_batch_class_info(batch_ids) if batch_ids else {}

    except httpx.HTTPStatusError as e:
        raise_external_service_error(
            message=f"Backend service error: {e.response.status_code}",
            service="bff_teacher_service",
            operation="get_teacher_dashboard",
            correlation_id=x_correlation_id or None,
            details={"status_code": e.response.status_code, "service": "ras/cms"},
        )
    except Exception as e:
        raise_external_service_error(
            message=f"Failed to fetch dashboard data: {e}",
            service="bff_teacher_service",
            operation="get_teacher_dashboard",
            correlation_id=x_correlation_id or None,
        )

    # Transform batches to DTOs with class info from CMS
    batch_summaries = [
        BatchSummaryV1(
            batch_id=b["batch_id"],
            class_id=batch_class_map.get(b["batch_id"], {}).get("class_id"),
            class_name=batch_class_map.get(b["batch_id"], {}).get("class_name"),
            status=b["overall_status"],
            essay_count=b["essay_count"],
            completed_essay_count=b["completed_essay_count"],
            failed_essay_count=b["failed_essay_count"],
            created_at=b["created_at"],
            last_updated=b["last_updated"],
            requested_pipeline=b.get("requested_pipeline"),
        )
        for b in batches_data
    ]
    
    return TeacherDashboardResponseV1(
        batches=batch_summaries,
        total_count=len(batch_summaries),
    )
```

#### 4.8. File: `services/bff_teacher_service/app.py` (UPDATE)

Add Dishka setup after app creation:

```python
# Add imports at top
from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from services.bff_teacher_service.di import BFFTeacherProvider

# In create_app(), after app = FastAPI(...):
container = make_async_container(BFFTeacherProvider())
setup_dishka(container, app)
```

### Phase 6: Tests

#### 4.9. File: `services/bff_teacher_service/tests/__init__.py` (NEW)

Empty file.

#### 4.10. File: `services/bff_teacher_service/tests/unit/__init__.py` (NEW)

Empty file.

#### 4.11. File: `services/bff_teacher_service/tests/unit/test_dashboard_endpoint.py` (NEW)

```python
"""Unit tests for teacher dashboard endpoint."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, UTC

from services.bff_teacher_service.api.v1.teacher_routes import get_teacher_dashboard
from services.bff_teacher_service.dto.teacher_v1 import TeacherDashboardResponseV1
from common_core.status_enums import BatchClientStatus

@pytest.mark.asyncio
async def test_dashboard_returns_batches_with_class_info():
    """Test dashboard returns batches with class name from CMS batch→class mapping."""
    mock_ras = AsyncMock()
    mock_ras.get_batches_for_user.return_value = [
        {
            "batch_id": "batch-123",
            "overall_status": BatchClientStatus.PROCESSING,
            "essay_count": 10,
            "completed_essay_count": 5,
            "failed_essay_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
            "requested_pipeline": "spell_cj",
        }
    ]

    mock_cms = AsyncMock()
    mock_cms.get_batch_class_info.return_value = {
        "batch-123": {"class_id": "class-456", "class_name": "English 5A"},
    }

    result = await get_teacher_dashboard(
        ras_client=mock_ras,
        cms_client=mock_cms,
        x_user_id="teacher-789",
        x_correlation_id="corr-001",
    )

    assert isinstance(result, TeacherDashboardResponseV1)
    assert result.total_count == 1
    assert result.batches[0].batch_id == "batch-123"
    assert result.batches[0].class_id == "class-456"
    assert result.batches[0].class_name == "English 5A"
    assert result.batches[0].status == BatchClientStatus.PROCESSING

@pytest.mark.asyncio
async def test_dashboard_empty_when_no_batches():
    """Test dashboard returns empty list when user has no batches."""
    mock_ras = AsyncMock()
    mock_ras.get_batches_for_user.return_value = []

    mock_cms = AsyncMock()

    result = await get_teacher_dashboard(
        ras_client=mock_ras,
        cms_client=mock_cms,
        x_user_id="new-teacher",
        x_correlation_id="",
    )

    assert result.total_count == 0
    assert result.batches == []

@pytest.mark.asyncio
async def test_dashboard_batch_without_class_association():
    """Test dashboard handles batches that have no class association (valid state)."""
    mock_ras = AsyncMock()
    mock_ras.get_batches_for_user.return_value = [
        {
            "batch_id": "batch-standalone",
            "overall_status": BatchClientStatus.COMPLETED_SUCCESSFULLY,
            "essay_count": 5,
            "completed_essay_count": 5,
            "failed_essay_count": 0,
            "created_at": datetime.now(UTC).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
        }
    ]

    mock_cms = AsyncMock()
    mock_cms.get_batch_class_info.return_value = {}

    result = await get_teacher_dashboard(
        ras_client=mock_ras,
        cms_client=mock_cms,
        x_user_id="teacher-123",
        x_correlation_id="",
    )

    assert result.total_count == 1
    assert result.batches[0].batch_id == "batch-standalone"
    assert result.batches[0].class_id is None
    assert result.batches[0].class_name is None
```

#### 4.12. File: `services/bff_teacher_service/tests/unit/test_ras_client.py` (NEW)

```python
"""Unit tests for RAS client."""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

from services.bff_teacher_service.clients.ras_client import RASClient

@pytest.mark.asyncio
async def test_get_batches_sends_internal_auth_headers():
    """Test that internal API key headers are sent."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"batches": []}
    mock_client.get.return_value = mock_response
    
    client = RASClient(
        base_url="http://ras:4003",
        client=mock_client,
        api_key="test-api-key",
    )
    
    await client.get_batches_for_user("user-123")
    
    mock_client.get.assert_called_once()
    call_kwargs = mock_client.get.call_args.kwargs
    assert call_kwargs["headers"]["X-Internal-API-Key"] == "test-api-key"
    assert call_kwargs["headers"]["X-Service-ID"] == "bff_teacher_service"
```

---

## 5. File-by-File Implementation Order

### Phase 0: CMS Internal Endpoint (BLOCKING PRE-REQUISITE)

| # | File | Action | Dependencies |
|---|------|--------|--------------|
| 0.1 | `services/class_management_service/protocols.py` | UPDATE | None |
| 0.2 | `services/class_management_service/implementations/class_management_service_impl.py` | UPDATE | protocols |
| 0.3 | `services/class_management_service/api/internal_routes.py` | UPDATE | impl |
| 0.4 | `services/class_management_service/tests/unit/test_batch_class_info.py` | CREATE | None |

### Phase 3-6: BFF Service Implementation

| # | File | Action | Dependencies |
|---|------|--------|--------------|
| 1 | `services/bff_teacher_service/config.py` | UPDATE | None |
| 2 | `services/bff_teacher_service/protocols.py` | CREATE | None |
| 3 | `services/bff_teacher_service/clients/ras_client.py` | CREATE | protocols.py |
| 4 | `services/bff_teacher_service/clients/cms_client.py` | CREATE | protocols.py |
| 5 | `services/bff_teacher_service/clients/__init__.py` | UPDATE | ras_client, cms_client |
| 6 | `services/bff_teacher_service/di.py` | CREATE | config, clients |
| 7 | `services/bff_teacher_service/dto/teacher_v1.py` | UPDATE | common_core |
| 8 | `services/bff_teacher_service/api/v1/teacher_routes.py` | UPDATE | protocols, dto |
| 9 | `services/bff_teacher_service/app.py` | UPDATE | di.py |
| 10 | `services/bff_teacher_service/tests/__init__.py` | CREATE | None |
| 11 | `services/bff_teacher_service/tests/unit/__init__.py` | CREATE | None |
| 12 | `services/bff_teacher_service/tests/unit/test_dashboard_endpoint.py` | CREATE | dto, routes |
| 13 | `services/bff_teacher_service/tests/unit/test_ras_client.py` | CREATE | clients |

---

## 6. Risks and Questions

### 6.1. INTERNAL_API_KEY Access

**Issue**: BFF config extends `SecureServiceSettings` which provides `get_internal_api_key()` via `HULEEDU_INTERNAL_API_KEY` env var.

**Status**: VERIFIED - Method available in base class (`secure_base.py:96-97`)

**Action**: Ensure `HULEEDU_INTERNAL_API_KEY` is set in `docker-compose.services.yml` for `bff_teacher_service`.

### 6.2. Batch→Class Association

**Architecture**:
- `assignment_id` in RAS links to assessment instructions/prompts (separate domain)
- Batch→Class relationship exists in CMS via `EssayStudentAssociation` table
- Query: `SELECT DISTINCT class_id FROM essay_student_associations WHERE batch_id = ?`

**Implementation**:
- CMS internal endpoint: `GET /internal/v1/batches/class-info?batch_ids=...`
- Response: `{batch_id: {class_id: uuid, class_name: str} | null}`
- Batches without class associations return `null` (valid state)

### 6.3. Missing Tests Directory

**Issue**: `services/bff_teacher_service/tests/` does not exist.

**Action**: Create directory structure as part of implementation.

### 6.4. Dishka FastAPI Integration

**Pattern Verified**: API Gateway uses `setup_dishka(container, app)` with `FromDishka[]` in route parameters.

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/api_gateway_service/tests/test_bff_teacher_routes.py:64-66`

### 6.5. Required Endpoints Status

| Endpoint | Status | Notes |
|----------|--------|-------|
| RAS: `GET /internal/v1/batches/user/{user_id}` | ✅ EXISTS | Returns batch list |
| CMS: `GET /internal/v1/batches/class-info` | ❌ REQUIRED | **Must implement** - batch→class mapping |
| CMS: `GET /v1/classes/` | ✅ EXISTS | Not needed for dashboard (use class-info endpoint instead) |

**BLOCKING**: CMS internal endpoint for batch→class mapping must be implemented first

---

## 7. Docker Compose Updates Needed

Add to `docker-compose.services.yml` under `bff_teacher_service.environment`:

```yaml
- RESULT_AGGREGATOR_SERVICE_URL=http://result_aggregator_service:4003
- CLASS_MANAGEMENT_SERVICE_URL=http://class_management_service:5002
- HULEEDU_INTERNAL_API_KEY=${HULEEDU_INTERNAL_API_KEY}
```

---

## 8. Validation Commands

After implementation:

```bash
# Type checking
pdm run typecheck-all

# Linting
pdm run format-all && pdm run lint-fix --unsafe-fixes

# Unit tests
pdm run pytest-root services/bff_teacher_service/tests/unit/ -v

# Manual test (with dev stack running)
curl -H "X-User-ID: test-user" http://localhost:8080/bff/v1/teacher/dashboard
```

---

## 9. Recommended Next Steps

1. **Immediate**: Implement Phase 3 (clients) and Phase 4 (endpoint) following this plan
2. **Required**: Add unit tests (Phase 6)
3. **Optional**: Add integration tests with testcontainers
4. **Future**: Implement batch detail endpoint (`/bff/v1/teacher/batches/{batch_id}`)

---

## 10. Related Documentation

- **Rule**: `.claude/rules/020.21-bff-teacher-service.md`
- **Task**: `frontend/TASKS/integration/bff-service-implementation-plan.md`
- **ADR**: `docs/decisions/0007-bff-vs-api-gateway-pattern.md`
- **Handoff**: `frontend/.claude/work/session/handoff.md`
