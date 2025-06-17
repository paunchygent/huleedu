# EPIC: CLIENT_INTERFACE_AND_DYNAMIC_PIPELINE_V1

TASK TICKET: Implement API Gateway and Batch Conductor Service
Status: Ready for Development

Owner: @LeadDeveloper

Labels: architecture, feature, api-gateway, bcs, quart, fastapi

Depends On: PIPELINE_HARDENING_V1.1 (Event Idempotency)

## 1. Objective

To enable client-facing interactions and dynamic, state-aware pipeline generation by implementing two new core services: the API Gateway Service and the Batch Conductor Service (BCS). This will decouple the client from the internal orchestration logic and introduce intelligent, dependency-aware pipeline construction, moving the platform closer to the vision outlined in the PRD.

## 2. Key Deliverables

### 2.1. API Gateway Service

[ ] A new FastAPI-based microservice (api_gateway_service).

[ ] An HTTP endpoint (POST /v1/batches/{batch_id}/pipelines) to accept user requests for processing pipelines, with automatic interactive documentation (Swagger UI).

[ ] Logic to validate client requests and publish a ClientBatchPipelineRequestV1 command to a new Kafka topic.

[ ] Standardized health (/healthz) and metrics (/metrics) endpoints.

[ ] Integration into docker-compose.yml and the monorepo build/test process.

### 2.2. Batch Conductor Service (BCS)

[ ] A new Quart-based microservice (batch_conductor_service).

[ ] An internal HTTP endpoint (POST /internal/v1/pipelines/define) that accepts a batch ID and a requested pipeline.

[ ] Core logic to query the Essay Lifecycle Service (ELS) for the current state of essays in the specified batch.

[ ] A rules engine to determine necessary prerequisite processing steps (e.g., ensuring spellcheck runs before ai_feedback).

[ ] Logic to return a final, ordered list of pipeline phases to the caller (BOS).

### 2.3. Modifications to Existing Services

[ ] Batch Orchestrator Service (BOS):

[ ] Create a new Kafka consumer to listen for ClientBatchPipelineRequestV1 commands from the API Gateway.

[ ] Implement an HTTP client to call the new BCS endpoint to resolve the full pipeline definition.

[ ] Update the BatchEssaysReadyHandler to transition the batch to a READY_FOR_PIPELINE_EXECUTION state instead of immediately initiating a pipeline.

[ ] common_core:

[ ] Define new Pydantic models for the ClientBatchPipelineRequestV1 command and the BCSPipelineDefinitionResponseV1 response.

### 3. Architectural Implementation Plan

3.1. New Event & Command Contracts
ClientBatchPipelineRequestV1
This command is published by the API Gateway to Kafka when a user requests a pipeline to be run on a batch.

File: common_core/src/common_core/events/client_commands.py

from __future__ import annotations
import uuid
from pydantic import BaseModel, Field

class ClientBatchPipelineRequestV1(BaseModel):
    """
    Command sent from the API Gateway to signal a user's request to run a
    processing pipeline on an existing, fully uploaded batch.
    """
    batch_id: str = Field(description="The unique identifier of the target batch.")
    requested_pipeline: str = Field(description="The final pipeline the user wants to run (e.g., 'ai_feedback').")
    # user_id: str - To be added once authentication is in place.

BCSPipelineDefinitionRequestV1
This is the internal request model for the HTTP call from BOS to BCS.

File: services/batch_conductor_service/api_models.py

from __future__ import annotations
from pydantic import BaseModel

class BCSPipelineDefinitionRequestV1(BaseModel):
    batch_id: str
    requested_pipeline: str

BCSPipelineDefinitionResponseV1
This is the internal response model for the HTTP call from BOS to BCS.

File: services/batch_conductor_service/api_models.py

from __future__ import annotations
from typing import List
from pydantic import BaseModel

class BCSPipelineDefinitionResponseV1(BaseModel):
    batch_id: str
    final_pipeline: List[str]

### 3.2. API Gateway Service Implementation (api_gateway_service)

