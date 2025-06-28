# Result Aggregator Service: Production-Ready Implementation Guide v2.0

This document provides the definitive implementation guide for the `result_aggregator_service`, incorporating all architectural requirements, security measures, and integration patterns established in the HuleEdu ecosystem.

## Executive Summary

The Result Aggregator Service (RAS) serves as a **materialized view layer** for the event-driven backend, providing fast, query-optimized access to processing results for the API Gateway. This service exemplifies our commitment to Domain-Driven Design, maintaining clear boundaries while aggregating data from multiple processing services.

### Key Architectural Decisions

1. **Event Sourcing Pattern**: RAS consumes completion events to build its materialized view
2. **CQRS Implementation**: Separates write operations (event consumption) from read operations (API queries)
3. **Security-First Design**: Internal API with service-to-service authentication
4. **Performance Optimization**: Normalized schema with strategic indexes and caching
5. **Resilience Patterns**: DLQ integration, idempotency, and graceful degradation

## Service Architecture Overview

```mermaid
graph TD
    subgraph "Event Producers"
        ELS[Essay Lifecycle Service]
        SC[Spell Checker Service]
        CJ[CJ Assessment Service]
        NLP[Future: NLP Service]
        AI[Future: AI Feedback Service]
    end
    
    subgraph "Result Aggregator Service"
        KC[Kafka Consumer]
        DLQ[Dead Letter Queue Handler]
        DB[(PostgreSQL Database)]
        API[Internal REST API]
        CACHE[(Redis Cache)]
        METRICS[Prometheus Metrics]
    end
    
    subgraph "Consumers"
        APIGW[API Gateway Service]
        ADMIN[Future: Admin Dashboard]
    end
    
    ELS -->|Phase Outcomes| KC
    SC -->|Completion Events| KC
    CJ -->|Assessment Results| KC
    NLP -->|Future Events| KC
    AI -->|Future Events| KC
    
    KC --> DB
    KC --> DLQ
    KC --> CACHE
    
    API --> DB
    API --> CACHE
    API --> METRICS
    
    APIGW -->|Queries| API
    ADMIN -->|Future Queries| API
```

## Implementation Checkpoints

### Checkpoint 1: Service Scaffolding & Database Schema

#### Objective
Create a production-ready service structure with a normalized, extensible database schema that supports efficient querying and future service integration.

#### Directory Structure

```
services/result_aggregator_service/
├── __init__.py
├── app.py                    # Lean Quart app setup (<150 lines)
├── api/
│   ├── __init__.py
│   ├── health_routes.py      # MANDATORY health/metrics endpoints
│   ├── query_routes.py       # Internal batch/essay query endpoints
│   └── middleware.py         # Authentication & correlation ID
├── config.py                 # Pydantic Settings configuration
├── di.py                     # Dishka DI container setup
├── enums_api.py             # API-specific enums
├── enums_db.py              # Database-specific enums
├── implementations/
│   ├── __init__.py
│   ├── aggregator_service_impl.py
│   ├── batch_repository_postgres_impl.py
│   ├── state_store_redis_impl.py
│   └── security_impl.py
├── kafka_consumer.py         # Hardened Kafka consumer
├── metrics.py               # Service-specific metrics
├── models_api.py            # API request/response models
├── models_db.py             # SQLAlchemy database models
├── protocols.py             # Service interfaces
├── startup_setup.py         # DI and metrics initialization
├── pyproject.toml           # Service dependencies
├── Dockerfile               # Container configuration
├── tests/                   # Comprehensive test suite
└── README.md               # Service documentation
```

#### Database Schema (models_db.py)

