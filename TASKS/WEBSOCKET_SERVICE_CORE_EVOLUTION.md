# WebSocket Service Core Evolution: Three-Layer Architecture for Real-Time Notifications

---

**Task ID**: `WS-CORE-001`  
**Status**: `Ready for Implementation`  
**Author**: `System Architect`  
**Date**: `2025-08-06`  
**Priority**: `HIGH`

---

## 🎯 **OBJECTIVE**

Evolve the WebSocket service from handling 2 file events (3% coverage) to 17 critical user-facing events (25% coverage) using a **three-layer architecture** that separates infrastructure, domain routing, and notification handling while strictly adhering to HuleEdu architectural mandates.

## 🏗️ **ARCHITECTURAL FOUNDATION ANALYSIS**

### **Current Implementation Strengths**
✅ **Protocol-Based Architecture**: Proper `typing.Protocol` interfaces  
✅ **Service Library Compliance**: Uses `huleedu_service_libs` correctly  
✅ **Dishka DI Integration**: Proper scoping and lifecycle management  
✅ **Structured Error Handling**: `HuleEduError` pattern implementation  
✅ **Event Processing**: Kafka consumer with `@idempotent_consumer`  
✅ **Redis Pub/Sub Bridge**: Reliable message delivery pipeline  
✅ **JWT Authentication**: Secure WebSocket connection establishment  
✅ **Testing Framework**: E2E validation with Docker integration  

### **Current Event Flow (Proven Architecture)**
```
File Service → Kafka (outbox) → WebSocket Service → Redis → WebSocket Clients
                    ↓
               (FileEventConsumer)
                    ↓
            (FileNotificationHandler)
                    ↓
              (Redis Pub/Sub)
```

## 🎯 **CORE EVOLUTION STRATEGY**

### **Design Philosophy: THREE-LAYER SEPARATION**

**INFRASTRUCTURE**: Kafka consumption mechanics isolated from business logic  
**DOMAIN**: Event routing and processing with clean routing table  
**NOTIFICATION**: User notification formatting and Redis publishing  

### **Architectural Pattern: Clean Layer Separation**
- **KafkaEventConsumer**: Handles only Kafka lifecycle and message consumption
- **DomainEventProcessor**: Routes events to handlers using mapping table (no if-elif chains)
- **UserNotificationHandler**: Transforms domain events into user notifications
- **Maintain current testing patterns** with systematic coverage expansion for each layer

## 📋 **IMPLEMENTATION PHASES**

### **Phase 1: Common Core Enum Registration (1 day)**

#### **1.1 WebSocket Event Categories Enum**

**File**: `/libs/common_core/src/common_core/websocket_enums.py`

```python
"""WebSocket service enums for event categorization and notification handling."""

from __future__ import annotations

from enum import Enum


class WebSocketEventCategory(str, Enum):
    """Categories for WebSocket event prioritization and filtering."""
    
    BATCH_PROGRESS = "batch_progress"        # Batch processing updates
    PROCESSING_RESULTS = "processing_results"  # Service completion events  
    FILE_OPERATIONS = "file_operations"     # File upload/removal events
    CLASS_MANAGEMENT = "class_management"   # Class/student operations
    STUDENT_WORKFLOW = "student_workflow"   # Student matching/validation
    SYSTEM_ALERTS = "system_alerts"        # Error notifications


class NotificationPriority(str, Enum):
    """Notification delivery priority levels."""
    
    IMMEDIATE = "immediate"    # Real-time delivery required
    STANDARD = "standard"      # Normal delivery queue
    LOW = "low"               # Can be batched/delayed


class WebSocketConnectionState(str, Enum):
    """WebSocket connection lifecycle states."""
    
    CONNECTING = "connecting"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    DISCONNECTED = "disconnected"
    ERROR = "error"
```

#### **1.2 Update Common Core __init__.py**

**File**: `/libs/common_core/src/common_core/__init__.py`

```python
# Add to existing imports
from .websocket_enums import (
    WebSocketEventCategory,
    NotificationPriority, 
    WebSocketConnectionState,
)
```

### **Phase 2: Three-Layer Architecture Implementation (3 days)**

#### **2.1 Enhanced Kafka Topic Configuration**

**File**: `/services/websocket_service/config.py`