This service acts as the new front door. It will be built using FastAPI to leverage its automatic API documentation capabilities.

Directory Structure: Create services/api_gateway_service/ mirroring other services, but with a simpler app.py structure idiomatic to FastAPI.

Dependencies (pyproject.toml): fastapi, uvicorn[standard], dishka, huleedu-common-core, huleedu-service-libs.

Core Logic:

di.py: Provides KafkaBus and Settings.

app.py: FastAPI application setup, DI integration, startup/shutdown events, and route definitions.

Endpoint: POST /v1/batches/{batch_id}/pipelines

## In services/api_gateway_service/app.py

from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import JSONResponse
from dishka.integrations.fastapi import DishkaRoute, FromDishka

from huleedu_service_libs.kafka_client import KafkaBus
from common_core.events.client_commands import ClientBatchPipelineRequestV1
from common_core.events.envelope import EventEnvelope
import uuid

### ... (app setup, DI setup, startup/shutdown events)

## The route for handling pipeline requests

@app.post("/v1/batches/{batch_id}/pipelines", status_code=status.HTTP_202_ACCEPTED)
async def run_pipeline(
    batch_id: str,
    command_data: ClientBatchPipelineRequestV1, # FastAPI automatically validates the request body
    kafka_bus: FromDishka[KafkaBus]
):
    # FastAPI ensures command_data is a valid Pydantic model
    # We just need to ensure the batch_id from the path matches
    if batch_id != command_data.batch_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Path batch_id does not match request body batch_id."}
        )

    correlation_id = uuid.uuid4()
    envelope = EventEnvelope[ClientBatchPipelineRequestV1](
        event_type="client.batch.pipeline.request.v1",
        source_service="api-gateway",
        correlation_id=correlation_id,
        data=command_data
    )

    await kafka_bus.publish("huleedu.commands.batch.pipeline.v1", envelope)

    return {
        "message": "Pipeline request accepted.",
        "batch_id": command_data.batch_id,
        "correlation_id": str(correlation_id)
    }

### 3.3. Batch Conductor Service (BCS) Implementation (batch_conductor_service)

This is the new "pipeline brain." It is an internal HTTP service queried by BOS. It will be built with Quart for consistency with other internal services.

Directory Structure: Create services/batch_conductor_service/ mirroring batch_orchestrator_service.

Dependencies (pyproject.toml): quart, hypercorn, dishka, aiohttp, huleedu-common-core.

Core Logic:

di.py: Provides an aiohttp.ClientSession for calling ELS.

pipeline_rules.py: Contains the logic for dependency resolution (e.g., {'ai_feedback': ['spellcheck']}).

api/pipeline_routes.py: Implements the internal endpoint for BOS.

Endpoint: POST /internal/v1/pipelines/define

### In services/batch_conductor_service/api/pipeline_routes.py

from quart import Blueprint, request, jsonify
from quart_dishka import inject
from dishka import FromDishka
import aiohttp
from .api_models import BCSPipelineDefinitionRequestV1, BCSPipelineDefinitionResponseV1

pipeline_bp = Blueprint("pipeline_routes", __name__)

### Hardcoded rules for this implementation

PIPELINE_DEPENDENCIES = {
    "ai_feedback": ["spellcheck"],
    "cj_assessment": ["spellcheck"]
}

@pipeline_bp.route("/internal/v1/pipelines/define", methods=["POST"])
@inject
async def define_pipeline(session: FromDishka[aiohttp.ClientSession]):
    req_data = await request.get_json()
    validated_req = BCSPipelineDefinitionRequestV1(**req_data)
    batch_id = validated_req.batch_id
    requested_pipeline = validated_req.requested_pipeline

    # 1. Query ELS for current essay statuses
    els_url = f"http://essay_lifecycle_service:6001/v1/batches/{batch_id}/status"
    async with session.get(els_url) as response:
        if response.status != 200:
            return jsonify({"error": "Failed to get batch state from ELS"}), 502
        els_status_data = await response.json()

    # 2. Analyze statuses and apply rules
    # (Simplified logic for demonstration)
    final_pipeline = []
    dependencies = PIPELINE_DEPENDENCIES.get(requested_pipeline, [])

    # For each dependency, check if it's already done. If not, add it.
    # This logic would be more robust in production.
    if "spellcheck" in dependencies:
        # A more robust check would see if ALL essays are in SPELLCHECKED_SUCCESS state
        # For now, we assume if any are not, we need to run it.
        final_pipeline.append("spellcheck")

    final_pipeline.append(requested_pipeline)

    response_model = BCSPipelineDefinitionResponseV1(
        batch_id=batch_id,
        final_pipeline=final_pipeline
    )
    return jsonify(response_model.model_dump()), 200