```python
"""Database models for Result Aggregator Service."""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sqlalchemy import Enum as SQLAlchemyEnum


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models."""
    pass


class BatchResultStatus(str, Enum):
    """Overall batch processing status."""
    REGISTERED = "REGISTERED"
    PROCESSING = "PROCESSING"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProcessingPhaseStatus(str, Enum):
    """Individual processing phase status."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class BatchResult(Base):
    """Aggregated batch-level results."""
    __tablename__ = "batch_results"

    # Primary identification
    batch_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Status tracking
    overall_status: Mapped[BatchResultStatus] = mapped_column(
        SQLAlchemyEnum(
            BatchResultStatus,
            name="batch_result_status_enum",
            values_callable=lambda obj: [e.value for e in obj]
        ),
        nullable=False,
        default=BatchResultStatus.REGISTERED
    )
    
    # Metadata
    essay_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_essay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_essay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Processing metadata
    requested_pipeline: Mapped[Optional[str]] = mapped_column(String(100))
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        server_default="CURRENT_TIMESTAMP"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default="CURRENT_TIMESTAMP"
    )
    
    # Error tracking
    last_error: Mapped[Optional[str]] = mapped_column(String(500))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Additional metadata as JSON for flexibility
    metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    essays: Mapped[list["EssayResult"]] = relationship(
        "EssayResult", 
        back_populates="batch", 
        cascade="all, delete-orphan"
    )
    
    __table_args__ = (
        Index('idx_user_batch', 'user_id', 'batch_id'),
        Index('idx_batch_status', 'overall_status'),
        Index('idx_batch_created', 'created_at'),
    )


class EssayResult(Base):
    """Aggregated essay-level results from all processing phases."""
    __tablename__ = "essay_results"

    # Primary identification
    essay_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        String(255), 
        ForeignKey("batch_results.batch_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Core metadata
    filename: Mapped[Optional[str]] = mapped_column(String(255))
    original_text_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # === Current Service Results ===
    
    # Spellcheck Phase Results
    spellcheck_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(
        SQLAlchemyEnum(
            ProcessingPhaseStatus,
            name="processing_phase_status_enum",
            values_callable=lambda obj: [e.value for e in obj]
        )
    )
    spellcheck_correction_count: Mapped[Optional[int]] = mapped_column(Integer)
    spellcheck_corrected_text_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    spellcheck_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    spellcheck_error: Mapped[Optional[str]] = mapped_column(String(500))
    
    # CJ Assessment Phase Results  
    cj_assessment_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(
        SQLAlchemyEnum(
            ProcessingPhaseStatus,
            name="processing_phase_status_enum2",  # Different name for same enum
            values_callable=lambda obj: [e.value for e in obj]
        )
    )
    cj_rank: Mapped[Optional[int]] = mapped_column(Integer)
    cj_score: Mapped[Optional[float]] = mapped_column(Float)
    cj_comparison_count: Mapped[Optional[int]] = mapped_column(Integer)
    cj_assessment_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cj_assessment_error: Mapped[Optional[str]] = mapped_column(String(500))
    
    # === Future Service Placeholders (Commented for Phase 1) ===
    
    # NLP Analysis Phase Results
    # nlp_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(...)
    # nlp_lexical_diversity_score: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_cohesion_score: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_grammatical_error_rate: Mapped[Optional[float]] = mapped_column(Float)
    # nlp_metrics_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    # nlp_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # nlp_error: Mapped[Optional[str]] = mapped_column(String(500))
    
    # AI Feedback Phase Results
    # ai_feedback_status: Mapped[Optional[ProcessingPhaseStatus]] = mapped_column(...)
    # ai_feedback_storage_id: Mapped[Optional[str]] = mapped_column(String(255))
    # ai_feedback_summary: Mapped[Optional[str]] = mapped_column(String(1000))
    # ai_feedback_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    # ai_feedback_error: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        server_default="CURRENT_TIMESTAMP"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default="CURRENT_TIMESTAMP"
    )
    
    # Relationships
    batch: Mapped["BatchResult"] = relationship("BatchResult", back_populates="essays")
    
    __table_args__ = (
        Index('idx_essay_batch', 'batch_id', 'essay_id'),
        Index('idx_essay_spellcheck_status', 'spellcheck_status'),
        Index('idx_essay_cj_status', 'cj_assessment_status'),
        UniqueConstraint('batch_id', 'essay_id', name='uq_batch_essay'),
    )
```

#### Service-Specific Error Handling

The Result Aggregator Service defines its own error types internally, following the bounded context principle. These should NOT be added to common_core.

#### Configuration (config.py)