```python
# Add to existing settings
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Additional Kafka topics for expanded event handling
    BATCH_ESSAYS_READY_TOPIC: str = Field(
        default="huleedu.batch.essays.ready.v1",
        description="Batch readiness notifications"
    )
    BATCH_VALIDATION_ERRORS_TOPIC: str = Field(
        default="huleedu.batch.validation.errors.v1", 
        description="Batch validation error events"
    )
    BATCH_CONTENT_PROVISIONING_COMPLETED_TOPIC: str = Field(
        default="huleedu.batch.content.provisioning.completed.v1",
        description="Content provisioning completion events"
    )
    BATCH_AUTHOR_MATCHES_SUGGESTED_TOPIC: str = Field(
        default="huleedu.batch.author.matches.suggested.v1",
        description="Critical: User action required for student matching"
    )
    STUDENT_ASSOCIATIONS_CONFIRMED_TOPIC: str = Field(
        default="huleedu.class.student.associations.confirmed.v1",
        description="Student validation confirmation events"
    )
    VALIDATION_TIMEOUT_PROCESSED_TOPIC: str = Field(
        default="huleedu.class.validation.timeout.processed.v1",
        description="Validation timeout processing events"
    )
    CJ_ASSESSMENT_COMPLETED_TOPIC: str = Field(
        default="huleedu.cj_assessment.completed.v1",
        description="CJ Assessment completion events"
    )
    CJ_ASSESSMENT_FAILED_TOPIC: str = Field(
        default="huleedu.cj_assessment.failed.v1",
        description="CJ Assessment failure events"
    )
    SPELLCHECK_COMPLETED_TOPIC: str = Field(
        default="huleedu.essay.spellcheck.completed.v1",
        description="Spellcheck completion events"
    )
    ELS_BATCH_PHASE_OUTCOME_TOPIC: str = Field(
        default="huleedu.els.batch.phase.outcome.v1",
        description="ELS batch phase outcome events"
    )
    ESSAY_CONTENT_PROVISIONED_TOPIC: str = Field(
        default="huleedu.essay.content.provisioned.v1",
        description="Essay content provisioning events"
    )
    ESSAY_VALIDATION_FAILED_TOPIC: str = Field(
        default="huleedu.essay.validation.failed.v1",
        description="Essay validation failure events"
    )
    CLASS_CREATED_TOPIC: str = Field(
        default="huleedu.class.created.v1",
        description="Class creation events"
    )
    STUDENT_CREATED_TOPIC: str = Field(
        default="huleedu.student.created.v1", 
        description="Student creation events"
    )
    ESSAY_STUDENT_ASSOCIATION_UPDATED_TOPIC: str = Field(
        default="huleedu.essay.student.association.updated.v1",
        description="Essay-student association events"
    )
    
    def get_subscribed_topics(self) -> list[str]:
        """Return all topics this service subscribes to."""
        return [
            self.BATCH_FILE_ADDED_TOPIC,
            self.BATCH_FILE_REMOVED_TOPIC,
            self.BATCH_ESSAYS_READY_TOPIC,
            self.BATCH_VALIDATION_ERRORS_TOPIC,
            self.BATCH_CONTENT_PROVISIONING_COMPLETED_TOPIC,
            self.BATCH_AUTHOR_MATCHES_SUGGESTED_TOPIC,
            self.STUDENT_ASSOCIATIONS_CONFIRMED_TOPIC,
            self.VALIDATION_TIMEOUT_PROCESSED_TOPIC,
            self.CJ_ASSESSMENT_COMPLETED_TOPIC,
            self.CJ_ASSESSMENT_FAILED_TOPIC,
            self.SPELLCHECK_COMPLETED_TOPIC,
            self.ELS_BATCH_PHASE_OUTCOME_TOPIC,
            self.ESSAY_CONTENT_PROVISIONED_TOPIC,
            self.ESSAY_VALIDATION_FAILED_TOPIC,
            self.CLASS_CREATED_TOPIC,
            self.STUDENT_CREATED_TOPIC,
            self.ESSAY_STUDENT_ASSOCIATION_UPDATED_TOPIC,
        ]
```

#### **2.2 Kafka Event Consumer (Infrastructure Layer)**

**File**: `/services/websocket_service/implementations/kafka_event_consumer.py` (New)

