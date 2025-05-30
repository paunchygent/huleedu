"""Batch processing routes for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, Union

import aiohttp
from config import settings
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter
from protocols import BatchEventPublisherProtocol
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckRequestedDataV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata

logger = create_service_logger("bos.api.batch")
batch_bp = Blueprint("batch_routes", __name__, url_prefix="/v1/batches")

CONTENT_SERVICE_URL = settings.CONTENT_SERVICE_URL
OUTPUT_KAFKA_TOPIC_SPELLCHECK_REQUEST = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)

# Global metrics reference (initialized in app.py)
BATCH_OPERATIONS: Optional[Counter] = None


def set_batch_operations_metric(metric: Counter) -> None:
    """Set the batch operations metric reference."""
    global BATCH_OPERATIONS
    BATCH_OPERATIONS = metric


"""
This endpoint is not used in production. It is used to test the DI functionality of
the service. The request endpoints will be removed as soon as request events owned by
Essay Lifecycle Service are implemented.
"""
@batch_bp.route("/trigger-spellcheck-test", methods=["POST"])
@inject
async def trigger_spellcheck_test_endpoint(
    event_publisher: FromDishka[BatchEventPublisherProtocol],
) -> Union[Response, tuple[Response, int]]:
    """Test endpoint to trigger a spellcheck request using DI."""
    try:
        batch_id = str(uuid.uuid4())
        essay_id_1 = str(uuid.uuid4())
        correlation_id_val = uuid.uuid4()

        dummy_essay_text = "This is a tset essay with a teh and anothre recieve error for testing."
        original_text_storage_id: Optional[str] = None

        async with aiohttp.ClientSession() as http_session:
            logger.info(
                f"Posting dummy essay text to content service for batch {batch_id}, "
                f"essay {essay_id_1}"
            )
            async with http_session.post(
                CONTENT_SERVICE_URL, data=dummy_essay_text.encode("utf-8")
            ) as response:
                if response.status == 201:
                    data = await response.json()
                    original_text_storage_id = data.get("storage_id")
                    logger.info(f"Dummy essay stored, content_id: {original_text_storage_id}")
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to store dummy essay text: {response.status} - {error_text}"
                    )
                    if BATCH_OPERATIONS:
                        BATCH_OPERATIONS.labels(operation="test_spellcheck", status="failed").inc()
                    return (
                        jsonify({"error": f"Failed to store dummy essay: {response.status}"}),
                        500,
                    )

        if not original_text_storage_id:
            if BATCH_OPERATIONS:
                BATCH_OPERATIONS.labels(operation="test_spellcheck", status="failed").inc()
            return (
                jsonify({"error": "Could not get storage_id for dummy essay text"}),
                500,
            )

        essay_ref = EntityReference(entity_id=essay_id_1, entity_type="essay", parent_id=batch_id)

        system_meta_for_request = SystemProcessingMetadata(
            entity=essay_ref,
            event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.PENDING,
        )

        spellcheck_request_data = SpellcheckRequestedDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
            entity_ref=essay_ref,
            status=EssayStatus.AWAITING_SPELLCHECK,
            system_metadata=system_meta_for_request,
            text_storage_id=original_text_storage_id,
        )

        envelope = EventEnvelope[SpellcheckRequestedDataV1](
            event_type=OUTPUT_KAFKA_TOPIC_SPELLCHECK_REQUEST,
            source_service="batch-service",
            correlation_id=correlation_id_val,
            data=spellcheck_request_data,
        )

        # Use the injected event publisher
        await event_publisher.publish_batch_event(envelope)

        logger.info(
            f"Published SpellcheckRequestedDataV1 for essay {essay_id_1}, "
            f"event_id {envelope.event_id}"
        )

        if BATCH_OPERATIONS:
            BATCH_OPERATIONS.labels(operation="test_spellcheck", status="success").inc()

        return (
            jsonify(
                {
                    "message": "Test spellcheck request published",
                    "batch_id": batch_id,
                    "essay_id": essay_id_1,
                    "original_text_storage_id": original_text_storage_id,
                    "event_id": str(envelope.event_id),
                    "correlation_id": str(correlation_id_val),
                }
            ),
            202,
        )

    except Exception as e:
        logger.error(f"Error in trigger_spellcheck_test: {e}", exc_info=True)
        if BATCH_OPERATIONS:
            BATCH_OPERATIONS.labels(operation="test_spellcheck", status="error").inc()
        return jsonify({"error": "Failed to trigger test spellcheck request."}), 500
