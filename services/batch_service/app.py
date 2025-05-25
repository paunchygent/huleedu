import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Union

import aiohttp
from dotenv import load_dotenv
from quart import Quart, Response, jsonify

load_dotenv()

from huleedu_service_libs.kafka_client import KafkaBus

from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckRequestedDataV1
from common_core.metadata_models import EntityReference, SystemProcessingMetadata

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Quart(__name__)
KAFKA_BUS_CLIENT_ID = "batch-service-producer"
app.config["KAFKA_BUS"] = None

CONTENT_SERVICE_URL = os.getenv("CONTENT_SERVICE_URL", "http://content_service:8000/v1/content")
OUTPUT_KAFKA_TOPIC_SPELLCHECK_REQUEST = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)


@app.before_serving
async def startup() -> None:
    try:
        bus = KafkaBus(client_id=KAFKA_BUS_CLIENT_ID)
        await bus.start()
        app.config["KAFKA_BUS"] = bus
        logger.info("Batch Service KafkaBus started.")
    except Exception as e:
        logger.critical(f"Failed to start KafkaBus for Batch Service: {e}", exc_info=True)


@app.after_serving
async def shutdown() -> None:
    bus = app.config.get("KAFKA_BUS")
    if bus:
        await bus.stop()
        logger.info("Batch Service KafkaBus stopped.")


@app.post("/v1/batches/trigger-spellcheck-test")
async def trigger_spellcheck_test_endpoint() -> Union[Response, tuple[Response, int]]:
    bus: Optional[KafkaBus] = app.config.get("KAFKA_BUS")
    if not bus:
        logger.error("KafkaBus not initialized in Batch Service.")
        return jsonify({"error": "Service not ready, Kafka producer unavailable."}), 503

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
                    return (
                        jsonify({"error": f"Failed to store dummy essay: {response.status}"}),
                        500,
                    )

        if not original_text_storage_id:
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

        await bus.publish(OUTPUT_KAFKA_TOPIC_SPELLCHECK_REQUEST, envelope, key=essay_id_1)

        logger.info(
            f"Published SpellcheckRequestedDataV1 for essay {essay_id_1}, "
            f"event_id {envelope.event_id}"
        )
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
        return jsonify({"error": "Failed to trigger test spellcheck request."}), 500


@app.get("/healthz")
async def health_check() -> Union[Response, tuple[Response, int]]:
    bus: Optional[KafkaBus] = app.config.get("KAFKA_BUS")
    kafka_status = "connected" if bus and bus._started else "disconnected"
    return (
        jsonify(
            {
                "status": "ok",
                "message": "Batch Service is healthy",
                "kafka_producer": kafka_status,
            }
        ),
        200,
    )
