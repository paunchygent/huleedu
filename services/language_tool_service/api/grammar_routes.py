"""Grammar check routes for Language Tool Service."""

from __future__ import annotations

import time
from typing import Any

from common_core.api_models.language_tool import GrammarCheckRequest, GrammarCheckResponse
from dishka import FromDishka
from huleedu_service_libs.error_handling import raise_processing_error, raise_validation_error
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import ValidationError
from quart import Blueprint, request
from quart_dishka import inject

from services.language_tool_service.protocols import LanguageToolWrapperProtocol

logger = create_service_logger("language_tool_service.api.grammar")
grammar_bp = Blueprint("grammar_routes", __name__)


def _get_text_length_range(word_count: int) -> str:
    """Categorize text length by word count for metrics."""
    if word_count <= 100:
        return "0-100_words"
    elif word_count <= 250:
        return "101-250_words"
    elif word_count <= 500:
        return "251-500_words"
    elif word_count <= 1000:
        return "501-1000_words"
    elif word_count <= 2000:
        return "1001-2000_words"
    else:
        return "2000+_words"


@grammar_bp.route("/v1/check", methods=["POST"])
@inject
async def check_grammar(
    corr: FromDishka[CorrelationContext],
    language_tool_wrapper: FromDishka[LanguageToolWrapperProtocol],
    metrics: FromDishka[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    """
    Check text for grammar errors using Language Tool.

    This endpoint accepts text content and returns grammar analysis results
    including error categorization and rule-based feedback.

    Args:
        corr: Correlation context for request tracing
        language_tool_wrapper: Language Tool service implementation

    Returns:
        Tuple of (response_dict, status_code)

    Raises:
        HuleEduError: For validation errors, processing failures
    """
    request_start = time.perf_counter()

    # Parse request body
    try:
        request_data = await request.get_json()
        if not request_data:
            raise_validation_error(
                service="language-tool-service",
                operation="grammar_check",
                field="request_body",
                message="Request body is required",
                correlation_id=corr.uuid,
            )

        # Validate request with Pydantic
        grammar_request = GrammarCheckRequest(**request_data)

    except ValidationError as e:
        logger.warning(
            f"Grammar check request validation failed: {e}",
            correlation_id=corr.original,
        )
        # Emit business-specific failure metrics
        metrics["grammar_analysis_total"].labels(
            status="validation_error", text_length_range="unknown"
        ).inc()
        metrics["api_errors_total"].labels(
            endpoint="/v1/check", error_type="validation_error"
        ).inc()

        raise_validation_error(
            service="language-tool-service",
            operation="grammar_check",
            field="request_format",
            message=f"Invalid request format: {str(e)}",
            correlation_id=corr.uuid,
        )
    except Exception as e:
        logger.error(
            f"Failed to parse grammar check request: {e}",
            correlation_id=corr.original,
        )
        # Emit business-specific failure metrics
        metrics["grammar_analysis_total"].labels(
            status="parsing_error", text_length_range="unknown"
        ).inc()
        metrics["api_errors_total"].labels(endpoint="/v1/check", error_type="parsing_error").inc()

        raise_validation_error(
            service="language-tool-service",
            operation="grammar_check",
            field="json_body",
            message="Invalid JSON in request body",
            correlation_id=corr.uuid,
        )

    # Start grammar analysis timing
    analysis_start = time.perf_counter()
    text_length = len(grammar_request.text)
    word_count = len(grammar_request.text.split())
    text_length_range = _get_text_length_range(word_count)

    logger.info(
        f"Starting grammar check for {word_count} words ({text_length} characters), "
        f"language: {grammar_request.language}",
        correlation_id=corr.original,
    )

    try:
        # Call Language Tool wrapper for grammar analysis
        raw_errors = await language_tool_wrapper.check_text(
            text=grammar_request.text,
            correlation_context=corr,
            language=grammar_request.language,
            request_options=grammar_request.to_languagetool_payload(),
        )

        # Process analysis results
        analysis_end = time.perf_counter()
        analysis_duration = analysis_end - analysis_start
        processing_time_ms = max(1, int((analysis_end - request_start) * 1000))

        # Calculate aggregated statistics
        total_errors = len(raw_errors)
        category_counts: dict[str, int] = {}
        rule_counts: dict[str, int] = {}

        for error in raw_errors:
            if not isinstance(error, dict):
                continue

            category_key: str | None = None

            category_id_value = error.get("category_id")
            if isinstance(category_id_value, str) and category_id_value:
                category_key = category_id_value
            else:
                error_type_raw = error.get("type")
                if isinstance(error_type_raw, dict):
                    type_name = error_type_raw.get("typeName")
                    if isinstance(type_name, str) and type_name:
                        category_key = type_name
                elif isinstance(error.get("category_name"), str):
                    category_key = error["category_name"]
                elif isinstance(error.get("category"), str):
                    category_key = error["category"]

            if not category_key:
                category_key = "UNKNOWN"

            category_counts[category_key] = category_counts.get(category_key, 0) + 1

            rule_id_value = error.get("rule_id")
            if not isinstance(rule_id_value, str) or not rule_id_value:
                rule_info = error.get("rule")
                if isinstance(rule_info, dict):
                    fallback_rule = rule_info.get("id")
                    if isinstance(fallback_rule, str) and fallback_rule:
                        rule_id_value = fallback_rule

            rule_key = rule_id_value if isinstance(rule_id_value, str) and rule_id_value else "UNKNOWN_RULE"
            rule_counts[rule_key] = rule_counts.get(rule_key, 0) + 1

        # Create response
        response = GrammarCheckResponse(
            errors=raw_errors,
            total_grammar_errors=total_errors,
            grammar_category_counts=category_counts,
            grammar_rule_counts=rule_counts,
            language=grammar_request.language,
            processing_time_ms=processing_time_ms,
        )

        # Emit business-specific success metrics
        metrics["grammar_analysis_total"].labels(
            status="success", text_length_range=text_length_range
        ).inc()
        metrics["grammar_analysis_duration_seconds"].observe(analysis_duration)

        logger.info(
            f"Grammar check completed: {total_errors} errors found in {processing_time_ms}ms",
            correlation_id=corr.original,
        )

        return response.model_dump(mode="json"), 200

    except Exception as e:
        analysis_end = time.perf_counter()
        analysis_duration = analysis_end - analysis_start

        logger.error(
            f"Grammar analysis failed after {analysis_duration:.3f}s: {e}",
            correlation_id=corr.original,
            exc_info=True,
        )

        # Emit business-specific failure metrics
        metrics["grammar_analysis_total"].labels(
            status="processing_error", text_length_range=text_length_range
        ).inc()
        metrics["grammar_analysis_duration_seconds"].observe(analysis_duration)
        metrics["api_errors_total"].labels(
            endpoint="/v1/check", error_type="processing_error"
        ).inc()

        raise_processing_error(
            service="language-tool-service",
            operation="grammar_check",
            message=f"Grammar analysis failed: {str(e)}",
            correlation_id=corr.uuid,
        )