```python
"""Configuration for Result Aggregator Service."""
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Service Identity
    SERVICE_NAME: str = Field(default="result-aggregator-service")
    SERVICE_VERSION: str = Field(default="1.0.0")
    
    # HTTP API Configuration
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=4003)
    
    # Database Configuration
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://huledu:huledu_password@localhost:5436/result_aggregator"
    )
    DATABASE_POOL_SIZE: int = Field(default=20)
    DATABASE_MAX_OVERFLOW: int = Field(default=10)
    
    # Kafka Configuration
    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="localhost:9093")
    KAFKA_CONSUMER_GROUP_ID: str = Field(default="result-aggregator-group")
    KAFKA_AUTO_OFFSET_RESET: str = Field(default="earliest")
    KAFKA_MAX_POLL_RECORDS: int = Field(default=100)
    KAFKA_SESSION_TIMEOUT_MS: int = Field(default=30000)
    
    # Redis Configuration
    REDIS_URL: str = Field(default="redis://localhost:6379")
    REDIS_CACHE_TTL_SECONDS: int = Field(default=300)  # 5 minutes
    REDIS_IDEMPOTENCY_TTL_SECONDS: int = Field(default=86400)  # 24 hours
    
    # Security Configuration
    INTERNAL_API_KEY: str = Field(
        default="dev-internal-api-key",
        description="Shared secret for service-to-service auth"
    )
    ALLOWED_SERVICE_IDS: list[str] = Field(
        default=["api-gateway-service", "admin-dashboard-service"],
        description="Services allowed to query this API"
    )
    
    # Monitoring Configuration
    METRICS_PORT: int = Field(default=9096)
    LOG_LEVEL: str = Field(default="INFO")
    
    # Performance Configuration
    API_TIMEOUT_SECONDS: int = Field(default=30)
    CACHE_ENABLED: bool = Field(default=True)
    
    # DLQ Configuration
    DLQ_TOPIC: str = Field(default="huleedu.result-aggregator.dlq.v1")
    DLQ_MAX_RETRIES: int = Field(default=3)
```

### Checkpoint 2: Hardened Kafka Consumer with DLQ

#### Kafka Consumer Implementation (kafka_consumer.py)

```python
"""Hardened Kafka consumer for Result Aggregator Service."""
import asyncio
import json
from typing import Any, Optional

from aiokafka import ConsumerRecord
from dishka import AsyncContainer

from common_core.enums import ServiceName
from common_core.errors import EventProcessingError
from common_core.events import (
    CJAssessmentCompletedV1,
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
    SpellcheckResultDataV1
)
# Note: DLQ handling is a BOS responsibility, not individual services
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.kafka_bus import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol

from .metrics import ResultAggregatorMetrics
from .protocols import (
    BatchRepositoryProtocol,
    EventProcessorProtocol,
    StateStoreProtocol
)


logger = create_service_logger("result_aggregator.kafka_consumer")


class ResultAggregatorKafkaConsumer:
    """Kafka consumer with production-grade error handling."""
    
    def __init__(
        self,
        kafka_bus: KafkaBus,
        redis_client: RedisClientProtocol,
        container: AsyncContainer,
        metrics: ResultAggregatorMetrics
    ):
        """Initialize the consumer."""
        self.kafka_bus = kafka_bus
        self.redis_client = redis_client
        self.container = container
        self.metrics = metrics
        self._running = False
        
        # Topic subscription list - current services only
        self.topics = [
            "huleedu.els.batch_phase.outcome.v1",
            "huleedu.essay.spellcheck.completed.v1", 
            "huleedu.cj_assessment.completed.v1",
            # Future topics to add when services are implemented:
            # "huleedu.essay.nlp.completed.v1",
            # "huleedu.essay.aifeedback.completed.v1",
        ]
        
    async def start(self) -> None:
        """Start the consumer loop."""
        logger.info("Starting Result Aggregator Kafka consumer", topics=self.topics)
        self._running = True
        
        try:
            await self.kafka_bus.start()
            await self.kafka_bus.subscribe(self.topics)
            
            while self._running:
                try:
                    # Fetch messages with timeout
                    messages = await self.kafka_bus.get_many(
                        timeout_ms=1000,
                        max_records=100
                    )
                    
                    if messages:
                        await self._process_batch(messages)
                        
                except asyncio.CancelledError:
                    logger.info("Consumer cancelled, shutting down")
                    break
                except Exception as e:
                    logger.error("Error in consumer loop", error=str(e), exc_info=True)
                    self.metrics.consumer_errors.inc()
                    await asyncio.sleep(1)  # Brief pause before retry
                    
        finally:
            await self.kafka_bus.stop()
            logger.info("Kafka consumer stopped")
            
    async def stop(self) -> None:
        """Stop the consumer gracefully."""
        logger.info("Stopping Result Aggregator Kafka consumer")
        self._running = False
        
    async def _process_batch(self, messages: dict[str, list[ConsumerRecord]]) -> None:
        """Process a batch of messages with manual commits."""
        for topic, records in messages.items():
            for record in records:
                try:
                    with self.metrics.message_processing_time.time():
                        await self._process_message(record)
                        
                    # Commit after successful processing
                    await self.kafka_bus.commit()
                    self.metrics.messages_processed.inc()
                    
                except Exception as e:
                    logger.error(
                        "Failed to process message",
                        topic=topic,
                        partition=record.partition,
                        offset=record.offset,
                        error=str(e),
                        exc_info=True
                    )
                    
                    # Log error - DLQ handling is BOS responsibility
                    self.metrics.consumer_errors.inc()
                    
                    # Still commit to avoid reprocessing
                    await self.kafka_bus.commit()
                    
    async def _process_message(self, record: ConsumerRecord) -> None:
        """Process a single message with idempotency check."""
        # Create idempotent wrapper
        @idempotent_consumer(redis_client=self.redis_client, ttl_seconds=86400)
        async def process_message_idempotently(msg: ConsumerRecord) -> bool:
            await self._process_message_impl(msg)
            return True  # Indicate successful processing
        
        # Call the idempotent wrapper
        await process_message_idempotently(record)
    
    async def _process_message_impl(self, record: ConsumerRecord) -> None:
        """Actual message processing logic."""
            
        try:
            # Parse the event envelope
            envelope_data = json.loads(record.value.decode('utf-8'))
            envelope = EventEnvelope.model_validate(envelope_data)
            
            # Route to appropriate handler based on topic
            async with self.container() as request_container:
                processor = await request_container.get(EventProcessorProtocol)
                
                if record.topic == "huleedu.els.batch_phase.outcome.v1":
                    data = ELSBatchPhaseOutcomeV1.model_validate(envelope.data)
                    await processor.process_batch_phase_outcome(envelope, data)
                    
                elif record.topic == "huleedu.essay.spellcheck.completed.v1":
                    data = SpellcheckResultDataV1.model_validate(envelope.data)
                    await processor.process_spellcheck_completed(envelope, data)
                    
                elif record.topic == "huleedu.cj_assessment.completed.v1":
                    data = CJAssessmentCompletedV1.model_validate(envelope.data)
                    await processor.process_cj_assessment_completed(envelope, data)
                    
                else:
                    logger.warning(f"Unhandled topic: {record.topic}")
                    
        except json.JSONDecodeError as e:
            raise EventProcessingError(f"Invalid JSON: {str(e)}")
        except Exception as e:
            raise EventProcessingError(f"Processing failed: {str(e)}")
            
    # Note: DLQ handling removed - this is BOS responsibility
    # Services should focus on idempotent processing and logging errors
```

