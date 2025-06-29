import pytest
from httpx import ASGITransport, AsyncClient, Response
from respx import MockRouter

from services.api_gateway_service.app.main import create_app
from services.api_gateway_service.auth import get_current_user_id
from services.api_gateway_service.config import settings

USER_ID = "test-user-123"
BATCH_ID = "test-batch-abc-123"


@pytest.fixture
def mock_auth():
    def get_test_user():
        return USER_ID

    return get_test_user


@pytest.fixture
async def client(unified_container, mock_auth):
    app = create_app()
    app.dependency_overrides[get_current_user_id] = mock_auth
    from dishka.integrations.fastapi import setup_dishka

    setup_dishka(unified_container, app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_batch_status_success(client: AsyncClient, respx_mock: MockRouter):
    """Test successful retrieval of batch status with correct ownership."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    mock_route = respx_mock.get(aggregator_url).mock(
        return_value=Response(200, json={"user_id": USER_ID, "status": "completed"})
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "available",
        "details": {"status": "completed"},
    }
    assert mock_route.called


@pytest.mark.asyncio
async def test_get_batch_status_ownership_failure(client: AsyncClient, respx_mock: MockRouter):
    """Test for 403 Forbidden when the batch belongs to a different user."""
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    respx_mock.get(aggregator_url).mock(
        return_value=Response(200, json={"user_id": "another-user-id", "status": "completed"})
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 403
    assert response.json() == {"detail": "Access denied"}


@pytest.mark.asyncio
async def test_get_batch_status_not_found_fallback_success(
    client: AsyncClient, respx_mock: MockRouter
):
    """Test fallback to BOS when batch is not in the aggregator."""
    settings.HANDLE_MISSING_BATCHES = "query_bos"
    aggregator_url = f"{settings.RESULT_AGGREGATOR_URL}/internal/v1/batches/{BATCH_ID}/status"
    bos_url = f"{settings.BOS_URL}/internal/v1/batches/{BATCH_ID}/pipeline-state"

    respx_mock.get(aggregator_url).mock(return_value=Response(404))
    
    # Mock realistic BOS ProcessingPipelineState data
    bos_data = {
        "batch_id": BATCH_ID,
        "user_id": USER_ID,
        "requested_pipelines": ["spellcheck"],
        "last_updated": "2024-01-15T10:30:00Z",
        "spellcheck": {
            "status": "in_progress",
            "essay_counts": {
                "total": 5,
                "successful": 2,
                "failed": 0,
                "pending_dispatch_or_processing": 3
            },
            "started_at": "2024-01-15T10:00:00Z",
            "completed_at": None
        }
    }
    
    bos_mock = respx_mock.get(bos_url).mock(
        return_value=Response(200, json=bos_data)
    )

    response = await client.get(f"/v1/batches/{BATCH_ID}/status")

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["status"] == "processing"
    
    # Verify transformed data structure
    details = response_data["details"]
    assert details["batch_id"] == BATCH_ID
    assert details["user_id"] == USER_ID
    assert details["overall_status"] == "processing"  # BatchClientStatus.PROCESSING.value
    assert details["essay_count"] == 5
    assert details["completed_essay_count"] == 2
    assert details["failed_essay_count"] == 0
    assert details["requested_pipeline"] == "spellcheck"
    assert details["current_phase"] == "SPELLCHECK"
    assert details["essays"] == []  # Cannot populate from BOS
    assert details["last_updated"] == "2024-01-15T10:30:00Z"
    
    assert bos_mock.called