```python
"""Kafka event consumer - infrastructure layer only."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaConnectionError
from huleedu_service_libs.error_handling import (
    raise_connection_error,
    raise_initialization_failed,
)
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import create_service_logger

from services.websocket_service.config import Settings
from services.websocket_service.protocols import EventProcessorProtocol, KafkaConsumerProtocol

logger = create_service_logger("websocket.kafka_consumer")


class KafkaEventConsumer(KafkaConsumerProtocol):
    """Kafka consumer handling only infrastructure concerns."""

    def __init__(
        self,
        event_processor: EventProcessorProtocol,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
        tracer: Tracer | None = None,
    ) -> None:
        """Initialize the Kafka consumer."""
        self.event_processor = event_processor
        self.settings = settings
        self.redis_client = redis_client
        self.tracer = tracer
        self.consumer: AIOKafkaConsumer | None = None
        self.should_stop = False
        self.topics = settings.get_subscribed_topics()

        # Create idempotency configuration
        idempotency_config = IdempotencyConfig(
            service_name="websocket-service",
            enable_debug_logging=True,
        )

        # Create idempotent message processor
        @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
        async def process_message_idempotently(
            msg: object, *, confirm_idempotency: Callable[[], Awaitable[None]]
        ) -> bool | None:
            result = await self.event_processor.process_event(msg.value)
            await confirm_idempotency()
            return result

        self.process_message_idempotently = process_message_idempotently

    async def start_consumer(self) -> None:
        """Start consuming events from Kafka."""
        try:
            logger.info(
                "Starting Kafka consumer",
                extra={
                    "topics": self.topics,
                    "group_id": self.settings.KAFKA_CONSUMER_GROUP,
                },
            )

            self.consumer = AIOKafkaConsumer(
                *self.topics,
                bootstrap_servers=self.settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=self.settings.KAFKA_CONSUMER_GROUP,
                client_id=self.settings.KAFKA_CONSUMER_CLIENT_ID,
                enable_auto_commit=False,
                auto_offset_reset="earliest",
            )

            await self.consumer.start()
            logger.info("Kafka consumer started successfully")

            # Main consumption loop
            async for msg in self.consumer:
                if self.should_stop:
                    break

                try:
                    await self.process_message_idempotently(msg)
                    await self.consumer.commit()
                except Exception as e:
                    logger.error(
                        f"Error processing message: {e}",
                        exc_info=True,
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
                    # Continue processing other messages

        except KafkaConnectionError as e:
            logger.error(f"Kafka connection error: {e}", exc_info=True)
            raise_connection_error(
                service="websocket_service",
                operation="kafka_consume",
                target="kafka",
                message=f"Failed to connect to Kafka: {str(e)}",
                correlation_id=uuid4(),
            )
        except Exception as e:
            logger.error(f"Unexpected error in consumer: {e}", exc_info=True)
            raise_initialization_failed(
                service="websocket_service",
                operation="start_consumer",
                component="kafka_consumer",
                message=f"Failed to initialize Kafka consumer: {str(e)}",
                correlation_id=uuid4(),
            )
        finally:
            if self.consumer:
                await self.consumer.stop()

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        logger.info("Stopping Kafka consumer")
        self.should_stop = True
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")
```

#### **2.3 Domain Event Processor (Domain Layer)**

**File**: `/services/websocket_service/implementations/domain_event_processor.py` (New)