### Checkpoint 3: Secured Internal API with Blueprint Pattern

#### Health Routes (api/health_routes.py)

```python
"""Health check and metrics endpoints."""
from quart import Blueprint, Response, jsonify

from huleedu_service_libs.logging_utils import create_service_logger

from ..metrics import ResultAggregatorMetrics


logger = create_service_logger("result_aggregator.api.health")

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz")
async def health_check() -> Response:
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "result_aggregator_service",
        "version": "1.0.0"
    })


@health_bp.route("/metrics")
async def metrics(metrics_instance: ResultAggregatorMetrics) -> Response:
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest
    
    return Response(
        generate_latest(),
        mimetype="text/plain; version=0.0.4"
    )
```

#### Query Routes (api/query_routes.py)

```python
"""Internal API routes for querying aggregated results."""
from typing import Optional
from uuid import uuid4

from dishka.integrations.quart import FromDishka, inject
from quart import Blueprint, Response, g, jsonify, request

from huleedu_service_libs.logging_utils import create_service_logger

from ..metrics import ResultAggregatorMetrics
from ..models_api import BatchStatusRequest, BatchStatusResponse, ErrorResponse
from ..protocols import (
    BatchQueryServiceProtocol,
    SecurityServiceProtocol
)


logger = create_service_logger("result_aggregator.api.query")

query_bp = Blueprint("query", __name__, url_prefix="/internal/v1")


@query_bp.before_request
@inject
async def authenticate_request(
    security: FromDishka[SecurityServiceProtocol]
) -> Optional[Response]:
    """Authenticate internal service requests."""
    # Extract service credentials
    api_key = request.headers.get("X-Internal-API-Key")
    service_id = request.headers.get("X-Service-ID")
    
    if not api_key or not service_id:
        logger.warning("Missing authentication headers")
        return jsonify({"error": "Missing authentication"}), 401
        
    # Validate credentials
    if not await security.validate_service_credentials(api_key, service_id):
        logger.warning("Invalid service credentials", service_id=service_id)
        return jsonify({"error": "Invalid credentials"}), 401
        
    # Set request context
    g.service_id = service_id
    g.correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    
    return None


@query_bp.route("/batches/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    query_service: FromDishka[BatchQueryServiceProtocol],
    metrics: FromDishka[ResultAggregatorMetrics]
) -> Response:
    """Get comprehensive batch status including all essay results."""
    with metrics.api_request_duration.labels(
        endpoint="get_batch_status",
        method="GET"
    ).time():
        try:
            logger.info(
                "Batch status query",
                batch_id=batch_id,
                service_id=g.service_id,
                correlation_id=g.correlation_id
            )
            
            # Query the aggregated results
            result = await query_service.get_batch_status(batch_id)
            
            if not result:
                metrics.api_requests_total.labels(
                    endpoint="get_batch_status",
                    method="GET",
                    status_code=404
                ).inc()
                return jsonify({"error": "Batch not found"}), 404
                
            # Convert to API response model
            response = BatchStatusResponse.from_domain(result)
            
            metrics.api_requests_total.labels(
                endpoint="get_batch_status",
                method="GET", 
                status_code=200
            ).inc()
            
            return jsonify(response.model_dump(mode="json")), 200
            
        except ValueError as e:
            logger.error("Invalid batch ID", batch_id=batch_id, error=str(e))
            metrics.api_errors_total.labels(
                endpoint="get_batch_status",
                error_type="validation"
            ).inc()
            return jsonify({"error": "Invalid batch ID"}), 400
            
        except Exception as e:
            logger.error(
                "Error retrieving batch status",
                batch_id=batch_id,
                error=str(e),
                exc_info=True
            )
            metrics.api_errors_total.labels(
                endpoint="get_batch_status",
                error_type="internal"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500


@query_bp.route("/batches/user/<user_id>", methods=["GET"])
@inject
async def get_user_batches(
    user_id: str,
    query_service: FromDishka[BatchQueryServiceProtocol],
    metrics: FromDishka[ResultAggregatorMetrics]
) -> Response:
    """Get all batches for a specific user."""
    with metrics.api_request_duration.labels(
        endpoint="get_user_batches",
        method="GET"
    ).time():
        try:
            # Parse query parameters
            limit = request.args.get("limit", 20, type=int)
            offset = request.args.get("offset", 0, type=int)
            status = request.args.get("status", type=str)
            
            logger.info(
                "User batches query",
                user_id=user_id,
                limit=limit,
                offset=offset,
                status=status,
                service_id=g.service_id
            )
            
            # Query batches
            batches = await query_service.get_user_batches(
                user_id=user_id,
                status=status,
                limit=limit,
                offset=offset
            )
            
            metrics.api_requests_total.labels(
                endpoint="get_user_batches",
                method="GET",
                status_code=200
            ).inc()
            
            return jsonify({
                "batches": [b.model_dump(mode="json") for b in batches],
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "total": len(batches)  # Would include total count in production
                }
            }), 200
            
        except Exception as e:
            logger.error(
                "Error retrieving user batches",
                user_id=user_id,
                error=str(e),
                exc_info=True
            )
            metrics.api_errors_total.labels(
                endpoint="get_user_batches",
                error_type="internal"
            ).inc()
            return jsonify({"error": "Internal server error"}), 500
```

