"""Unit tests for BOS preflight route.

Covers allowed, denied, and invalid phase scenarios using a lightweight Quart app
and Dishka DI with protocol-based mocks (Rule 042, Rule 070).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator

import pytest
from common_core.domain_enums import CourseCode
from common_core.pipeline_models import PhaseName, PipelineExecutionStatus, ProcessingPipelineState
from common_core.status_enums import BatchStatus
from dishka import Provider, Scope, make_async_container, provide
from quart import Quart
from quart.typing import TestClientProtocol as QuartTestClient
from quart_dishka import QuartDishka

from services.batch_orchestrator_service.api.batch_routes import internal_bp
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.domain.pipeline_credit_guard import (
    CreditCheckOutcome,
    PipelineCreditGuard,
)
from services.batch_orchestrator_service.protocols import (
    BatchConductorClientProtocol,
    BatchRepositoryProtocol,
    EntitlementsServiceProtocol,
)


@dataclass
class _BatchContext:
    batch_id: str
    user_id: str
    org_id: str | None
    expected_essay_count: int = 3


class _MockRepo(BatchRepositoryProtocol):
    def __init__(self, ctx: _BatchContext | None) -> None:
        self._ctx_raw = ctx
        self._ctx_model: BatchRegistrationRequestV1 | None
        if ctx is None:
            self._ctx_model = None
        else:
            self._ctx_model = BatchRegistrationRequestV1(
                expected_essay_count=ctx.expected_essay_count,
                essay_ids=None,
                course_code=CourseCode.ENG5,
                essay_instructions="",
                user_id=ctx.user_id,
                org_id=ctx.org_id,
                class_id=None,
                enable_cj_assessment=True,
                cj_default_llm_model=None,
                cj_default_temperature=None,
            )

    async def get_batch_by_id(self, batch_id: str) -> dict | None:
        return {"id": batch_id} if self._ctx_model is not None else None

    async def create_batch(self, batch_data: dict) -> dict:  # pragma: no cover
        return batch_data

    async def update_batch_status(
        self, batch_id: str, new_status: BatchStatus
    ) -> bool:  # pragma: no cover
        return True

    async def save_processing_pipeline_state(
        self, batch_id: str, pipeline_state: ProcessingPipelineState
    ) -> bool:  # pragma: no cover
        return True

    async def get_processing_pipeline_state(
        self, batch_id: str
    ) -> ProcessingPipelineState | None:  # pragma: no cover
        return None

    async def store_batch_context(
        self,
        batch_id: str,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: str | None = None,
    ) -> bool:  # pragma: no cover
        return True

    async def get_batch_context(self, batch_id: str) -> BatchRegistrationRequestV1 | None:
        return self._ctx_model

    async def store_batch_essays(
        self, batch_id: str, essays: list[Any]
    ) -> bool:  # pragma: no cover
        return True

    async def get_batch_essays(self, batch_id: str) -> list[Any] | None:  # pragma: no cover
        return []

    async def update_phase_status_atomically(
        self,
        batch_id: str,
        phase_name: PhaseName,
        expected_status: PipelineExecutionStatus,
        new_status: PipelineExecutionStatus,
        completion_timestamp: str | None = None,
        correlation_id: str | None = None,
    ) -> bool:  # pragma: no cover
        return True


class _MockBCS(BatchConductorClientProtocol):
    async def resolve_pipeline(
        self, batch_id: str, requested_pipeline: PhaseName, correlation_id: str
    ) -> dict[str, Any]:
        # Echo back a simple resolution that includes requested phase and a fixed follow-up
        return {"final_pipeline": [requested_pipeline.value, PhaseName.AI_FEEDBACK.value]}

    async def report_phase_completion(
        self, batch_id: str, completed_phase: PhaseName, success: bool = True
    ) -> None:  # pragma: no cover
        return None


class _StubEntitlements(EntitlementsServiceProtocol):
    async def check_credits_bulk(
        self,
        user_id: str,
        org_id: str | None,
        requirements: dict[str, int],
        correlation_id: str,
    ) -> dict[str, Any]:
        return {"allowed": True, "available_credits": 9999}


class _AllowGuard(PipelineCreditGuard):
    def __init__(self) -> None:
        super().__init__(entitlements_client=_StubEntitlements(), cost_strategy=None)

    async def evaluate(
        self,
        *,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        batch_context: Any,
        correlation_id: str,
    ) -> CreditCheckOutcome:
        return CreditCheckOutcome(
            allowed=True,
            denial_reason=None,
            required_credits=6,
            available_credits=100,
            resource_breakdown={"cj_comparison": 3, "ai_feedback_generation": 3},
        )


class _DenyGuard(PipelineCreditGuard):
    def __init__(self) -> None:
        super().__init__(entitlements_client=_StubEntitlements(), cost_strategy=None)

    async def evaluate(
        self,
        *,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        batch_context: Any,
        correlation_id: str,
    ) -> CreditCheckOutcome:
        return CreditCheckOutcome(
            allowed=False,
            denial_reason="insufficient_credits",
            required_credits=10,
            available_credits=3,
            resource_breakdown={"cj_comparison": 7, "ai_feedback_generation": 3},
        )


class _RateLimitGuard(PipelineCreditGuard):
    def __init__(self) -> None:
        super().__init__(entitlements_client=_StubEntitlements(), cost_strategy=None)

    async def evaluate(
        self,
        *,
        batch_id: str,
        resolved_pipeline: list[PhaseName],
        batch_context: Any,
        correlation_id: str,
    ) -> CreditCheckOutcome:
        return CreditCheckOutcome(
            allowed=False,
            denial_reason="rate_limit_exceeded",
            required_credits=6,
            available_credits=0,
            resource_breakdown={"cj_comparison": 3, "ai_feedback_generation": 3},
        )


class _TestProvider(Provider):
    scope = Scope.APP

    def __init__(
        self,
        repo: BatchRepositoryProtocol,
        bcs: BatchConductorClientProtocol,
        guard: PipelineCreditGuard,
    ) -> None:
        super().__init__()
        self._repo = repo
        self._bcs = bcs
        self._guard = guard

    @provide
    async def provide_repo(self) -> AsyncIterator[BatchRepositoryProtocol]:
        yield self._repo

    @provide
    async def provide_bcs(self) -> AsyncIterator[BatchConductorClientProtocol]:
        yield self._bcs

    @provide
    async def provide_guard(self) -> AsyncIterator[PipelineCreditGuard]:
        yield self._guard


async def _create_app(provider: Provider) -> tuple[Quart, QuartTestClient]:
    app = Quart(__name__)
    container = make_async_container(provider)
    QuartDishka(app=app, container=container)
    app.register_blueprint(internal_bp)
    client = app.test_client()
    return app, client


@pytest.mark.asyncio
async def test_preflight_allowed_returns_200() -> None:
    ctx = _BatchContext(batch_id="b1", user_id="u1", org_id=None)
    app, client = await _create_app(_TestProvider(_MockRepo(ctx), _MockBCS(), _AllowGuard()))

    resp = await client.post("/internal/v1/batches/b1/pipelines/cj_assessment/preflight")
    assert resp.status_code == 200
    data = await resp.get_json()
    assert data["allowed"] is True
    assert data["resolved_pipeline"][0] == "cj_assessment"
    assert data["required_credits"] == 6


@pytest.mark.asyncio
async def test_preflight_denied_returns_402() -> None:
    ctx = _BatchContext(batch_id="b2", user_id="u2", org_id=None)
    app, client = await _create_app(_TestProvider(_MockRepo(ctx), _MockBCS(), _DenyGuard()))

    resp = await client.post("/internal/v1/batches/b2/pipelines/cj_assessment/preflight")
    assert resp.status_code == 402
    data = await resp.get_json()
    assert data["allowed"] is False
    assert data["denial_reason"] == "insufficient_credits"
    assert data["required_credits"] == 10


@pytest.mark.asyncio
async def test_preflight_invalid_phase_returns_400() -> None:
    ctx = _BatchContext(batch_id="b3", user_id="u3", org_id=None)
    app, client = await _create_app(_TestProvider(_MockRepo(ctx), _MockBCS(), _AllowGuard()))

    resp = await client.post("/internal/v1/batches/b3/pipelines/not_a_phase/preflight")
    assert resp.status_code == 400
    data = await resp.get_json()
    assert "Invalid pipeline phase" in data.get("error", "")


@pytest.mark.asyncio
async def test_preflight_rate_limited_returns_429() -> None:
    ctx = _BatchContext(batch_id="b4", user_id="u4", org_id=None)
    app, client = await _create_app(_TestProvider(_MockRepo(ctx), _MockBCS(), _RateLimitGuard()))

    resp = await client.post("/internal/v1/batches/b4/pipelines/cj_assessment/preflight")
    assert resp.status_code == 429
    data = await resp.get_json()
    assert data["allowed"] is False
    assert data["denial_reason"] == "rate_limit_exceeded"
