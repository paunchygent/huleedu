"""
Tests for AGW registration proxy to BOS.

Focus: identity injection, body transformation, correlation forwarding, and status passthrough.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from dishka import make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi.testclient import TestClient

from common_core.domain_enums import CourseCode
from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.tests.test_provider import (
    AuthTestProvider,
    HttpClientTestProvider,
)

USER_ID = "test_user_123"
ORG_ID = "org_abc_999"


@pytest.fixture
def mock_http_client():
    return AsyncMock()


@pytest.fixture(autouse=True)
def _clear_prometheus_registry():
    from prometheus_client import REGISTRY

    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield


@pytest.fixture
async def client_with_org(mock_http_client):
    container = make_async_container(
        HttpClientTestProvider(mock_http_client),
        AuthTestProvider(user_id=USER_ID, org_id=ORG_ID),
        FastapiProvider(),
    )
    app = create_app()
    setup_dishka(container, app)
    with TestClient(app) as client:
        yield client, container, mock_http_client
    await container.close()


def _ok_response(json_body: dict, status_code: int = 202) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


@pytest.mark.asyncio
async def test_registration_proxy_injects_identity_and_calls_bos(client_with_org):
    client, container, mock_http_client = client_with_org
    mock_http_client.post.return_value = _ok_response({"status": "registered", "batch_id": "b1"})

    prompt_ref_payload = {
        "references": {
            "student_prompt_text": {
                "storage_id": "prompt-storage-123",
                "path": "",
            }
        }
    }

    payload = {
        "expected_essay_count": 2,
        "essay_ids": ["e1", "e2"],
        "course_code": CourseCode.SV1.value,
        "class_id": "class-1",
        "cj_default_llm_model": "gpt-4o-mini",
        "cj_default_temperature": 0.5,
        "student_prompt_ref": prompt_ref_payload,
    }

    resp = client.post("/v1/batches/register", json=payload)

    assert resp.status_code in (200, 202)
    # Verify BOS call
    assert mock_http_client.post.called
    args, kwargs = mock_http_client.post.call_args
    assert args[0].endswith("/v1/batches/register")
    body = kwargs["json"]
    assert body["user_id"] == USER_ID
    assert body["org_id"] == ORG_ID
    assert body["expected_essay_count"] == 2
    assert body["course_code"] == CourseCode.SV1.value
    assert body["student_prompt_ref"] == prompt_ref_payload
    assert kwargs["headers"]["X-Correlation-ID"]


@pytest.mark.asyncio
async def test_registration_proxy_handles_bos_error_passthrough(client_with_org):
    client, container, mock_http_client = client_with_org
    mock_http_client.post.return_value = _ok_response(
        {"error": "Validation Error"}, status_code=400
    )

    payload = {
        "expected_essay_count": 1,
        "course_code": CourseCode.SV1.value,
    }

    resp = client.post("/v1/batches/register", json=payload)
    # Ensure we reflect the BOS status and body
    assert resp.status_code == 400
    assert resp.json().get("error") == "Validation Error"