#### API Models (models_api.py)

```python
"""API request and response models."""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .enums_api import BatchStatus, ProcessingPhase


class EssayResultResponse(BaseModel):
    """Essay result in API response."""
    essay_id: str
    filename: Optional[str] = None
    
    # Current service results
    spellcheck_status: Optional[str] = None
    spellcheck_correction_count: Optional[int] = None
    spellcheck_corrected_text_storage_id: Optional[str] = None
    spellcheck_error: Optional[str] = None
    
    cj_assessment_status: Optional[str] = None
    cj_rank: Optional[int] = None
    cj_score: Optional[float] = None
    cj_assessment_error: Optional[str] = None
    
    # Timestamps
    last_updated: datetime


class BatchStatusResponse(BaseModel):
    """Comprehensive batch status response."""
    batch_id: str
    user_id: str  # Critical for API Gateway security checks
    overall_status: BatchStatus
    
    # Counts
    essay_count: int
    completed_essay_count: int
    failed_essay_count: int
    
    # Processing info
    requested_pipeline: Optional[str] = None
    current_phase: Optional[ProcessingPhase] = None
    
    # Essays with results
    essays: List[EssayResultResponse] = Field(default_factory=list)
    
    # Metadata
    created_at: datetime
    last_updated: datetime
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    
    @classmethod
    def from_domain(cls, batch_result: "BatchResult") -> "BatchStatusResponse":
        """Convert from domain model."""
        return cls(
            batch_id=batch_result.batch_id,
            user_id=batch_result.user_id,
            overall_status=BatchStatus(batch_result.overall_status.value),
            essay_count=batch_result.essay_count,
            completed_essay_count=batch_result.completed_essay_count,
            failed_essay_count=batch_result.failed_essay_count,
            requested_pipeline=batch_result.requested_pipeline,
            current_phase=ProcessingPhase.SPELLCHECK,  # Derive from data
            essays=[
                EssayResultResponse(
                    essay_id=essay.essay_id,
                    filename=essay.filename,
                    spellcheck_status=essay.spellcheck_status.value if essay.spellcheck_status else None,
                    spellcheck_correction_count=essay.spellcheck_correction_count,
                    spellcheck_corrected_text_storage_id=essay.spellcheck_corrected_text_storage_id,
                    spellcheck_error=essay.spellcheck_error,
                    cj_assessment_status=essay.cj_assessment_status.value if essay.cj_assessment_status else None,
                    cj_rank=essay.cj_rank,
                    cj_score=essay.cj_score,
                    cj_assessment_error=essay.cj_assessment_error,
                    last_updated=essay.updated_at
                )
                for essay in batch_result.essays
            ],
            created_at=batch_result.created_at,
            last_updated=batch_result.updated_at,
            processing_started_at=batch_result.processing_started_at,
            processing_completed_at=batch_result.processing_completed_at
        )


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    details: Optional[Dict] = None
    correlation_id: Optional[str] = None
```