```python
"""Domain event processor - routes events to appropriate handlers."""

from __future__ import annotations

import json
from typing import Callable, Dict, Tuple, Type

from common_core.events.batch_coordination_events import (
    BatchContentProvisioningCompletedV1,
    BatchEssaysReadyV1,
    BatchValidationErrorsV1,
)
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.class_events import (
    ClassCreatedV1,
    StudentCreatedV1,
)
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.essay_lifecycle_events import EssayStudentAssociationUpdatedV1
from common_core.events.file_events import (
    EssayContentProvisionedV1,
    EssayValidationFailedV1,
)
from common_core.events.file_management_events import (
    BatchFileAddedV1,
    BatchFileRemovedV1,
)
from common_core.events.nlp_events import BatchAuthorMatchesSuggestedV1
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.events.validation_events import (
    StudentAssociationsConfirmedV1,
    ValidationTimeoutProcessedV1,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import extract_trace_context
from pydantic import BaseModel

from services.websocket_service.protocols import (
    EventProcessorProtocol,
    UserNotificationHandlerProtocol,
)

logger = create_service_logger("websocket.domain_processor")


class DomainEventProcessor(EventProcessorProtocol):
    """Routes domain events to appropriate handlers using a clean mapping table."""

    def __init__(
        self,
        notification_handler: UserNotificationHandlerProtocol,
    ) -> None:
        """Initialize the domain event processor."""
        self.notification_handler = notification_handler
        self.event_routes = self._build_routes()

    def _build_routes(self) -> Dict[str, Tuple[Type[BaseModel], Callable]]:
        """Build clean routing table instead of if-elif chain."""
        return {
            # File operations
            "huleedu.file.batch.file.added.v1": (
                BatchFileAddedV1,
                self.notification_handler.handle_batch_file_added,
            ),
            "huleedu.file.batch.file.removed.v1": (
                BatchFileRemovedV1,
                self.notification_handler.handle_batch_file_removed,
            ),
            # Batch lifecycle
            "huleedu.batch.essays.ready.v1": (
                BatchEssaysReadyV1,
                self.notification_handler.handle_batch_essays_ready,
            ),
            "huleedu.batch.validation.errors.v1": (
                BatchValidationErrorsV1,
                self.notification_handler.handle_batch_validation_errors,
            ),
            "huleedu.batch.content.provisioning.completed.v1": (
                BatchContentProvisioningCompletedV1,
                self.notification_handler.handle_batch_content_provisioning_completed,
            ),
            # Student matching (critical user action)
            "huleedu.batch.author.matches.suggested.v1": (
                BatchAuthorMatchesSuggestedV1,
                self.notification_handler.handle_batch_author_matches_suggested,
            ),
            "huleedu.class.student.associations.confirmed.v1": (
                StudentAssociationsConfirmedV1,
                self.notification_handler.handle_student_associations_confirmed,
            ),
            "huleedu.class.validation.timeout.processed.v1": (
                ValidationTimeoutProcessedV1,
                self.notification_handler.handle_validation_timeout_processed,
            ),
            # Processing results
            "huleedu.cj_assessment.completed.v1": (
                CJAssessmentCompletedV1,
                self.notification_handler.handle_cj_assessment_completed,
            ),
            "huleedu.cj_assessment.failed.v1": (
                CJAssessmentFailedV1,
                self.notification_handler.handle_cj_assessment_failed,
            ),
            "huleedu.essay.spellcheck.completed.v1": (
                SpellcheckResultDataV1,
                self.notification_handler.handle_spellcheck_completed,
            ),
            "huleedu.els.batch.phase.outcome.v1": (
                ELSBatchPhaseOutcomeV1,
                self.notification_handler.handle_batch_phase_outcome,
            ),
            # Essay events
            "huleedu.file.essay.content.provisioned.v1": (
                EssayContentProvisionedV1,
                self.notification_handler.handle_essay_content_provisioned,
            ),
            "huleedu.file.essay.validation.failed.v1": (
                EssayValidationFailedV1,
                self.notification_handler.handle_essay_validation_failed,
            ),
            # Class management
            "huleedu.class.created.v1": (
                ClassCreatedV1,
                self.notification_handler.handle_class_created,
            ),
            "huleedu.class.student.created.v1": (
                StudentCreatedV1,
                self.notification_handler.handle_student_created,
            ),
            "huleedu.class.essay.association.updated.v1": (
                EssayStudentAssociationUpdatedV1,
                self.notification_handler.handle_essay_student_association_updated,
            ),
        }

    async def process_event(self, raw_message: bytes) -> bool:
        """Process a single event - clean and maintainable."""
        try:
            # Parse raw message bytes to dict
            envelope_data = json.loads(raw_message.decode("utf-8"))
            
            # Extract trace context if present
            if envelope_data.get("metadata"):
                extract_trace_context(envelope_data["metadata"])

            event_type = envelope_data["event_type"]
            logger.info(
                f"Processing event: {event_type}",
                extra={
                    "event_id": envelope_data.get("event_id"),
                    "correlation_id": envelope_data.get("correlation_id"),
                },
            )

            # Clean routing using mapping table
            route = self.event_routes.get(event_type)
            if not route:
                logger.warning(
                    f"No handler for event type: {event_type}",
                    extra={"event_id": envelope_data.get("event_id")},
                )
                return False

            # Create event instance and call handler
            event_class, handler = route
            event = event_class(**envelope_data["data"])
            await handler(event)

            logger.info(
                f"Successfully processed event: {event_type}",
                extra={"event_id": envelope_data.get("event_id")},
            )
            return True

        except Exception as e:
            logger.error(
                f"Error processing event: {e}",
                exc_info=True,
                extra={"raw_message": raw_message[:200]},  # Log first 200 bytes for debugging
            )
            return False
```

### **Phase 3: User Notification Handler (2 days)**

#### **3.1 Notification Models**

**File**: `/services/websocket_service/models.py` (New)

