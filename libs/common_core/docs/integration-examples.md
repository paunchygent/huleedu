# Integration Examples

CJ Assessment Service as canonical implementation reference.

## Service Overview

**Location**: `services/cj_assessment_service/`

**Demonstrates**:
- Event consumption with EventEnvelope deserialization
- Dual-event production (thin + rich)
- Storage references for large payloads
- Error handling with service-specific enums
- Identity threading (user_id/org_id)
- Grade scale registry usage
- Typed result models (EssayResultV1)

## Event Consumption

File: `services/cj_assessment_service/kafka_handlers.py`

```python
from common_core.events.envelope import EventEnvelope
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from typing import Any

class CJKafkaHandler:
    async def handle_assessment_request(self, message: bytes) -> None:
        # Phase 1: Deserialize envelope
        envelope = EventEnvelope[Any].model_validate_json(message)

        # Phase 2: Validate typed event data
        request = ELS_CJAssessmentRequestV1.model_validate(envelope.data)

        # Extract correlation_id for tracing
        correlation_id = envelope.correlation_id

        # Identity threading
        user_id = request.user_id
        org_id = request.org_id

        # Process request
        await self.cj_service.process_batch(
            essays=request.essays_for_cj,
            language=request.language,
            course_code=request.course_code,
            user_id=user_id,
            org_id=org_id,
            correlation_id=correlation_id
        )
```

## Dual-Event Production

File: `services/cj_assessment_service/event_publisher.py`

```python
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    AssessmentResultV1,
    EssayResultV1
)
from common_core.status_enums import ProcessingStage
from common_core.metadata_models import SystemProcessingMetadata

class CJEventPublisher:
    async def publish_completion(
        self,
        batch_id: str,
        job_id: str,
        results: list[ProcessedEssay],
        correlation_id: UUID
    ) -> None:
        # Thin event → ELS
        thin_event = CJAssessmentCompletedV1(
            entity_ref=batch_id,
            status=ProcessingStage.COMPLETED,
            system_metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                processing_stage=ProcessingStage.COMPLETED,
                completed_at=datetime.now(UTC)
            ),
            cj_assessment_job_id=job_id,
            processing_summary={
                "successful": len(results),
                "successful_essay_ids": [r.essay_id for r in results]
            }
        )

        thin_envelope = EventEnvelope[CJAssessmentCompletedV1](
            event_type=topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            source_service="cj_assessment_service",
            correlation_id=correlation_id,
            data=thin_event
        )

        # Rich event → RAS
        rich_event = AssessmentResultV1(
            batch_id=batch_id,
            cj_assessment_job_id=job_id,
            assessment_method="cj_assessment",
            model_used="claude-3-opus",
            model_provider="anthropic",
            essay_results=[
                EssayResultV1(
                    essay_id=r.essay_id,
                    normalized_score=r.score,
                    letter_grade=r.grade,
                    confidence_score=r.confidence,
                    bt_score=r.bt_value,
                    rank=r.rank
                ) for r in results
            ]
        )

        rich_envelope = EventEnvelope[AssessmentResultV1](
            event_type=topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
            source_service="cj_assessment_service",
            correlation_id=correlation_id,
            data=rich_event
        )

        # Publish both
        await self.kafka_bus.publish(
            topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            thin_envelope.model_dump_json().encode('utf-8')
        )
        await self.kafka_bus.publish(
            topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
            rich_envelope.model_dump_json().encode('utf-8')
        )
```

## Storage References

File: `services/cj_assessment_service/content_client.py`

```python
from common_core.metadata_models import StorageReferenceMetadata
from common_core.domain_enums import ContentType

class ContentClient:
    async def fetch_student_prompt(
        self,
        storage_ref: StorageReferenceMetadata,
        correlation_id: UUID
    ) -> str:
        # Extract storage_id from reference
        prompt_ref = storage_ref.references.get(ContentType.STUDENT_PROMPT_TEXT)
        if not prompt_ref:
            raise ValueError("No student prompt reference")

        storage_id = prompt_ref["storage_id"]

        # Fetch from Content Service
        prompt_text = await self.http_client.get(
            f"{self.content_service_url}/fetch/{storage_id}",
            headers={"X-Correlation-ID": str(correlation_id)}
        )
        return prompt_text
```

## Error Handling

File: `services/cj_assessment_service/error_handler.py`

