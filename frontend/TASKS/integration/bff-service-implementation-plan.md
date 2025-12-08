---
id: bff-service-implementation-plan
title: BFF-Teacher Service Implementation Plan
type: task
status: research
priority: high
domain: integration
service: bff_teacher_service
owner_team: frontend
owner: ""
program: ""
created: 2025-11-24
last_updated: 2025-11-24
related: []
labels: []
---
 
 BFF-Teacher Service Implementation Plan
 
 Based on the BFF Frontend Integration architecture spec (`docs/architecture/bff-frontend-integration.md`) and the detailed design in `TASKS/frontend/bff-vue-3-frontend-integration-design.md`, this plan details the implementation of the bff-teacher service following HuleEdu's DDD, Clean Code, and microservices patterns.
 
 ---
 Objective

 Implement the Teacher Backend-for-Frontend (BFF) service that aggregates data from internal microservices and provides screen-specific APIs for the Vue 3 teacher dashboard.

 ---
 Scope

 In Scope:
 - Teacher BFF service with 4 screen-specific endpoints
 - DTO models for teacher screens
 - Internal service client integrations (RAS, CMS, File, Content)
 - WebSocket event publishing to Redis
 - Authentication via JWT (validated by API Gateway; optional BFF JWT validation for direct dev calls)
 - Correlation ID propagation
 - Structured error handling
 - Docker Compose integration
 - Comprehensive tests

 Out of Scope:
 - Admin BFF (separate implementation after teacher BFF validated)
 - Frontend implementation (separate workstream)
 - Backend service modifications (CMS endpoints, RAS optimizations)

 ---
 Architecture Overview

 Service Structure

 services/bff_teacher_service/
 ├── app.py                          # FastAPI app with middleware
 ├── config.py                       # Settings (Pydantic BaseSettings)
 ├── di.py                           # Dishka DI container setup
 ├── dto/
 │   ├── __init__.py
 │   └── teacher_v1.py              # Screen-specific DTOs
 ├── api/
 │   ├── __init__.py
 │   ├── v1/
 │   │   ├── __init__.py
 │   │   ├── dashboard.py           # GET /v1/teacher/dashboard
 │   │   ├── batch_detail.py        # GET /v1/teacher/batches/{batch_id}
 │   │   ├── essay_feedback.py      # GET /v1/teacher/batches/{batch_id}/essays/{essay_id}
 │   │   └── associations.py        # GET /v1/teacher/batches/{batch_id}/associations
 ├── clients/
 │   ├── __init__.py
 │   ├── ras_client.py              # Result Aggregator Service client
 │   ├── cms_client.py              # Class Management Service client
 │   ├── file_client.py             # File Service client
 │   └── content_client.py          # Content Service client
 ├── streaming/
 │   ├── __init__.py
 │   ├── event_publisher.py         # Redis pub/sub for WebSocket
 │   └── kafka_listener.py          # Optional: listen to domain events
 ├── protocols.py                    # Protocol definitions for DI
 ├── tests/
 │   ├── unit/
 │   │   ├── test_dashboard_endpoint.py
 │   │   ├── test_batch_detail_endpoint.py
 │   │   └── test_clients.py
 │   ├── integration/
 │   │   ├── test_ras_integration.py
 │   │   └── test_full_flow.py
 │   └── contract/
 │       └── test_dto_contracts.py
 ├── Dockerfile
 └── README.md

 ---
 Implementation Phases

 Phase 1: Service Skeleton & Configuration (2-3 hours)

 1.1 Create Service Directory Structure

 - Create services/bff_teacher_service/ with subdirectories
 - Initialize __init__.py files
 - Create README.md with service overview

 1.2 Configuration (config.py)

 from pydantic_settings import BaseSettings

 class BFFTeacherSettings(BaseSettings):
     # Service
     SERVICE_NAME: str = "bff_teacher_service"
     SERVICE_PORT: int = 8002  # TBD - choose port

     # Downstream services
     RAS_BASE_URL: str = "http://result_aggregator_service:8000"
     CMS_BASE_URL: str = "http://class_management_service:8000"
     FILE_SERVICE_BASE_URL: str = "http://file_service:8000"
     CONTENT_SERVICE_BASE_URL: str = "http://content_service:8000"

     # Internal auth
     INTERNAL_API_KEY: str  # For calling internal endpoints

     # Redis for WebSocket events
     REDIS_HOST: str = "redis"
     REDIS_PORT: int = 6379

     # JWT validation (shared secret)
     JWT_SECRET_KEY: str
     JWT_ALGORITHM: str = "HS256"

     # CORS
     CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:4173"]

     # Observability
     JAEGER_AGENT_HOST: str = "jaeger"

     class Config:
         env_file = ".env"
         case_sensitive = True

 1.3 FastAPI App Setup (app.py)

 - Initialize FastAPI with title, version, OpenAPI metadata
 - Add CORS middleware
 - Add correlation ID middleware (from huleedu_service_libs)
 - In production rely on JWT validation in API Gateway; optionally add authentication middleware (JWT validation) for direct dev calls
 - Add structured error handlers (from huleedu_service_libs.error_handling)
 - Add Jaeger tracing middleware
 - Register API routers
 - Health check endpoint: GET /health

 Pattern: Follow api_gateway_service/app.py structure but simplified

 1.4 Dependency Injection Setup (di.py)

 from dishka import Provider, Scope, provide
 from .protocols import (
     RASClientProtocol,
     CMSClientProtocol,
     FileClientProtocol,
     ContentClientProtocol,
     EventPublisherProtocol
 )

 class BFFTeacherProvider(Provider):
     @provide(scope=Scope.APP)
     def provide_settings(self) -> BFFTeacherSettings:
         return BFFTeacherSettings()

     @provide(scope=Scope.APP)
     def provide_httpx_client(self) -> httpx.AsyncClient:
         return httpx.AsyncClient(timeout=5.0)

     @provide(scope=Scope.APP)
     def provide_redis_client(self, settings: BFFTeacherSettings) -> redis.Redis:
         return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)

     @provide(scope=Scope.APP)
     def provide_ras_client(
         self, 
         settings: BFFTeacherSettings,
         client: httpx.AsyncClient
     ) -> RASClientProtocol:
         return RASClient(base_url=settings.RAS_BASE_URL, client=client)

     # Similar for CMS, File, Content clients

     @provide(scope=Scope.APP)
     def provide_event_publisher(
         self,
         redis_client: redis.Redis
     ) -> EventPublisherProtocol:
         return EventPublisher(redis_client)

 1.5 Docker Configuration

 - Create Dockerfile (base: Python 3.11, PDM setup)
 - Add to docker-compose.dev.yml:
 bff_teacher_service:
   build:
     context: .
     dockerfile: services/bff_teacher_service/Dockerfile
   container_name: huleedu_bff_teacher
   ports:
     - "8002:8002"
   environment:
     - RAS_BASE_URL=http://result_aggregator_service:8000
     - CMS_BASE_URL=http://class_management_service:8000
   # ... other env vars
   depends_on:
     - result_aggregator_service
     - class_management_service
     - redis
   networks:
     - huleedu-network

 1.6 API Gateway Routing

 Update api_gateway_service/config.py to add:
 BFF_TEACHER_URL: str = "http://bff_teacher_service:8002"

 Add route handler in API Gateway for /bff/v1/teacher/* → forward to BFF

 Deliverable: Service skeleton that starts, responds to /health, and can be called via API Gateway

 ---
 Phase 2: DTO Models (2 hours)

 2.1 Define DTOs (dto/teacher_v1.py)

 Based on architect's design, create 4 main DTOs:

 from pydantic import BaseModel, Field
 from datetime import datetime
 from common_core.status_enums import BatchClientStatus

# Dashboard DTO
 class BatchSummaryV1(BaseModel):
     """Summary of a batch for dashboard list"""
     batch_id: str
     class_id: str | None
     class_name: str | None
     status: BatchClientStatus
     progress: int = Field(ge=0, le=100)
     total_essays: int
     completed_essays: int
     failed_essays: int
     created_at: datetime
     last_updated: datetime
     requested_pipeline: str

 class TeacherClassDashboardV1(BaseModel):
     """Dashboard view: list of batches for teacher"""
     batches: list[BatchSummaryV1]
     total_count: int

# Batch Detail DTO
 class EssayStatusV1(BaseModel):
     """Status of individual essay in batch"""
     essay_id: str
     filename: str
     status: str  # Processing status
     spellcheck_status: str | None
     score: float | None
     processing_started_at: datetime | None
     processing_completed_at: datetime | None

 class TeacherBatchDetailV1(BaseModel):
     """Detailed batch view with all essays"""
     batch_id: str
     overall_status: BatchClientStatus
     class_id: str | None
     class_name: str | None
     created_at: datetime
     last_updated: datetime
     requested_pipeline: str
     total_essays: int
     essays: list[EssayStatusV1]

# Essay Feedback DTO
 class TeacherEssayFeedbackV1(BaseModel):
     """Single essay detail with content and feedback"""
     essay_id: str
     batch_id: str
     filename: str
     content: str  # Essay text
     status: str
     spellcheck_results: dict | None  # Spellcheck feedback
     score: float | None
     ai_feedback: dict | None  # LLM-generated feedback
     created_at: datetime
     last_updated: datetime

# Student Associations DTO
 class StudentAssociationV1(BaseModel):
     """Student-batch association"""
     association_id: str
     student_id: str
     student_name: str
     essay_id: str | None
     filename: str | None
     confirmed: bool

 class StudentAssociationListV1(BaseModel):
     """List of student associations for batch"""
     batch_id: str
     class_id: str
     associations: list[StudentAssociationV1]

 Considerations:
 - Import BatchClientStatus from common_core.status_enums
 - Use optional fields (| None) for data that might not exist
 - Include validation constraints (Field with ge/le for progress)
 - Add docstrings for OpenAPI generation

 Deliverable: DTO models with OpenAPI schema auto-generation

 ---
 Phase 3: Internal Service Clients (4-5 hours)

 3.1 Protocols (protocols.py)

 from typing import Protocol
 from .dto.teacher_v1 import *

 class RASClientProtocol(Protocol):
     async def get_batches_for_user(self, user_id: str) -> list[dict]: ...
     async def get_batch_status(self, batch_id: str) -> dict: ...
     async def get_essay_status(self, essay_id: str) -> dict: ...

 class CMSClientProtocol(Protocol):
     async def get_classes_for_teacher(self, teacher_id: str) -> list[dict]: ...
     async def get_associations_for_batch(self, batch_id: str) -> list[dict]: ...

 class FileClientProtocol(Protocol):
     async def get_file_metadata(self, file_id: str) -> dict: ...

 class ContentClientProtocol(Protocol):
     async def get_essay_content(self, essay_id: str) -> str: ...

 class EventPublisherProtocol(Protocol):
     async def publish_to_user(self, user_id: str, event: dict) -> None: ...

 3.2 RAS Client (clients/ras_client.py)

 import httpx
 from typing import Any

 class RASClient:
     def __init__(self, base_url: str, client: httpx.AsyncClient, api_key: str):
         self.base_url = base_url
         self.client = client
         self.api_key = api_key

     async def get_batches_for_user(self, user_id: str) -> list[dict[str, Any]]:
         """Call RAS: GET /internal/v1/batches/user/{user_id}"""
         headers = {
             "X-Internal-API-Key": self.api_key,
             "X-Service-ID": "bff_teacher_service"
         }
         response = await self.client.get(
             f"{self.base_url}/internal/v1/batches/user/{user_id}",
             headers=headers
         )
         response.raise_for_status()
         return response.json()

     async def get_batch_status(self, batch_id: str) -> dict[str, Any]:
         """Call RAS: GET /internal/v1/batches/{batch_id}/status"""
         headers = {
             "X-Internal-API-Key": self.api_key,
             "X-Service-ID": "bff_teacher_service"
         }
         response = await self.client.get(
             f"{self.base_url}/internal/v1/batches/{batch_id}/status",
             headers=headers
         )
         response.raise_for_status()
         return response.json()

     # Add get_essay_status when RAS implements it

 3.3 CMS Client (clients/cms_client.py)

 class CMSClient:
     def __init__(self, base_url: str, client: httpx.AsyncClient):
         self.base_url = base_url
         self.client = client

     async def get_classes_for_teacher(self, teacher_id: str) -> list[dict[str, Any]]:
         """Call CMS: GET /v1/classes?owner_id={teacher_id}"""
         # NOTE: This endpoint needs to be implemented in CMS
         response = await self.client.get(
             f"{self.base_url}/v1/classes",
             params={"owner_id": teacher_id}
         )
         response.raise_for_status()
         return response.json()

     async def get_associations_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
         """Call CMS: GET /v1/associations/batch/{batch_id}"""
         response = await self.client.get(
             f"{self.base_url}/v1/associations/batch/{batch_id}"
         )
         response.raise_for_status()
         return response.json()

 3.4 File & Content Clients

 Similar pattern for File and Content services (implement as needed)

 Error Handling in Clients:
 - Catch httpx.HTTPStatusError and raise appropriate HuleEduError
 - Map 404 → RESOURCE_NOT_FOUND
 - Map 500 → EXTERNAL_SERVICE_ERROR
 - Include correlation ID in error context

 Deliverable: Working internal service clients with error handling

 ---
 Phase 4: API Endpoints (6-8 hours)

 4.1 Dashboard Endpoint (api/v1/dashboard.py)

 from fastapi import APIRouter, Depends, Header
 from dishka.integrations.fastapi import FromDishka
 from ...dto.teacher_v1 import TeacherClassDashboardV1, BatchSummaryV1
 from ...protocols import RASClientProtocol, CMSClientProtocol
 from common_core.error_enums import ErrorCode
 from huleedu_service_libs.error_handling import HuleEduError

 router = APIRouter(prefix="/v1/teacher", tags=["Teacher"])

 @router.get("/dashboard", response_model=TeacherClassDashboardV1)
 async def get_teacher_dashboard(
     x_user_id: str = Header(..., alias="X-User-ID"),
     x_correlation_id: str = Header(..., alias="X-Correlation-ID"),
     ras_client: RASClientProtocol = FromDishka(),
     cms_client: CMSClientProtocol = FromDishka()
 ) -> TeacherClassDashboardV1:
     """
     Get teacher dashboard: list of all batches with status and progress.
     
     This endpoint aggregates data from:
     - Result Aggregator Service (batch statuses)
     - Class Management Service (class names)
     """
     try:
         # Parallel calls to RAS and CMS
         batches_data, classes_data = await asyncio.gather(
             ras_client.get_batches_for_user(x_user_id),
             cms_client.get_classes_for_teacher(x_user_id)
         )

         # Build class_id -> class_name map
         class_map = {c["class_id"]: c["name"] for c in classes_data}

         # Transform to DTOs
         batch_summaries = [
             BatchSummaryV1(
                 batch_id=b["batch_id"],
                 class_id=b.get("class_id"),
                 class_name=class_map.get(b.get("class_id")),
                 status=b["status"],  # Already BatchClientStatus from RAS
                 progress=b.get("progress", 0),
                 total_essays=b["total_essays"],
                 completed_essays=b.get("completed_essays", 0),
                 failed_essays=b.get("failed_essays", 0),
                 created_at=b["created_at"],
                 last_updated=b["last_updated"],
                 requested_pipeline=b["requested_pipeline"]
             )
             for b in batches_data
         ]

         return TeacherClassDashboardV1(
             batches=batch_summaries,
             total_count=len(batch_summaries)
         )

     except httpx.HTTPStatusError as e:
         if e.response.status_code == 404:
             raise HuleEduError(
                 ErrorCode.RESOURCE_NOT_FOUND,
                 "User data not found",
                 correlation_id=x_correlation_id
             )
         raise HuleEduError(
             ErrorCode.EXTERNAL_SERVICE_ERROR,
             f"Service unavailable: {e}",
             correlation_id=x_correlation_id
         )

 4.2 Batch Detail Endpoint (api/v1/batch_detail.py)

 @router.get("/batches/{batch_id}", response_model=TeacherBatchDetailV1)
 async def get_batch_detail(
     batch_id: str,
     x_user_id: str = Header(..., alias="X-User-ID"),
     x_correlation_id: str = Header(..., alias="X-Correlation-ID"),
     ras_client: RASClientProtocol = FromDishka(),
     cms_client: CMSClientProtocol = FromDishka()
 ) -> TeacherBatchDetailV1:
     """
     Get detailed batch view with all essay statuses.
     
     Data source: primarily RAS (batch status with essays)
     """
     try:
         batch_data = await ras_client.get_batch_status(batch_id)

         # Optional: enrich with class name from CMS if class_id exists
         class_name = None
         if batch_data.get("class_id"):
             classes = await cms_client.get_classes_for_teacher(x_user_id)
             class_map = {c["class_id"]: c["name"] for c in classes}
             class_name = class_map.get(batch_data["class_id"])

         # Map essays
         essay_statuses = [
             EssayStatusV1(
                 essay_id=e["essay_id"],
                 filename=e["filename"],
                 status=e["status"],
                 spellcheck_status=e.get("spellcheck_status"),
                 score=e.get("score"),
                 processing_started_at=e.get("processing_started_at"),
                 processing_completed_at=e.get("processing_completed_at")
             )
             for e in batch_data.get("essays", [])
         ]

         return TeacherBatchDetailV1(
             batch_id=batch_data["batch_id"],
             overall_status=batch_data["status"],
             class_id=batch_data.get("class_id"),
             class_name=class_name,
             created_at=batch_data["created_at"],
             last_updated=batch_data["last_updated"],
             requested_pipeline=batch_data["requested_pipeline"],
             total_essays=len(essay_statuses),
             essays=essay_statuses
         )

     except httpx.HTTPStatusError as e:
         # Similar error handling
         ...

 4.3 Essay Feedback Endpoint (api/v1/essay_feedback.py)

 @router.get(
     "/batches/{batch_id}/essays/{essay_id}", 
     response_model=TeacherEssayFeedbackV1
 )
 async def get_essay_feedback(
     batch_id: str,
     essay_id: str,
     x_user_id: str = Header(..., alias="X-User-ID"),
     x_correlation_id: str = Header(..., alias="X-Correlation-ID"),
     ras_client: RASClientProtocol = FromDishka(),
     content_client: ContentClientProtocol = FromDishka()
 ) -> TeacherEssayFeedbackV1:
     """
     Get detailed essay feedback with content and scores.
     
     Data sources:
     - RAS: essay status, scores, AI feedback
     - Content Service: essay text
     """
     # Implementation: fetch essay from RAS, get content from Content Service
     # Combine into TeacherEssayFeedbackV1
     ...

 4.4 Student Associations Endpoint (api/v1/associations.py)

 @router.get(
     "/batches/{batch_id}/associations",
     response_model=StudentAssociationListV1
 )
 async def get_batch_associations(
     batch_id: str,
     x_user_id: str = Header(..., alias="X-User-ID"),
     x_correlation_id: str = Header(..., alias="X-Correlation-ID"),
     cms_client: CMSClientProtocol = FromDishka()
 ) -> StudentAssociationListV1:
     """
     Get student-essay associations for batch.
     
     Data source: Class Management Service
     """
     try:
         associations_data = await cms_client.get_associations_for_batch(batch_id)

         associations = [
             StudentAssociationV1(
                 association_id=a["association_id"],
                 student_id=a["student_id"],
                 student_name=a["student_name"],
                 essay_id=a.get("essay_id"),
                 filename=a.get("filename"),
                 confirmed=a.get("confirmed", False)
             )
             for a in associations_data
         ]

         return StudentAssociationListV1(
             batch_id=batch_id,
             class_id=associations_data[0]["class_id"] if associations_data else None,
             associations=associations
         )

     except httpx.HTTPStatusError as e:
         # Error handling
         ...

 Common Patterns:
 - Extract X-User-ID from headers (set by API Gateway)
 - Extract X-Correlation-ID for tracing
 - Use Dishka FromDishka() for dependency injection
 - Validate user has access to requested resource (batch ownership)
 - Use async/await throughout
 - Parallel calls with asyncio.gather when independent

 Deliverable: 4 working endpoints returning proper DTOs

 ---
 Phase 5: WebSocket Event Publishing (3-4 hours)

 5.1 Event Publisher (streaming/event_publisher.py)

 import json
 from datetime import datetime
 from typing import Any

 import redis.asyncio as aioredis
 from huleedu_service_libs.redis_pubsub import RedisPubSub

 class EventPublisher:
     def __init__(self, redis_client: aioredis.Redis, client_id: str = "bff_teacher_service"):
         # Use shared RedisPubSub helper to ensure async, standardized channel naming
         self._pubsub = RedisPubSub(client=redis_client, client_id=client_id)

     async def publish_to_user(self, user_id: str, event: dict[str, Any]) -> None:
         """Publish view-model events to the user's WebSocket channel."""
         await self._pubsub.publish_user_notification(
             user_id=user_id,
             event_type=event["event"],
             data=event,
         )

     async def publish_batch_updated(
         self, 
         user_id: str, 
         batch_id: str,
         new_status: str,
         progress: int
     ) -> None:
         """Convenience method for batch update events."""
         event = {
             "event": "BATCH_UPDATED",
             "batch_id": batch_id,
             "new_status": new_status,
             "progress": progress,
             "timestamp": datetime.utcnow().isoformat(),
         }
         await self.publish_to_user(user_id, event)

     async def publish_essay_updated(
         self,
         user_id: str,
         batch_id: str,
         essay_id: str,
         new_score: float | None,
         status: str
     ) -> None:
         """Convenience method for essay update events."""
         event = {
             "event": "ESSAY_UPDATED",
             "batch_id": batch_id,
             "essay_id": essay_id,
             "new_score": new_score,
             "status": status,
             "timestamp": datetime.utcnow().isoformat(),
         }
         await self.publish_to_user(user_id, event)

 5.2 Kafka Listener (Optional - Phase 2)

# streaming/kafka_listener.py
# Listen to domain events and republish as WebSocket events
# Example: BatchProgressUpdated -> publish_batch_updated()
# This can be deferred to Phase 2 if RAS already publishes to Redis

 Integration:
 - When BFF performs mutations (if any), publish events
 - OR: Have RAS publish events directly to Redis (simpler for MVP)
 - Event format matches what WebSocket service expects

 Deliverable: Event publishing to Redis channels

 ---
 Phase 6: Testing (6-8 hours)

 6.1 Unit Tests (tests/unit/)

 Test Dashboard Endpoint:
# tests/unit/test_dashboard_endpoint.py
 import pytest
 from unittest.mock import AsyncMock
 from ...api.v1.dashboard import get_teacher_dashboard

 @pytest.mark.asyncio
 async def test_dashboard_returns_batches():
     # Mock RAS client
     mock_ras = AsyncMock()
     mock_ras.get_batches_for_user.return_value = [
         {
             "batch_id": "batch-123",
             "status": "processing",
             "progress": 50,
             "total_essays": 10,
             # ... other fields
         }
     ]

     # Mock CMS client
     mock_cms = AsyncMock()
     mock_cms.get_classes_for_teacher.return_value = []

     # Call endpoint
     result = await get_teacher_dashboard(
         x_user_id="teacher-1",
         x_correlation_id="test-corr-id",
         ras_client=mock_ras,
         cms_client=mock_cms
     )

     # Assertions
     assert result.total_count == 1
     assert result.batches[0].batch_id == "batch-123"
     assert result.batches[0].status == "processing"

 Test Client Error Handling:
 @pytest.mark.asyncio
 async def test_dashboard_handles_ras_404():
     mock_ras = AsyncMock()
     mock_ras.get_batches_for_user.side_effect = httpx.HTTPStatusError(
         "Not found",
         request=...,
         response=Mock(status_code=404)
     )

     with pytest.raises(HuleEduError) as exc_info:
         await get_teacher_dashboard(...)

     assert exc_info.value.error_code == ErrorCode.RESOURCE_NOT_FOUND

 6.2 Integration Tests (tests/integration/)

 Test RAS Integration:
# tests/integration/test_ras_integration.py
 @pytest.mark.integration
 @pytest.mark.asyncio
 async def test_ras_client_fetches_real_batches(ras_client, test_teacher_id):
     """Test against actual RAS service (in Docker)"""
     batches = await ras_client.get_batches_for_user(test_teacher_id)
     assert isinstance(batches, list)
     # More assertions based on test data

 Test Full Flow:
 @pytest.mark.integration
 @pytest.mark.asyncio
 async def test_full_dashboard_flow(test_client):
     """Test actual HTTP call through FastAPI TestClient"""
     response = await test_client.get(
         "/v1/teacher/dashboard",
         headers={
             "X-User-ID": "test-teacher",
             "X-Correlation-ID": "test-123"
         }
     )
     assert response.status_code == 200
     data = response.json()
     assert "batches" in data
     assert "total_count" in data

 6.3 Contract Tests (tests/contract/)

# tests/contract/test_dto_contracts.py
 def test_dashboard_dto_matches_openapi_schema():
     """Validate DTO can serialize/deserialize per OpenAPI spec"""
     sample_data = {
         "batches": [
             {
                 "batch_id": "123",
                 "status": "processing",
                 # ... all required fields
             }
         ],
         "total_count": 1
     }

     dto = TeacherClassDashboardV1(**sample_data)
     json_output = dto.model_dump_json()

     # Validate against OpenAPI schema
     # Or just ensure it round-trips
     assert TeacherClassDashboardV1.model_validate_json(json_output)

 Test Coverage Goals:
 - Unit tests: 80%+ coverage on endpoints and clients
 - Integration tests: Happy path + error scenarios for each endpoint
 - Contract tests: All DTOs validated

 Deliverable: Comprehensive test suite with >80% coverage

 ---
 Phase 7: Docker & API Gateway Integration (2-3 hours)

 7.1 Update Docker Compose

 Add BFF service to docker-compose.dev.yml as specified in Phase 1.5

 7.2 Update API Gateway

 Add proxy route in API Gateway:
# In api_gateway_service/api/proxy.py or similar
 @router.api_route(
     "/bff/v1/teacher/{path:path}",
     methods=["GET", "POST", "PUT", "DELETE"]
 )
 async def proxy_to_teacher_bff(
     path: str,
     request: Request,
     settings: Settings = Depends(get_settings)
 ):
     """Forward all /bff/v1/teacher/* requests to BFF Teacher service"""
     target_url = f"{settings.BFF_TEACHER_URL}/v1/teacher/{path}"

     # Forward request with all headers (including JWT, correlation ID)
     # Return response from BFF
     ...

 7.3 Environment Configuration

 Create .env.bff-teacher with all required variables

 7.4 Test End-to-End

 1. Start all services: pdm run dev-start
 2. Call via API Gateway: curl <http://localhost:4001/bff/v1/teacher/dashboard> -H "Authorization: Bearer <token>"
 3. Verify response
 4. Check logs for correlation ID propagation

 Deliverable: BFF accessible via API Gateway, full request flow working

 ---
 Phase 8: Documentation & OpenAPI (2 hours)

 8.1 Generate OpenAPI Spec

# Run service and export OpenAPI JSON
 curl <http://localhost:8002/openapi.json> > docs/reference/apis/bff-teacher-openapi.json

 8.2 Generate TypeScript Types

# Use openapi-typescript or similar
 npx openapi-typescript docs/reference/apis/bff-teacher-openapi.json \
   -o docs/reference/apis/bff-teacher-types.ts

 8.3 Update README

 Document:
 - Service purpose
 - Available endpoints
 - Required environment variables
 - How to run locally
 - How to run tests

 Deliverable: OpenAPI spec, TypeScript types, comprehensive README

 ---
 Success Criteria

 ✅ Service runs and is healthy - /health returns 200
 ✅ 4 endpoints implemented - Dashboard, Batch Detail, Essay Feedback, Associations
 ✅ DTOs match design spec - All 4 DTOs defined and working
 ✅ Internal clients work - RAS, CMS clients can call services
 ✅ Error handling consistent - Uses structured error enums
 ✅ Correlation IDs propagate - Tracing works end-to-end
 ✅ WebSocket events publish - Events reach Redis channels
 ✅ Tests pass - Unit (80%+), integration, contract tests all green
 ✅ Docker integration works - Service runs in compose, accessible via gateway
 ✅ OpenAPI generated - TypeScript types available for frontend
 ✅ Type checking passes - pdm run typecheck-all shows 0 errors
 ✅ Linting passes - pdm run format-all && pdm run lint-fix clean

 ---
 Timeline Estimate

 Total: 30-35 hours = 4-5 working days

 - Phase 1: Service Skeleton (2-3 hours)
 - Phase 2: DTO Models (2 hours)
 - Phase 3: Internal Clients (4-5 hours)
 - Phase 4: API Endpoints (6-8 hours)
 - Phase 5: WebSocket Events (3-4 hours)
 - Phase 6: Testing (6-8 hours)
 - Phase 7: Docker Integration (2-3 hours)
 - Phase 8: Documentation (2 hours)
 - Buffer: 3-5 hours for debugging/iteration

 ---
 Dependencies & Blockers

 Backend Service Updates Required

 Class Management Service:
 - ❌ Missing: GET /v1/classes?owner_id={teacher_id} endpoint
 - Blocker Impact: Dashboard cannot enrich batches with class names
 - Workaround: Return null for class_name initially, add later

 Result Aggregator Service:
 - ❌ Optional: GET /internal/v1/essays/{essay_id} endpoint (optimization)
 - Blocker Impact: Essay Feedback must fetch full batch then filter
 - Workaround: Filter batch data in BFF for MVP

 Not Blockers (can proceed without):
 - Identity Service admin endpoints (only needed for Admin BFF)
 - Config Service (only needed for Admin BFF)

 ---
 Risk Mitigation

 Risk: RAS endpoints don't return expected data structure
 Mitigation: Write integration tests early, coordinate with RAS team on contracts

 Risk: JWT validation fails in BFF
 Mitigation: Use existing huleedu_service_libs auth middleware, test with real tokens

 Risk: WebSocket events don't reach frontend
 Mitigation: Test Redis pub/sub independently, use WebSocket service's test endpoint

 Risk: Performance issues with parallel calls
 Mitigation: Monitor with Jaeger, add caching if needed (Phase 2)

 ---
 Post-Implementation

 Phase 2 Enhancements (Future)

 1. Add in-memory caching for dashboard queries (30s TTL)
 2. Implement Kafka listener for proactive event publishing
 3. Add pagination for large batch lists
 4. Optimize essay-level queries (work with RAS team)

 Admin BFF (After Teacher BFF Validated)

 - Follow same pattern
 - 2 endpoints: pending users, system settings
 - Separate service: bff_admin_service

 ---
 Next Steps After Approval

 1. Create feature branch: feature/bff-teacher-service
 2. Create task: pdm run new-task --domain architecture --title "Implement BFF Teacher Service"
 3. Begin Phase 1: Service skeleton
 4. Daily standups to track progress
 5. Code review after Phase 4 (endpoints complete)
 6. Final review after Phase 6 (tests complete)
 7. Merge to main after all success criteria met
