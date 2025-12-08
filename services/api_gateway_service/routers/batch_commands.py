"""Batch command routes for API Gateway Service.

Handles batch creation and configuration commands:
- POST /batches/register - Create a new batch
- PATCH /batches/{batch_id}/prompt - Update batch prompt reference
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from common_core.api_models.batch_prompt_amendment import BatchPromptAmendmentRequest
from common_core.api_models.batch_registration import BatchRegistrationRequestV1
from huleedu_service_libs.logging_utils import create_service_logger

from ..config import settings
from ..protocols import HttpClientProtocol, MetricsProtocol
from ._batch_utils import ClientBatchRegistrationRequest

router = APIRouter()
logger = create_service_logger("api_gateway.batch_commands")


@router.post(
    "/batches/register",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Register a new batch",
    description=(
        "Client-facing endpoint for batch registration. API Gateway injects identity "
        "(user_id/org_id) and proxies to the Batch Orchestrator Service."
    ),
)
@inject
async def register_batch(
    registration_request: ClientBatchRegistrationRequest,
    request: Request,
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    org_id: FromDishka[str | None],
    correlation_id: FromDishka[UUID],
):
    """Register a new batch for processing.

    Enriches the client request with authenticated user identity and proxies
    to Batch Orchestrator Service.
    """
    endpoint = "/batches/register"
    with metrics.http_request_duration_seconds.labels(method="POST", endpoint=endpoint).time():
        # Build inter-service contract with identity enrichment
        internal_model = BatchRegistrationRequestV1(
            expected_essay_count=registration_request.expected_essay_count,
            essay_ids=registration_request.essay_ids,
            course_code=registration_request.course_code,
            student_prompt_ref=registration_request.student_prompt_ref,
            user_id=user_id,
            org_id=org_id,
            class_id=registration_request.class_id,
            cj_default_llm_model=registration_request.cj_default_llm_model,
            cj_default_temperature=registration_request.cj_default_temperature,
        )

        # Proxy to BOS with correlation header
        bos_url = f"{settings.BOS_URL}/v1/batches/register"
        response = await http_client.post(
            bos_url,
            json=internal_model.model_dump(mode="json"),
            headers={"X-Correlation-ID": str(correlation_id)},
            timeout=30.0,
        )

        # Pass through status and response body
        try:
            body = response.json()
        except Exception:
            body = {"detail": "Invalid response from BOS"}

        if response.status_code in (200, 202):
            logger.info(
                f"Batch registration proxied: user_id='{user_id}', "
                f"org_id='{org_id}', correlation_id='{correlation_id}'"
            )
        else:
            logger.warning(
                f"BOS registration failed: status={response.status_code}, "
                f"body={body}, correlation_id='{correlation_id}'"
            )
        return JSONResponse(status_code=response.status_code, content=body)


@router.patch(
    "/batches/{batch_id}/prompt",
    status_code=status.HTTP_200_OK,
    summary="Attach or replace the student prompt reference for a batch",
)
@inject
async def amend_batch_prompt(
    batch_id: str,
    amendment_request: BatchPromptAmendmentRequest,
    request: Request,
    http_client: FromDishka[HttpClientProtocol],
    metrics: FromDishka[MetricsProtocol],
    user_id: FromDishka[str],
    org_id: FromDishka[str | None],
    correlation_id: FromDishka[UUID],
):
    """Attach or replace the student prompt reference for a batch.

    Proxies the amendment request to Batch Orchestrator Service with
    identity headers for authorization.
    """
    endpoint = "/batches/{batch_id}/prompt"
    with metrics.http_request_duration_seconds.labels(method="PATCH", endpoint=endpoint).time():
        bos_url = f"{settings.BOS_URL}/v1/batches/{batch_id}/prompt"
        headers = {
            "X-User-ID": user_id,
            "X-Correlation-ID": str(correlation_id),
        }
        if org_id:
            headers["X-Org-ID"] = org_id

        response = await http_client.patch(
            bos_url,
            json=amendment_request.model_dump(mode="json"),
            headers=headers,
        )

        try:
            body = response.json()
        except Exception:
            body = {"detail": "Invalid response from BOS"}

        if response.status_code < 400:
            logger.info(
                "Batch prompt amendment proxied",
                extra={
                    "operation": "proxy_batch_prompt_amend",
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "correlation_id": str(correlation_id),
                },
            )
        else:
            logger.warning(
                "BOS prompt amendment failed",
                extra={
                    "operation": "proxy_batch_prompt_amend",
                    "batch_id": batch_id,
                    "user_id": user_id,
                    "correlation_id": str(correlation_id),
                    "status": response.status_code,
                },
            )

        return JSONResponse(status_code=response.status_code, content=body)