```python
"""Pydantic models for WebSocket notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from common_core.websocket_enums import WebSocketEventCategory, NotificationPriority


class BaseNotification(BaseModel):
    """Base notification model for all WebSocket messages."""
    
    event: str = Field(..., description="Event type identifier")
    category: WebSocketEventCategory = Field(..., description="Event category")
    priority: NotificationPriority = Field(default=NotificationPriority.STANDARD)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str = Field(..., description="Target user ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event-specific data")


class BatchProgressNotification(BaseNotification):
    """Notification for batch processing progress updates."""
    
    category: WebSocketEventCategory = Field(default=WebSocketEventCategory.BATCH_PROGRESS)
    batch_id: str = Field(..., description="Batch identifier")
    phase: Optional[str] = Field(None, description="Processing phase")
    status: str = Field(..., description="Current status")
    

class ProcessingResultNotification(BaseNotification):
    """Notification for processing completion results."""
    
    category: WebSocketEventCategory = Field(default=WebSocketEventCategory.PROCESSING_RESULTS)
    batch_id: str = Field(..., description="Batch identifier")
    service: str = Field(..., description="Processing service name")
    results_available: bool = Field(..., description="Whether results are ready")
    

class FileOperationNotification(BaseNotification):
    """Notification for file upload/removal operations."""
    
    category: WebSocketEventCategory = Field(default=WebSocketEventCategory.FILE_OPERATIONS)
    batch_id: str = Field(..., description="Batch identifier")
    file_upload_id: str = Field(..., description="File upload identifier")
    filename: str = Field(..., description="File name")
    

class ClassManagementNotification(BaseNotification):
    """Notification for class/student management operations."""
    
    category: WebSocketEventCategory = Field(default=WebSocketEventCategory.CLASS_MANAGEMENT)
    class_id: Optional[str] = Field(None, description="Class identifier")
    student_id: Optional[str] = Field(None, description="Student identifier")
    

class ValidationErrorNotification(BaseNotification):
    """Notification for validation errors."""
    
    category: WebSocketEventCategory = Field(default=WebSocketEventCategory.SYSTEM_ALERTS)
    priority: NotificationPriority = Field(default=NotificationPriority.IMMEDIATE)
    batch_id: str = Field(..., description="Batch identifier")
    errors: List[Dict[str, Any]] = Field(..., description="Validation error details")
```

#### **3.2 User Notification Handler (Notification Layer)**

**File**: `/services/websocket_service/implementations/user_notification_handler.py` (Rename from file_notification_handler.py)

