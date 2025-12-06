"""Admin routes for LLM Provider Service.

Currently exposes the active mock configuration used by the service.
"""

from __future__ import annotations

from typing import Any, Dict

from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.llm_provider_service.config import MockMode, Settings

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin/mock-mode", methods=["GET"])
@inject
async def get_mock_mode(settings: FromDishka[Settings]) -> Response | tuple[Response, int]:
    """Return the active mock configuration for the running service instance.

    This endpoint is intended for development and CI usage only and acts as
    the single source of truth for mock mode verification in tests.
    """
    logger = create_service_logger("llm_provider_service.api.admin")

    if not settings.ADMIN_API_ENABLED:
        logger.info("Admin API disabled; /admin/mock-mode returning 404")
        return jsonify({"error": "admin_api_disabled"}), 404

    mock_mode: MockMode | None = getattr(settings, "MOCK_MODE", None)
    # Treat DEFAULT as “no explicit profile” for tests that expect
    # cj/eng5-specific modes.
    if mock_mode is None or mock_mode == MockMode.DEFAULT:
        mock_mode_value: str | None = None
    else:
        mock_mode_value = mock_mode.value

    default_provider = settings.DEFAULT_LLM_PROVIDER
    default_provider_value: str
    if hasattr(default_provider, "value"):
        default_provider_value = default_provider.value  # type: ignore[assignment]
    else:
        default_provider_value = str(default_provider)

    payload: Dict[str, Any] = {
        "use_mock_llm": settings.USE_MOCK_LLM,
        "mock_mode": mock_mode_value,
        "default_provider": default_provider_value,
    }

    return jsonify(payload), 200
