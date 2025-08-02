# WebSocket Service Core Evolution: Robust and Extendible Real-Time Architecture

---

**Task ID**: `WS-CORE-001`  
**Status**: `Ready for Implementation`  
**Author**: `System Architect`  
**Date**: `2025-08-01`  
**Priority**: `HIGH`

---

## 🎯 **OBJECTIVE**

Evolve the WebSocket service from handling 2 file events (3% coverage) to 13 critical user-facing events (20% coverage) using a **robust, minimalist core expansion** that strictly adheres to HuleEdu architectural mandates while avoiding overengineering.

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

### **Design Philosophy: ROBUST + EXTENDIBLE + MINIMAL**

**ROBUST**: Build on proven patterns, maintain architectural compliance  
**EXTENDIBLE**: Systematic expansion without architectural debt  
**MINIMAL**: Zero overengineering, strict YAGNI adherence  

### **Expansion Approach: Pattern Replication**
- **Extend existing `FileEventConsumer`** rather than creating new abstractions
- **Add handlers to existing `FileNotificationHandler`** following established patterns
- **Reuse Redis channel strategy** with minimal enhancements
- **Maintain current testing patterns** with systematic coverage expansion

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

### **Phase 2: Event Consumer Extension (2 days)**

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
    CJ_ASSESSMENT_COMPLETED_TOPIC: str = Field(
        default="huleedu.cj_assessment.completed.v1",
        description="CJ Assessment completion events"
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
```

#### **2.2 Extended Event Consumer**

**File**: `/services/websocket_service/implementations/file_event_consumer.py` (Enhanced)

```python
# Extend existing consumer with additional topics
class FileEventConsumer(FileEventConsumerProtocol):
    def __init__(
        self,
        settings: Settings,
        notification_handler: FileNotificationHandlerProtocol,
        redis_client: AtomicRedisClientProtocol,
        kafka_consumer_factory: Callable[..., KafkaConsumerProtocol] | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        # ... existing initialization ...
        
        # Extended topics to consume (systematic expansion)
        self.topics = [
            # Existing file events
            self.settings.BATCH_FILE_ADDED_TOPIC,
            self.settings.BATCH_FILE_REMOVED_TOPIC,
            
            # Phase 1 expansion: Critical user-facing events
            self.settings.BATCH_ESSAYS_READY_TOPIC,
            self.settings.BATCH_VALIDATION_ERRORS_TOPIC,
            self.settings.BATCH_CONTENT_PROVISIONING_COMPLETED_TOPIC,
            self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            self.settings.SPELLCHECK_COMPLETED_TOPIC,
            self.settings.ELS_BATCH_PHASE_OUTCOME_TOPIC,
            self.settings.ESSAY_CONTENT_PROVISIONED_TOPIC,
            self.settings.ESSAY_VALIDATION_FAILED_TOPIC,
            self.settings.CLASS_CREATED_TOPIC,
            self.settings.STUDENT_CREATED_TOPIC,
            self.settings.ESSAY_STUDENT_ASSOCIATION_UPDATED_TOPIC,
        ]

    async def process_message(self, msg: ConsumerRecord) -> bool:
        """Process a single Kafka message - EXTENDED for additional event types."""
        try:
            # Parse raw message bytes to dict
            raw_message = msg.value.decode("utf-8")
            envelope_data = json.loads(raw_message)
            
            # Extract trace context if present
            if envelope_data.get("metadata"):
                extract_trace_context(envelope_data["metadata"])

            logger.info(
                f"Processing event: {envelope_data['event_type']}",
                extra={
                    "event_id": envelope_data.get("event_id"),
                    "correlation_id": envelope_data.get("correlation_id"),
                },
            )

            # Route to appropriate handler based on event type
            # SYSTEMATIC EXTENSION: Add new event types following existing pattern
            event_type = envelope_data["event_type"]
            
            if event_type == "huleedu.file.batch.file.added.v1":
                added_event = BatchFileAddedV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_file_added(added_event)
                
            elif event_type == "huleedu.file.batch.file.removed.v1":
                removed_event = BatchFileRemovedV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_file_removed(removed_event)
                
            elif event_type == "huleedu.batch.essays.ready.v1":
                ready_event = BatchEssaysReadyV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_essays_ready(ready_event)
                
            elif event_type == "huleedu.batch.validation.errors.v1":
                validation_event = BatchValidationErrorsV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_validation_errors(validation_event)
                
            elif event_type == "huleedu.batch.content.provisioning.completed.v1":
                content_event = BatchContentProvisioningCompletedV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_content_provisioning_completed(content_event)
                
            elif event_type == "huleedu.cj_assessment.completed.v1":
                cj_event = CJAssessmentCompletedV1(**envelope_data["data"])
                await self.notification_handler.handle_cj_assessment_completed(cj_event)
                
            elif event_type == "huleedu.essay.spellcheck.completed.v1":
                spell_event = SpellcheckResultDataV1(**envelope_data["data"])
                await self.notification_handler.handle_spellcheck_completed(spell_event)
                
            elif event_type == "huleedu.els.batch.phase.outcome.v1":
                phase_event = ELSBatchPhaseOutcomeV1(**envelope_data["data"])
                await self.notification_handler.handle_batch_phase_outcome(phase_event)
                
            elif event_type == "huleedu.essay.content.provisioned.v1":
                essay_content_event = EssayContentProvisionedV1(**envelope_data["data"])
                await self.notification_handler.handle_essay_content_provisioned(essay_content_event)
                
            elif event_type == "huleedu.essay.validation.failed.v1":
                essay_validation_event = EssayValidationFailedV1(**envelope_data["data"])
                await self.notification_handler.handle_essay_validation_failed(essay_validation_event)
                
            elif event_type == "huleedu.class.created.v1":
                class_event = ClassCreatedV1(**envelope_data["data"])
                await self.notification_handler.handle_class_created(class_event)
                
            elif event_type == "huleedu.student.created.v1":
                student_event = StudentCreatedV1(**envelope_data["data"])
                await self.notification_handler.handle_student_created(student_event)
                
            elif event_type == "huleedu.essay.student.association.updated.v1":
                association_event = EssayStudentAssociationUpdatedV1(**envelope_data["data"])
                await self.notification_handler.handle_essay_student_association_updated(association_event)
                
            else:
                logger.warning(
                    f"Unknown event type: {event_type}",
                    extra={"event_id": envelope_data.get("event_id")},
                )
                return False

            logger.info(
                f"Successfully processed event: {event_type}",
                extra={"event_id": envelope_data.get("event_id")},
            )
            return True

        except Exception as e:
            logger.error(
                f"Error processing event: {e}",
                exc_info=True,
                extra={
                    "topic": msg.topic,
                    "partition": msg.partition,
                    "offset": msg.offset,
                },
            )
            return False
```

### **Phase 3: Notification Handler Extension (2 days)**

#### **3.1 Enhanced Notification Models**

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

#### **3.2 Extended Notification Handler**

**File**: `/services/websocket_service/implementations/file_notification_handler.py` (Enhanced)

```python
"""
File notification handler for WebSocket Service - EXTENDED for comprehensive event handling.
"""

from __future__ import annotations

from common_core.events.batch_coordination_events import (
    BatchEssaysReadyV1,
    BatchValidationErrorsV1, 
    BatchContentProvisioningCompletedV1,
)
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.file_events import (
    EssayContentProvisionedV1,
    EssayValidationFailedV1,
)
from common_core.events.class_events import ClassCreatedV1, StudentCreatedV1
from common_core.events.essay_lifecycle_events import EssayStudentAssociationUpdatedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1

from services.websocket_service.models import (
    BatchProgressNotification,
    ProcessingResultNotification,
    FileOperationNotification,
    ClassManagementNotification,
    ValidationErrorNotification,
)


class FileNotificationHandler(FileNotificationHandlerProtocol):
    """Handler for converting events to Redis notifications - SYSTEMATIC EXTENSION."""

    def __init__(self, redis_client: AtomicRedisClientProtocol) -> None:
        """Initialize the notification handler."""
        self.redis_client = redis_client

    # EXISTING METHODS (unchanged)
    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None:
        """Handle BatchFileAddedV1 event and publish notification to Redis."""
        try:
            notification = FileOperationNotification(
                event="batch_file_added",
                user_id=event.user_id,
                batch_id=event.batch_id,
                file_upload_id=event.file_upload_id,
                filename=event.filename,
                data={
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                    "filename": event.filename,
                    "timestamp": event.timestamp.isoformat(),
                },
            )

            await self.redis_client.publish_user_notification(
                user_id=event.user_id,
                event_type="batch_file_added",
                data=notification.data,
            )

            logger.info(
                f"Published batch_file_added notification for user {event.user_id}",
                extra={
                    "user_id": event.user_id,
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                },
            )

        except Exception as e:
            logger.error(
                f"Error publishing batch_file_added notification: {e}",
                exc_info=True,
                extra={
                    "user_id": event.user_id,
                    "batch_id": event.batch_id,
                    "file_upload_id": event.file_upload_id,
                },
            )
            raise

    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None:
        """Handle BatchFileRemovedV1 event and publish notification to Redis."""
        # ... existing implementation unchanged ...

    # NEW METHODS: SYSTEMATIC EXTENSION FOLLOWING ESTABLISHED PATTERNS
    async def handle_batch_essays_ready(self, event: BatchEssaysReadyV1) -> None:
        """Handle batch readiness notification."""
        try:
            notification = BatchProgressNotification(
                event="batch_essays_ready",
                user_id=event.user_id,
                batch_id=event.batch_id,
                status="ready",
                data={
                    "batch_id": event.batch_id,
                    "essay_count": event.essay_count,
                    "timestamp": event.timestamp.isoformat(),
                },
            )

            await self.redis_client.publish_user_notification(
                user_id=event.user_id,
                event_type="batch_essays_ready",
                data=notification.data,
            )

            logger.info(f"Published batch_essays_ready notification for user {event.user_id}")

        except Exception as e:
            logger.error(f"Error publishing batch_essays_ready notification: {e}", exc_info=True)
            raise

    async def handle_batch_validation_errors(self, event: BatchValidationErrorsV1) -> None:
        """Handle batch validation errors notification."""
        try:
            notification = ValidationErrorNotification(
                event="batch_validation_errors",
                user_id=event.user_id,
                batch_id=event.batch_id,
                errors=event.validation_errors,
                data={
                    "batch_id": event.batch_id,
                    "validation_errors": event.validation_errors,
                    "timestamp": event.timestamp.isoformat(),
                },
            )

            await self.redis_client.publish_user_notification(
                user_id=event.user_id,
                event_type="batch_validation_errors",
                data=notification.data,
            )

            logger.info(f"Published batch_validation_errors notification for user {event.user_id}")

        except Exception as e:
            logger.error(f"Error publishing batch_validation_errors notification: {e}", exc_info=True)
            raise

    async def handle_cj_assessment_completed(self, event: CJAssessmentCompletedV1) -> None:
        """Handle CJ assessment completion notification."""
        try:
            notification = ProcessingResultNotification(
                event="cj_assessment_completed",
                user_id=event.user_id,
                batch_id=event.batch_id,
                service="cj_assessment",
                results_available=True,
                data={
                    "batch_id": event.batch_id,
                    "assessment_id": event.assessment_id,
                    "comparison_count": event.comparison_count,
                    "timestamp": event.timestamp.isoformat(),
                },
            )

            await self.redis_client.publish_user_notification(
                user_id=event.user_id,
                event_type="cj_assessment_completed",
                data=notification.data,
            )

            logger.info(f"Published cj_assessment_completed notification for user {event.user_id}")

        except Exception as e:
            logger.error(f"Error publishing cj_assessment_completed notification: {e}", exc_info=True)
            raise

    # Additional handler methods following the same pattern...
    # (spellcheck_completed, batch_phase_outcome, etc.)
```

### **Phase 4: Protocol Extension (1 day)**

#### **4.1 Extended Notification Handler Protocol**

**File**: `/services/websocket_service/protocols.py` (Enhanced)

```python
# Add to existing protocols
class FileNotificationHandlerProtocol(Protocol):
    """Protocol for file notification handling - EXTENDED for comprehensive events."""

    # Existing methods
    async def handle_batch_file_added(self, event: BatchFileAddedV1) -> None: ...
    async def handle_batch_file_removed(self, event: BatchFileRemovedV1) -> None: ...
    
    # Extended methods for Phase 1 events
    async def handle_batch_essays_ready(self, event: BatchEssaysReadyV1) -> None: ...
    async def handle_batch_validation_errors(self, event: BatchValidationErrorsV1) -> None: ...
    async def handle_batch_content_provisioning_completed(self, event: BatchContentProvisioningCompletedV1) -> None: ...
    async def handle_cj_assessment_completed(self, event: CJAssessmentCompletedV1) -> None: ...
    async def handle_spellcheck_completed(self, event: SpellcheckResultDataV1) -> None: ...
    async def handle_batch_phase_outcome(self, event: ELSBatchPhaseOutcomeV1) -> None: ...
    async def handle_essay_content_provisioned(self, event: EssayContentProvisionedV1) -> None: ...
    async def handle_essay_validation_failed(self, event: EssayValidationFailedV1) -> None: ...
    async def handle_class_created(self, event: ClassCreatedV1) -> None: ...
    async def handle_student_created(self, event: StudentCreatedV1) -> None: ...
    async def handle_essay_student_association_updated(self, event: EssayStudentAssociationUpdatedV1) -> None: ...
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
✅ **Event Coverage**: 2 → 13 events (650% increase)  
✅ **Architectural Compliance**: All new code follows established patterns  
✅ **Protocol Adherence**: Zero concrete dependencies in business logic  
✅ **Service Library Usage**: All infrastructure through `huleedu_service_libs`  
✅ **Error Handling**: Structured error handling with `HuleEduError`  
✅ **Testing Coverage**: E2E validation for all new event types  

### **Integration Validation**
✅ **SvelteKit Frontend**: WebSocket events integrate with frontend skeleton plan  
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

**Week 1**: Phases 1-2 (Enum registration + Event consumer extension)  
**Week 2**: Phases 3-4 (Notification handler + Protocol extension)  
**Week 3**: Phase 5 + Integration testing with SvelteKit frontend  

**Total Effort**: 7 days implementation + 3 days integration testing

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
- **Instant Result Notifications**: Eliminate email-only result delivery  
- **Live Error Feedback**: Immediate validation error notifications
- **Class Management Updates**: Real-time student/class management

### **Technical Benefits**
- **Reduced Support Load**: Self-service status visibility
- **Improved Platform Engagement**: Real-time experience drives usage
- **Architectural Foundation**: Scalable base for future event integration
- **Development Velocity**: Established patterns enable rapid expansion

---

**This evolution maintains the robust architectural foundation while providing systematic, minimal expansion that delivers maximum user value without overengineering.**