```python
"""User notification handler - transforms domain events into user notifications."""

from __future__ import annotations

from common_core.events.batch_coordination_events import (
    BatchContentProvisioningCompletedV1,
    BatchEssaysReadyV1,
    BatchValidationErrorsV1,
)
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.class_events import ClassCreatedV1, StudentCreatedV1
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.essay_lifecycle_events import EssayStudentAssociationUpdatedV1
from common_core.events.file_events import (
    EssayContentProvisionedV1,
    EssayValidationFailedV1,
)
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from common_core.events.nlp_events import BatchAuthorMatchesSuggestedV1
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.events.validation_events import (
    StudentAssociationsConfirmedV1,
    ValidationTimeoutProcessedV1,
)
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.models import (
    BatchProgressNotification,
    FileOperationNotification,
    ProcessingResultNotification,
    ValidationErrorNotification,
)
from services.websocket_service.protocols import UserNotificationHandlerProtocol

logger = create_service_logger("websocket.user_notifications")


class UserNotificationHandler(UserNotificationHandlerProtocol):
    """Transforms domain events into user notifications."""

    def __init__(self, redis_client: AtomicRedisClientProtocol) -> None:
        """Initialize the notification handler."""
        self.redis_client = redis_client

    # File operations
    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None:
        """Transform file add event into user notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "file_upload_id": event.file_upload_id,
            "filename": event.filename,
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="batch_file_added",
            data=notification_data,
            category=WebSocketEventCategory.FILE_OPERATIONS,
        )

    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None:
        """Transform file removal event into user notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "file_upload_id": event.file_upload_id,
            "filename": event.filename,
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="batch_file_removed",
            data=notification_data,
            category=WebSocketEventCategory.FILE_OPERATIONS,
        )

    # Batch lifecycle
    async def handle_batch_essays_ready(self, event: BatchEssaysReadyV1) -> None:
        """Handle batch readiness notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "essay_count": event.essay_count,
            "message": f"Batch ready with {event.essay_count} essays",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="batch_essays_ready",
            data=notification_data,
            category=WebSocketEventCategory.BATCH_PROGRESS,
        )

    async def handle_batch_validation_errors(self, event: BatchValidationErrorsV1) -> None:
        """Handle batch validation errors - immediate attention required."""
        notification_data = {
            "batch_id": event.batch_id,
            "validation_errors": event.validation_errors,
            "error_count": len(event.validation_errors),
            "message": f"{len(event.validation_errors)} validation errors require attention",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="batch_validation_errors",
            data=notification_data,
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=NotificationPriority.IMMEDIATE,
        )

    # Student matching - CRITICAL USER ACTION REQUIRED
    async def handle_batch_author_matches_suggested(self, event: BatchAuthorMatchesSuggestedV1) -> None:
        """Critical: Notify user they have 24 hours to confirm student matches."""
        notification_data = {
            "batch_id": event.batch_id,
            "class_id": event.class_id,
            "suggested_matches": [
                {
                    "essay_id": match.essay_id,
                    "suggested_student_id": match.suggested_student_id,
                    "confidence_score": match.confidence_score,
                }
                for match in event.suggested_matches
            ],
            "confirmation_deadline": event.confirmation_deadline.isoformat(),
            "confirmation_url": f"/batches/{event.batch_id}/confirm-matches",
            "message": f"Please review {len(event.suggested_matches)} student matches within 24 hours",
            "action_required": True,
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="student_matches_suggested",
            data=notification_data,
            category=WebSocketEventCategory.STUDENT_WORKFLOW,
            priority=NotificationPriority.IMMEDIATE,
        )

    async def handle_student_associations_confirmed(self, event: StudentAssociationsConfirmedV1) -> None:
        """Notify user that student associations have been confirmed."""
        notification_data = {
            "batch_id": event.batch_id,
            "confirmed_count": event.confirmed_count,
            "message": f"{event.confirmed_count} student associations confirmed",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="student_associations_confirmed",
            data=notification_data,
            category=WebSocketEventCategory.STUDENT_WORKFLOW,
        )

    async def handle_validation_timeout_processed(self, event: ValidationTimeoutProcessedV1) -> None:
        """Notify user that validation timeout has been processed."""
        notification_data = {
            "batch_id": event.batch_id,
            "auto_confirmed_count": event.auto_confirmed_count,
            "message": f"Validation timeout: {event.auto_confirmed_count} matches auto-confirmed",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="validation_timeout_processed",
            data=notification_data,
            category=WebSocketEventCategory.STUDENT_WORKFLOW,
        )

    # Processing results
    async def handle_spellcheck_completed(self, event: SpellcheckResultDataV1) -> None:
        """Handle spellcheck completion notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "essay_id": event.essay_id,
            "corrections_count": event.corrections_count,
            "message": f"Spellcheck completed: {event.corrections_count} corrections made",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="spellcheck_completed",
            data=notification_data,
            category=WebSocketEventCategory.PROCESSING_RESULTS,
        )

    async def handle_cj_assessment_completed(self, event: CJAssessmentCompletedV1) -> None:
        """Handle CJ assessment completion notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "assessment_id": event.assessment_id,
            "comparison_count": event.comparison_count,
            "message": "CJ Assessment completed successfully",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="cj_assessment_completed",
            data=notification_data,
            category=WebSocketEventCategory.PROCESSING_RESULTS,
        )

    async def handle_cj_assessment_failed(self, event: CJAssessmentFailedV1) -> None:
        """Handle CJ assessment failure notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "error_message": event.error_message,
            "message": "CJ Assessment failed - manual review required",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="cj_assessment_failed",
            data=notification_data,
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=NotificationPriority.IMMEDIATE,
        )

    async def handle_batch_phase_outcome(self, event: ELSBatchPhaseOutcomeV1) -> None:
        """Handle batch phase outcome notification."""
        notification_data = {
            "batch_id": event.batch_id,
            "phase": event.phase,
            "outcome_status": event.outcome_status,
            "message": f"Phase {event.phase} completed with status: {event.outcome_status}",
            "timestamp": event.timestamp.isoformat(),
        }

        await self._publish_notification(
            user_id=event.user_id,
            event_type="batch_phase_outcome",
            data=notification_data,
            category=WebSocketEventCategory.BATCH_PROGRESS,
        )

    # Additional handlers for remaining events...
    # (essay events, class management, etc. following same pattern)

    async def _publish_notification(
        self,
        user_id: str,
        event_type: str,
        data: dict,
        category: WebSocketEventCategory = WebSocketEventCategory.BATCH_PROGRESS,
        priority: NotificationPriority = NotificationPriority.STANDARD,
    ) -> None:
        """Centralized notification publishing with error handling."""
        try:
            # Add category and priority to notification data
            notification_data = {
                **data,
                "category": category.value,
                "priority": priority.value,
            }

            await self.redis_client.publish_user_notification(
                user_id=user_id,
                event_type=event_type,
                data=notification_data,
            )

            logger.info(
                f"Published {event_type} notification",
                extra={
                    "user_id": user_id,
                    "event_type": event_type,
                    "category": category.value,
                    "priority": priority.value,
                },
            )

        except Exception as e:
            logger.error(
                f"Error publishing {event_type} notification: {e}",
                exc_info=True,
                extra={"user_id": user_id, "event_type": event_type},
            )
            raise
```

