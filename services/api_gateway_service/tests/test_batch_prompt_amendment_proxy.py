"""
Tests for the API Gateway prompt amendment proxy to BOS.

Focus: identity injection, body validation short-circuit, and BOS passthrough.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi.testclient import TestClient

from common_core.api_models.batch_prompt_amendment import BatchPromptAmendmentRequest
from common_core.domain_enums import ContentType
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.tests.test_provider import (
    AuthTestProvider,
    HttpClientTestProvider,
)

USER_ID = "test_user_for_prompt_amendment"
ORG_ID = "org_prompt_amendment"


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield


def _response(json_body: dict, status_code: int = 200) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


@pytest.fixture
async def client_with_mocks():
    mock_http_client = AsyncMock()
    container = make_async_container(
        HttpClientTestProvider(mock_http_client),
        AuthTestProvider(user_id=USER_ID, org_id=ORG_ID),
        FastapiProvider(),
    )
    app = create_app()
    setup_dishka(container, app)
    with TestClient(app) as client:
        yield client, mock_http_client
    await container.close()


def _build_prompt_ref(storage_id: str) -> dict:
    amendment = BatchPromptAmendmentRequest(
        student_prompt_ref={
            "references": {
                ContentType.STUDENT_PROMPT_TEXT: {
                    "storage_id": storage_id,
                    "path": "prompts/example.txt",
                }
            }
        }
    )
    return amendment.model_dump(mode="json")


@pytest.mark.asyncio
async def test_prompt_amendment_proxy_calls_bos(client_with_mocks):
    client, mock_http_client = client_with_mocks
    mock_http_client.patch.return_value = _response({"status": "success", "batch_id": "batch-123"})

    payload = _build_prompt_ref("prompt-storage-456")

    resp = client.patch("/v1/batches/batch-123/prompt", json=payload)

    assert resp.status_code == 200
    args, kwargs = mock_http_client.patch.call_args
    assert args[0].endswith("/v1/batches/batch-123/prompt")
    assert kwargs["json"]["student_prompt_ref"]["references"]["student_prompt_text"]["storage_id"]
    headers = kwargs["headers"]
    assert headers["X-User-ID"] == USER_ID
    assert headers["X-Org-ID"] == ORG_ID
    assert headers["X-Correlation-ID"]


@pytest.mark.asyncio
async def test_prompt_amendment_proxy_validation_short_circuit(client_with_mocks):
    client, mock_http_client = client_with_mocks

    resp = client.patch("/v1/batches/batch-123/prompt", json={})

    # FastAPI validation should handle this before the handler is invoked
    assert resp.status_code in (400, 422)
    assert not mock_http_client.patch.called


@pytest.mark.asyncio
async def test_prompt_amendment_proxy_passthrough_error(client_with_mocks):
    client, mock_http_client = client_with_mocks
    mock_http_client.patch.return_value = _response({"error": "Batch not found"}, status_code=404)

    payload = _build_prompt_ref("missing-storage-id")
    resp = client.patch("/v1/batches/missing-batch/prompt", json=payload)

    assert resp.status_code == 404
    assert resp.json().get("error") == "Batch not found"
