"""Regression tests for download response construction."""

from __future__ import annotations

from services.content_service.api.content_routes import _build_download_response


def test_build_download_response_preserves_parameters() -> None:
    """Content-Type parameters survive when building the response."""

    response = _build_download_response(b"payload", "text/plain; charset=utf-8")

    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"


def test_build_download_response_defaults_to_octet_stream() -> None:
    """Missing content type falls back to application/octet-stream."""

    response = _build_download_response(b"payload", None)

    assert response.headers["Content-Type"] == "application/octet-stream"