### **Phase 4: Protocol Definitions (1 day)**

#### **4.1 Three-Layer Protocol Definitions**

**File**: `/services/websocket_service/protocols.py` (Replace existing)

```python
"""Protocol definitions for WebSocket service three-layer architecture."""

from __future__ import annotations

from typing import Protocol

# Import all event types
from common_core.events.batch_coordination_events import (
    BatchContentProvisioningCompletedV1,
    BatchEssaysReadyV1,
    BatchValidationErrorsV1,
)
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.class_events import ClassCreatedV1, StudentCreatedV1
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.essay_lifecycle_events import EssayStudentAssociationUpdatedV1
from common_core.events.file_events import (
    EssayContentProvisionedV1,
    EssayValidationFailedV1,
)
from common_core.events.file_management_events import (
    BatchFileAddedV1,
    BatchFileRemovedV1,
)
from common_core.events.nlp_events import BatchAuthorMatchesSuggestedV1
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.events.validation_events import (
    StudentAssociationsConfirmedV1,
    ValidationTimeoutProcessedV1,
)


class KafkaConsumerProtocol(Protocol):
    """Protocol for Kafka event consumer - infrastructure layer."""

    async def start_consumer(self) -> None:
        """Start consuming events from Kafka."""
        ...

    async def stop_consumer(self) -> None:
        """Stop the Kafka consumer gracefully."""
        ...


class EventProcessorProtocol(Protocol):
    """Protocol for domain event processor - domain layer."""

    async def process_event(self, raw_message: bytes) -> bool:
        """Process a single event and return success status."""
        ...


class UserNotificationHandlerProtocol(Protocol):
    """Protocol for user notification handler - notification layer."""

    # File operations
    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None: ...
    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None: ...

    # Batch lifecycle
    async def handle_batch_essays_ready(self, event: BatchEssaysReadyV1) -> None: ...
    async def handle_batch_validation_errors(self, event: BatchValidationErrorsV1) -> None: ...
    async def handle_batch_content_provisioning_completed(
        self, event: BatchContentProvisioningCompletedV1
    ) -> None: ...

    # Student matching workflow
    async def handle_batch_author_matches_suggested(
        self, event: BatchAuthorMatchesSuggestedV1
    ) -> None: ...
    async def handle_student_associations_confirmed(
        self, event: StudentAssociationsConfirmedV1
    ) -> None: ...
    async def handle_validation_timeout_processed(
        self, event: ValidationTimeoutProcessedV1
    ) -> None: ...

    # Processing results
    async def handle_spellcheck_completed(self, event: SpellcheckResultDataV1) -> None: ...
    async def handle_cj_assessment_completed(self, event: CJAssessmentCompletedV1) -> None: ...
    async def handle_cj_assessment_failed(self, event: CJAssessmentFailedV1) -> None: ...
    async def handle_batch_phase_outcome(self, event: ELSBatchPhaseOutcomeV1) -> None: ...

    # Essay events
    async def handle_essay_content_provisioned(self, event: EssayContentProvisionedV1) -> None: ...
    async def handle_essay_validation_failed(self, event: EssayValidationFailedV1) -> None: ...

    # Class management
    async def handle_class_created(self, event: ClassCreatedV1) -> None: ...
    async def handle_student_created(self, event: StudentCreatedV1) -> None: ...
    async def handle_essay_student_association_updated(
        self, event: EssayStudentAssociationUpdatedV1
    ) -> None: ...


# Existing protocols maintained for compatibility
class WebSocketManagerProtocol(Protocol):
    """Protocol for WebSocket connection management."""

    async def connect(self, websocket: object, user_id: str) -> bool: ...
    async def disconnect(self, websocket: object, user_id: str) -> None: ...
    def get_connection_count(self, user_id: str) -> int: ...


class MessageListenerProtocol(Protocol):
    """Protocol for Redis message listening."""

    async def start_listening(self, user_id: str, websocket: object) -> None: ...


class JWTValidatorProtocol(Protocol):
    """Protocol for JWT token validation."""

    async def validate_token(self, token: str) -> str: ...
```

### **Phase 5: Testing Extension (1 day)**

#### **5.1 Extended E2E Test Coverage**

**File**: `/tests/functional/test_e2e_websocket_comprehensive.py` (New)