### 3.4. Modifications to Batch Orchestrator Service (BOS)

New Kafka Consumer: Create a new consumer function in kafka_consumer.py to listen on huleedu.commands.batch.pipeline.v1.

Handler Logic:

On receiving ClientBatchPipelineRequestV1, extract batch_id and requested_pipeline.

Make a POST request to the BCS internal endpoint (/internal/v1/pipelines/define).

Receive the BCSPipelineDefinitionResponseV1 containing the final_pipeline list.

Save this final_pipeline list to the ProcessingPipelineState for the batch.

Initiate the first step of the final_pipeline using the existing initiator logic.

## 4. Updated System Workflow

sequenceDiagram
    participant User
    participant API Gateway
    participant Kafka
    participant BOS as Batch Orchestrator
    participant BCS as Batch Conductor
    participant ELS as Essay Lifecycle

    User->>API Gateway: POST /v1/batches/{id}/pipelines (req: "ai_feedback")
    API Gateway->>Kafka: Publishes ClientBatchPipelineRequestV1
    Kafka-->>BOS: Consumes command

    BOS->>BCS: POST /internal/pipelines/define (batch_id, "ai_feedback")
    BCS->>ELS: GET /v1/batches/{id}/status
    ELS-->>BCS: Returns essay statuses (all are "READY_FOR_PROCESSING")
    BCS-->>BOS: Returns final_pipeline: ["spellcheck", "ai_feedback"]

    BOS->>BOS: Stores final_pipeline in its state
    BOS->>Kafka: Publishes BatchServiceSpellcheckInitiateCommand
    Kafka-->>ELS: ELS processes spellcheck...
    ELS->>Kafka: ELS publishes ELSBatchPhaseOutcome for spellcheck
    Kafka-->>BOS: BOS consumes spellcheck outcome...

    BOS->>Kafka: Publishes BatchServiceAIFeedbackInitiateCommand
    Kafka-->>ELS: ELS processes AI feedback...
    Note right of ELS: Cycle continues...

## 5. Validation & Testing Strategy

Unit Tests:

Test the BCS pipeline_rules.py logic in isolation.

Test the new Pydantic command/response models.

Integration Tests:

Test the API Gateway's ability to publish to Kafka correctly.

Test BOS's ability to call the BCS HTTP endpoint and process the response.

Test BCS's ability to call the ELS HTTP endpoint.

End-to-End (E2E) Test:

Create a new test in tests/functional/ that simulates the full sequence diagram above.

The test will:

Register a batch and upload files (setup).

Call the new API Gateway endpoint.

Monitor Kafka to ensure BOS correctly initiates spellcheck first, not ai_feedback.

(Optional) Mock the spellcheck service's response to trigger the next phase and verify ai_feedback is initiated correctly.

## 6. Acceptance Criteria

[ ] All new services (api_gateway_service, batch_conductor_service) are created with the correct directory structure and dependencies.

[ ] The API Gateway has a functioning endpoint that publishes commands to Kafka.

[ ] The BCS has a functioning internal endpoint that correctly queries ELS and returns a dependency-aware pipeline.

[ ] BOS is modified to consume the new command, call the BCS, and initiate the correct first phase of the returned pipeline.

[ ] All new code is linted, type-checked, and includes unit tests with sufficient coverage.

[ ] A new E2E test successfully validates the updated orchestration flow.