```python
from common_core.error_enums import CJAssessmentErrorCode
from common_core.events.cj_assessment_events import CJAssessmentFailedV1
from common_core.status_enums import ProcessingStage
from common_core.metadata_models import SystemProcessingMetadata

class CJErrorHandler:
    async def publish_failure(
        self,
        batch_id: str,
        job_id: str,
        error: Exception,
        correlation_id: UUID
    ) -> None:
        failure_event = CJAssessmentFailedV1(
            entity_ref=batch_id,
            status=ProcessingStage.FAILED,
            system_metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                processing_stage=ProcessingStage.FAILED,
                error_info={
                    "error_code": CJAssessmentErrorCode.CJ_INSUFFICIENT_COMPARISONS,
                    "error_message": str(error),
                    "error_type": type(error).__name__
                }
            ),
            cj_assessment_job_id=job_id
        )

        envelope = EventEnvelope[CJAssessmentFailedV1](
            event_type=topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED),
            source_service="cj_assessment_service",
            correlation_id=correlation_id,
            data=failure_event
        )

        await self.kafka_bus.publish(
            topic_name(ProcessingEvent.CJ_ASSESSMENT_FAILED),
            envelope.model_dump_json().encode('utf-8')
        )
```

## Grade Scale Usage

File: `services/cj_assessment_service/grade_projector.py`

```python
from common_core.grade_scales import get_scale, validate_grade_for_scale

class GradeProjector:
    async def project_grades(
        self,
        essays: list[EssayWithBTScore],
        anchor_essays: list[AnchorEssay],
        scale_id: str
    ) -> list[GradeProjection]:
        # Get scale metadata
        scale = get_scale(scale_id)

        # Validate anchor grades
        for anchor in anchor_essays:
            if not validate_grade_for_scale(anchor.grade, scale_id):
                raise ValueError(f"Invalid anchor grade: {anchor.grade}")

        # Use population priors
        priors = scale.population_priors or get_uniform_priors(scale_id)

        # Project grades using BT scores + calibration
        projections = []
        for essay in essays:
            grade = self._project_single_grade(
                bt_score=essay.bt_score,
                anchors=anchor_essays,
                priors=priors,
                scale=scale
            )

            # Handle below-lowest
            if scale.allows_below_lowest and essay.bt_score < min_anchor_score:
                grade = scale.below_lowest_grade

            projections.append(GradeProjection(essay_id=essay.id, grade=grade))

        return projections
```

## Identity Threading

File: `services/cj_assessment_service/resource_tracker.py`

```python
from common_core.events.resource_consumption_events import ResourceConsumptionReportedV1

class ResourceTracker:
    async def report_llm_usage(
        self,
        user_id: str,
        org_id: str | None,
        tokens_used: int,
        correlation_id: UUID
    ) -> None:
        consumption_event = ResourceConsumptionReportedV1(
            user_id=user_id,  # From request, for entitlements
            org_id=org_id,    # Org-first attribution
            resource_type="llm_tokens",
            amount=tokens_used,
            timestamp=datetime.now(UTC)
        )

        envelope = EventEnvelope[ResourceConsumptionReportedV1](
            event_type=topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED),
            source_service="cj_assessment_service",
            correlation_id=correlation_id,
            data=consumption_event
        )

        await self.kafka_bus.publish(
            topic_name(ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED),
            envelope.model_dump_json().encode('utf-8')
        )
```

## DI Integration

File: `services/cj_assessment_service/di.py`

```python
from dishka import Provider, Scope, provide
from common_core.events.envelope import EventEnvelope
from common_core.event_enums import ProcessingEvent, topic_name

class CJProvider(Provider):
    @provide(scope=Scope.APP)
    async def provide_kafka_bus(self, settings: Settings) -> KafkaPublisherProtocol:
        kafka_bus = KafkaBus(client_id=f"{settings.SERVICE_NAME}-producer")
        await kafka_bus.start()
        return kafka_bus

    @provide(scope=Scope.REQUEST)
    def provide_event_publisher(
        self,
        kafka_bus: KafkaPublisherProtocol
    ) -> CJEventPublisher:
        return CJEventPublisher(kafka_bus=kafka_bus)
```

## Related

- `services/cj_assessment_service/README.md` - Full service documentation
- `services/cj_assessment_service/` - Complete implementation
- `common_core/events/cj_assessment_events.py` - Event contracts