```python
"""
Comprehensive E2E tests for extended WebSocket service functionality.

Tests the complete event flow for all supported event types.
"""

import pytest
from tests.functional.test_e2e_file_event_kafka_flow import TestEndToEndFileEventKafkaFlow


class TestComprehensiveWebSocketEventFlow(TestEndToEndFileEventKafkaFlow):
    """Extended E2E tests for comprehensive WebSocket event handling."""

    @pytest.mark.asyncio
    @pytest.mark.docker
    @pytest.mark.timeout(60)
    async def test_batch_progress_event_flow(
        self,
        redis_client,
        kafka_consumer,
        http_session,
    ) -> None:
        """Test batch progress events flow through Kafka to WebSocket notifications."""
        # Test implementation following existing pattern...
        
    @pytest.mark.asyncio
    @pytest.mark.docker 
    @pytest.mark.timeout(60)
    async def test_processing_results_event_flow(
        self,
        redis_client,
        kafka_consumer,
        http_session,
    ) -> None:
        """Test processing results events flow through Kafka to WebSocket notifications."""
        # Test implementation following existing pattern...
        
    # Additional test methods for each event category...
```

## 📊 **SUCCESS CRITERIA**

### **Technical Validation**
✅ **Event Coverage**: 2 → 17 events (850% increase)  
✅ **Three-Layer Architecture**: Clean separation of infrastructure, domain, and notification layers  
✅ **Protocol Adherence**: Zero concrete dependencies in business logic  
✅ **Service Library Usage**: All infrastructure through `huleedu_service_libs`  
✅ **Error Handling**: Structured error handling with `HuleEduError`  
✅ **Testing Coverage**: E2E validation for all new event types  

### **Integration Validation**
✅ **Frontend Integration**: WebSocket events ready for React/SvelteKit frontends  
✅ **Common Core Enums**: All cross-cutting enums registered properly  
✅ **Pydantic Models**: All data structures use Pydantic v2  
✅ **Redis Channels**: Maintain current channel strategy  
✅ **Kafka Topics**: Systematic topic expansion following naming conventions  

### **Performance Validation**
✅ **Connection Scalability**: Support 1000+ concurrent WebSocket connections  
✅ **Notification Latency**: Sub-100ms delivery for all event types  
✅ **Memory Efficiency**: No memory leaks under sustained load  
✅ **Idempotency**: All event processing remains idempotent  

## 🚀 **IMPLEMENTATION TIMELINE**

**Day 1**: Phase 1 (Common Core enum registration)  
**Days 2-4**: Phase 2 (Three-layer architecture implementation)  
**Days 5-6**: Phase 3 (User notification handler)  
**Day 7**: Phase 4 (Protocol definitions)  
**Days 8-9**: Phase 5 (Testing extension)  
**Day 10**: Integration testing with frontend  

**Total Effort**: 9 days implementation + 1 day integration testing

## 🛡️ **RISK MITIGATION**

### **Architectural Risks**
- **Mitigation**: Strict adherence to existing patterns prevents architectural drift
- **Validation**: Comprehensive protocol compliance testing

### **Performance Risks**
- **Mitigation**: Systematic load testing with real Redis/Kafka infrastructure
- **Validation**: Memory profiling and connection stress testing

### **Integration Risks**
- **Mitigation**: Continuous E2E testing throughout implementation
- **Validation**: Frontend integration testing with SvelteKit WebSocket client

## 📈 **EXPECTED BUSINESS IMPACT**

### **User Experience Improvements**
- **Real-time Batch Progress**: Immediate visibility into processing status
- **Critical Action Alerts**: 24-hour student matching confirmations with countdown
- **Instant Result Notifications**: Processing completion alerts as they happen
- **Live Error Feedback**: Immediate validation error notifications requiring action

### **Technical Benefits**
- **Clean Architecture**: Three-layer separation enables independent scaling
- **Maintainable Routing**: Event routing table eliminates if-elif sprawl
- **Reduced Support Load**: Self-service status visibility
- **Future-Proof Foundation**: Easy addition of new event types

## 🔄 **Migration Strategy**

### **From Current to Target Architecture**
1. **Rename existing files** (breaking change, coordinate with deployment):
   - `file_event_consumer.py` → `kafka_event_consumer.py`
   - `file_notification_handler.py` → `user_notification_handler.py`

2. **Introduce new layer** (non-breaking):
   - Add `domain_event_processor.py` between consumer and handler

3. **Update DI wiring** (deployment coordination required):
   - Wire three components in `di.py`
   - Update `startup_setup.py` to use new consumer

4. **Gradual event addition** (non-breaking):
   - Start with critical events (student matching, validation errors)
   - Add processing results next
   - Complete with class management events

---

**This three-layer architecture provides the clean separation, maintainability, and scalability required for comprehensive real-time notifications while avoiding overengineering and maintaining strict architectural compliance.**