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

    try:
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
            # Emit failure metrics
            metrics["request_count"].labels(method="POST", endpoint="/v1/check", status="400").inc()
            metrics["grammar_analysis_total"].labels(
                status="validation_error", text_length_range="unknown"
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
            # Emit failure metrics
            metrics["request_count"].labels(method="POST", endpoint="/v1/check", status="400").inc()
            metrics["grammar_analysis_total"].labels(
                status="parsing_error", text_length_range="unknown"
            ).inc()

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
            )

            # Process analysis results
            analysis_end = time.perf_counter()
            analysis_duration = analysis_end - analysis_start
            processing_time_ms = int((analysis_end - request_start) * 1000)

            # Calculate aggregated statistics
            total_errors = len(raw_errors)
            category_counts: dict[str, int] = {}
            rule_counts: dict[str, int] = {}

            for error in raw_errors:
                # Extract category from error type or rule with safe access
                error_type = error.get("type") if isinstance(error.get("type"), dict) else {}
                category = error_type.get("typeName", "UNKNOWN")
                category_counts[category] = category_counts.get(category, 0) + 1

                # Extract rule ID for rule counts with safe access
                error_rule = error.get("rule") if isinstance(error.get("rule"), dict) else {}
                rule_id = error_rule.get("id", "UNKNOWN_RULE")
                rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1

            # Create response
            response = GrammarCheckResponse(
                errors=raw_errors,
                total_grammar_errors=total_errors,
                grammar_category_counts=category_counts,
                grammar_rule_counts=rule_counts,
                language=grammar_request.language,
                processing_time_ms=processing_time_ms,
            )

            # Emit success metrics
            metrics["request_count"].labels(method="POST", endpoint="/v1/check", status="200").inc()
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

            # Emit failure metrics
            metrics["request_count"].labels(method="POST", endpoint="/v1/check", status="500").inc()
            metrics["grammar_analysis_total"].labels(
                status="processing_error", text_length_range=text_length_range
            ).inc()
            metrics["grammar_analysis_duration_seconds"].observe(analysis_duration)

            raise_processing_error(
                service="language-tool-service",
                operation="grammar_check",
                message=f"Grammar analysis failed: {str(e)}",
                correlation_id=corr.uuid,
            )

    finally:
        # Always emit request duration metric
        request_end = time.perf_counter()
        request_duration = request_end - request_start
        metrics["request_duration"].labels(method="POST", endpoint="/v1/check").observe(
            request_duration
        )