### Checkpoint 4: Service Integration & Infrastructure

#### Docker Configuration

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy service files
COPY pyproject.toml pdm.lock ./
COPY services/result_aggregator_service ./services/result_aggregator_service
COPY common_core ./common_core
COPY services/libs ./services/libs

# Install PDM and dependencies
RUN pip install pdm && \
    pdm install --prod --no-lock

# Set Python path
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 4003 9096

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4003/healthz || exit 1

# Run the service
CMD ["pdm", "run", "python", "-m", "services.result_aggregator_service.app"]
```

#### Docker Compose Integration

Add to `docker-compose.infrastructure.yml`:

```yaml
  # PostgreSQL database for Result Aggregator Service
  result_aggregator_db:
    image: postgres:15
    container_name: huleedu_result_aggregator_db
    restart: unless-stopped
    networks:
      - huleedu_internal_network
    ports:
      - "5436:5432"
    environment:
      - POSTGRES_DB=result_aggregator
      - POSTGRES_USER=${HULEEDU_DB_USER}
      - POSTGRES_PASSWORD=${HULEEDU_DB_PASSWORD}
    volumes:
      - result_aggregator_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${HULEEDU_DB_USER} -d result_aggregator"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

Add to `docker-compose.yml`:

```yaml
  result_aggregator_service:
    build:
      context: .
      dockerfile: services/result_aggregator_service/Dockerfile
    container_name: huleedu_result_aggregator
    restart: unless-stopped
    networks:
      - huleedu_internal_network
    ports:
      - "4003:4003"  # API port
      - "9096:9096"  # Metrics port
    environment:
      - DATABASE_URL=postgresql+asyncpg://huledu:${HULEEDU_DB_PASSWORD}@result_aggregator_db:5432/result_aggregator
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379
      - INTERNAL_API_KEY=${HULEEDU_INTERNAL_API_KEY}
      - LOG_LEVEL=INFO
    depends_on:
      result_aggregator_db:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./logs/result_aggregator:/app/logs
```

## Integration Requirements for Other Services

### 1. API Gateway Service Updates

The API Gateway must be updated to integrate with the Result Aggregator Service:

```python
# api_gateway_service/implementations/batch_status_service_impl.py

class BatchStatusServiceImpl(BatchStatusServiceProtocol):
    """Enhanced implementation using Result Aggregator Service."""
    
    def __init__(
        self,
        http_client: aiohttp.ClientSession,
        settings: Settings,
        metrics: APIGatewayMetrics
    ):
        self.http_client = http_client
        self.ras_base_url = settings.RESULT_AGGREGATOR_URL
        self.internal_api_key = settings.INTERNAL_API_KEY
        self.service_id = "api-gateway-service"
        self.metrics = metrics
        
    async def get_batch_status(
        self, 
        batch_id: str, 
        user_id: str,
        correlation_id: str
    ) -> Optional[BatchStatusResponse]:
        """Get batch status from Result Aggregator Service."""
        headers = {
            "X-Internal-API-Key": self.internal_api_key,
            "X-Service-ID": self.service_id,
            "X-Correlation-ID": correlation_id
        }
        
        try:
            async with self.http_client.get(
                f"{self.ras_base_url}/internal/v1/batches/{batch_id}/status",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 404:
                    return None
                    
                response.raise_for_status()
                data = await response.json()
                
                # Verify user ownership
                if data["user_id"] != user_id:
                    logger.warning(
                        "User ID mismatch",
                        batch_id=batch_id,
                        expected_user_id=user_id,
                        actual_user_id=data["user_id"]
                    )
                    return None
                    
                return BatchStatusResponse.model_validate(data)
                
        except Exception as e:
            logger.error(
                "Failed to get batch status",
                batch_id=batch_id,
                error=str(e),
                exc_info=True
            )
            self.metrics.external_api_errors.labels(
                service="result_aggregator",
                operation="get_batch_status"
            ).inc()
            raise
```

### 2. Essay Lifecycle Service Event Publishing

ELS must ensure all completion events include necessary metadata:

```python
# essay_lifecycle_service/implementations/event_publisher_impl.py additions

async def publish_batch_phase_outcome(
    self,
    batch_id: str,
    phase: ProcessingPhase,
    outcome: PhaseOutcome,
    metadata: Dict[str, Any]
) -> None:
    """Publish batch phase outcome with enhanced metadata."""
    # Ensure user_id is included in metadata
    if "user_id" not in metadata:
        # Fetch from batch context
        batch = await self.batch_repository.get_batch(batch_id)
        metadata["user_id"] = batch.user_id
        
    # Include essay count information
    metadata["total_essay_count"] = metadata.get("total_essay_count", 0)
    metadata["completed_essay_count"] = metadata.get("completed_essay_count", 0)
    metadata["failed_essay_count"] = metadata.get("failed_essay_count", 0)
    
    # Publish the event
    event_data = ELSBatchPhaseOutcomeV1(
        batch_id=batch_id,
        phase=phase,
        outcome=outcome,
        metadata=metadata,
        timestamp=datetime.utcnow()
    )
    
    await self._publish_event(
        event_type="els.batch_phase.outcome.v1",
        data=event_data
    )
```

### 3. Event Consumption Pattern

The Result Aggregator Service is a pure consumer - it does not emit any events. It maintains its materialized view by consuming events from other services. This follows the CQRS pattern where the read model is updated based on events from the write model.

Note: All event contracts (Pydantic models) used by the service are already defined in common_core/events:

- `ELSBatchPhaseOutcomeV1` - from Essay Lifecycle Service
- `SpellcheckResultDataV1` - from Spell Checker Service  
- `CJAssessmentCompletedV1` - from CJ Assessment Service

The service consumes these existing event contracts; it does not define new ones.

## Performance Optimization Strategies

### 1. Database Optimization

- **Indexes**: Composite indexes on frequently queried columns
- **Partitioning**: Consider partitioning by created_at for large datasets
- **Connection Pooling**: Configured for optimal performance
- **Query Optimization**: Use EXPLAIN ANALYZE for query tuning

### 2. Caching Strategy

```python
# implementations/cache_manager.py

class CacheManager:
    """Manages caching for frequently accessed data."""
    
    async def get_batch_status(
        self, 
        batch_id: str
    ) -> Optional[BatchStatusResponse]:
        """Get batch status from cache."""
        cache_key = f"batch_status:{batch_id}"
        
        # Try cache first
        cached = await self.redis_client.get(cache_key)
        if cached:
            return BatchStatusResponse.model_validate_json(cached)
            
        return None
        
    async def set_batch_status(
        self,
        batch_id: str,
        status: BatchStatusResponse,
        ttl: int = 300
    ) -> None:
        """Cache batch status."""
        cache_key = f"batch_status:{batch_id}"
        await self.redis_client.setex(
            cache_key,
            ttl,
            status.model_dump_json()
        )
```

### 3. Event Processing Optimization

- **Batch Processing**: Process multiple events in a single database transaction
- **Async I/O**: Leverage asyncio for concurrent operations
- **Connection Reuse**: Maintain persistent connections to databases and cache

## Monitoring and Observability

### Metrics Implementation

```python
# metrics.py

from prometheus_client import Counter, Histogram, Gauge

class ResultAggregatorMetrics:
    """Service-specific metrics."""
    
    def __init__(self):
        # API metrics
        self.api_requests_total = Counter(
            'ras_api_requests_total',
            'Total API requests',
            ['endpoint', 'method', 'status_code']
        )
        
        self.api_request_duration = Histogram(
            'ras_api_request_duration_seconds',
            'API request duration',
            ['endpoint', 'method']
        )
        
        self.api_errors_total = Counter(
            'ras_api_errors_total',
            'Total API errors',
            ['endpoint', 'error_type']
        )
        
        # Kafka consumer metrics
        self.messages_processed = Counter(
            'ras_messages_processed_total',
            'Total messages processed'
        )
        
        self.message_processing_time = Histogram(
            'ras_message_processing_duration_seconds',
            'Message processing duration'
        )
        
        self.consumer_errors = Counter(
            'ras_consumer_errors_total',
            'Total consumer errors'
        )
        
        # Database metrics
        self.db_operations = Counter(
            'ras_db_operations_total',
            'Total database operations',
            ['operation', 'status']
        )
        
        self.db_operation_duration = Histogram(
            'ras_db_operation_duration_seconds',
            'Database operation duration',
            ['operation']
        )
        
        # Cache metrics
        self.cache_hits = Counter(
            'ras_cache_hits_total',
            'Cache hits'
        )
        
        self.cache_misses = Counter(
            'ras_cache_misses_total',
            'Cache misses'
        )
        
        # Business metrics
        self.batches_aggregated = Counter(
            'ras_batches_aggregated_total',
            'Total batches aggregated'
        )
        
        self.essays_aggregated = Counter(
            'ras_essays_aggregated_total',
            'Total essays aggregated',
            ['phase']
        )
```

## Testing Strategy

### Unit Tests

```python
# tests/test_event_processor.py

import pytest
from unittest.mock import AsyncMock, MagicMock

from common_core.events import SpellcheckResultDataV1, EventEnvelope
from services.result_aggregator_service.implementations import EventProcessorImpl


class TestEventProcessor:
    """Test event processing logic."""
    
    @pytest.mark.asyncio
    async def test_process_spellcheck_completed(self):
        """Test processing spellcheck completion event."""
        # Arrange
        mock_repo = AsyncMock()
        mock_cache = AsyncMock()
        processor = EventProcessorImpl(mock_repo, mock_cache)
        
        envelope = EventEnvelope(
            event_id="test-123",
            event_type="essay.spellcheck.completed.v1",
            source_service="spell_checker_service",
            data={
                "essay_id": "essay-123",
                "batch_id": "batch-456",
                "correction_count": 5,
                "corrected_text_storage_id": "storage-789",
                "status": "COMPLETED"
            }
        )
        
        data = SpellcheckCompletedDataV1.model_validate(envelope.data)
        
        # Act
        await processor.process_spellcheck_completed(envelope, data)
        
        # Assert
        mock_repo.update_essay_spellcheck_result.assert_called_once_with(
            essay_id="essay-123",
            batch_id="batch-456",
            status="COMPLETED",
            correction_count=5,
            corrected_text_storage_id="storage-789",
            error=None
        )
        
        mock_cache.invalidate_batch.assert_called_once_with("batch-456")
```

### Integration Tests

```python
# tests/integration/test_api_integration.py

import pytest
from quart import Quart
from quart.testing import QuartClient

from services.result_aggregator_service.app import create_app


class TestAPIIntegration:
    """Test API integration."""
    
    @pytest.mark.asyncio
    async def test_get_batch_status_authenticated(self):
        """Test authenticated batch status retrieval."""
        # Arrange
        app = create_app(test_mode=True)
        client: QuartClient = app.test_client()
        
        headers = {
            "X-Internal-API-Key": "test-key",
            "X-Service-ID": "api-gateway-service",
            "X-Correlation-ID": "test-correlation"
        }
        
        # Act
        response = await client.get(
            "/internal/v1/batches/test-batch-123/status",
            headers=headers
        )
        
        # Assert
        assert response.status_code == 200
        data = await response.get_json()
        assert data["batch_id"] == "test-batch-123"
        assert "user_id" in data
        assert "essays" in data
```

## Deployment Checklist

- [ ] Database migrations created and tested
- [ ] Docker image builds successfully
- [ ] Integration tests pass in CI/CD pipeline
- [ ] Metrics endpoints accessible
- [ ] Health check returns healthy status
- [ ] DLQ topic created in Kafka
- [ ] Internal API authentication configured
- [ ] Redis connection established
- [ ] Performance testing completed
- [ ] Monitoring dashboards configured
- [ ] Documentation updated
- [ ] Security review completed

## Conclusion

This implementation guide provides a comprehensive, production-ready design for the Result Aggregator Service that:

1. **Aligns with Architecture**: Follows all established patterns from BOS and CMS
2. **Ensures Security**: Implements service-to-service authentication
3. **Maximizes Performance**: Uses normalized schema, caching, and optimization
4. **Provides Resilience**: Includes idempotency and comprehensive error handling
5. **Enables Observability**: Comprehensive metrics and logging
6. **Supports Growth**: Extensible design for future services

The service is ready for implementation following this guide, with all critical architectural concerns addressed and integration points clearly defined.
