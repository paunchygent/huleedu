"""HTTP client implementation for Batch Conductor Service communication."""

from __future__ import annotations

import json
from typing import Any

import aiohttp
from common_core.pipeline_models import PhaseName
from huleedu_service_libs.logging_utils import create_service_logger

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.protocols import BatchConductorClientProtocol


class BatchConductorClientImpl(BatchConductorClientProtocol):
    """HTTP client for communicating with Batch Conductor Service internal API."""

    def __init__(self, http_session: aiohttp.ClientSession, settings: Settings) -> None:
        """Initialize with HTTP session and configuration."""
        self.http_session = http_session
        self.settings = settings
        self.logger = create_service_logger("bos.client.batch_conductor")

        # Construct full BCS endpoint URL
        self.bcs_endpoint = f"{settings.BCS_BASE_URL}{settings.BCS_PIPELINE_ENDPOINT}"

    async def resolve_pipeline(
        self, batch_id: str, requested_pipeline: PhaseName, correlation_id: str
    ) -> dict[str, Any]:
        """
        Request pipeline resolution from BCS internal API.

        Args:
            batch_id: The unique identifier of the target batch
            requested_pipeline: The final pipeline phase the user wants to run
            correlation_id: The correlation ID from the original request for event tracking

        Returns:
            BCS response containing resolved pipeline and analysis

        Raises:
            aiohttp.ClientError: If HTTP communication fails
            ValueError: If BCS returns an error response
        """
        # Prepare request payload following BCS API contract
        request_data = {
            "batch_id": batch_id,
            "requested_pipeline": requested_pipeline.value,  # Convert enum to string for API
            "correlation_id": correlation_id,  # Pass correlation_id to BCS for event tracking
        }

        self.logger.info(
            "Requesting pipeline resolution from BCS",
            extra={
                "batch_id": batch_id,
                "requested_pipeline": requested_pipeline.value,
                "correlation_id": correlation_id,
                "bcs_endpoint": self.bcs_endpoint,
            },
        )

        try:
            # Make HTTP POST request to BCS
            async with self.http_session.post(
                self.bcs_endpoint,
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=self.settings.BCS_REQUEST_TIMEOUT),
                headers={"Content-Type": "application/json"},
            ) as response:
                response_text = await response.text()

                # Check for HTTP error status
                if response.status >= 400:
                    error_msg = f"BCS returned error status {response.status}: {response_text}"
                    self.logger.error(
                        error_msg,
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "correlation_id": correlation_id,
                            "status_code": response.status,
                            "response_text": response_text,
                        },
                    )
                    raise ValueError(error_msg)

                # Parse JSON response
                try:
                    response_data = json.loads(response_text)
                except json.JSONDecodeError as e:
                    error_msg = f"BCS returned invalid JSON: {e}"
                    self.logger.error(
                        error_msg,
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "correlation_id": correlation_id,
                            "response_text": response_text,
                        },
                    )
                    raise ValueError(error_msg) from e

                # Validate response structure
                if not isinstance(response_data, dict):
                    error_msg = "BCS response is not a valid object"
                    self.logger.error(
                        error_msg,
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "correlation_id": correlation_id,
                            "response_data": response_data,
                        },
                    )
                    raise ValueError(error_msg)

                # Check for required fields in response
                required_fields = ["batch_id", "final_pipeline"]
                missing_fields = [field for field in required_fields if field not in response_data]
                if missing_fields:
                    error_msg = f"BCS response missing required fields: {missing_fields}"
                    self.logger.error(
                        error_msg,
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "correlation_id": correlation_id,
                            "response_data": response_data,
                        },
                    )
                    raise ValueError(error_msg)

                # Validate final_pipeline is a list
                if not isinstance(response_data["final_pipeline"], list):
                    error_msg = "BCS response final_pipeline is not a list"
                    self.logger.error(
                        error_msg,
                        extra={
                            "batch_id": batch_id,
                            "requested_pipeline": requested_pipeline,
                            "correlation_id": correlation_id,
                            "final_pipeline": response_data["final_pipeline"],
                        },
                    )
                    raise ValueError(error_msg)

                self.logger.info(
                    "Successfully received pipeline resolution from BCS",
                    extra={
                        "batch_id": batch_id,
                        "requested_pipeline": requested_pipeline,
                        "correlation_id": correlation_id,
                        "final_pipeline": response_data["final_pipeline"],
                        "pipeline_length": len(response_data["final_pipeline"]),
                    },
                )

                return response_data

        except aiohttp.ClientError as e:
            error_msg = f"HTTP communication with BCS failed: {e}"
            self.logger.error(
                error_msg,
                extra={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "correlation_id": correlation_id,
                    "bcs_endpoint": self.bcs_endpoint,
                },
                exc_info=True,
            )
            raise

        except Exception as e:
            error_msg = f"Unexpected error during BCS communication: {e}"
            self.logger.error(
                error_msg,
                extra={
                    "batch_id": batch_id,
                    "requested_pipeline": requested_pipeline,
                    "correlation_id": correlation_id,
                    "bcs_endpoint": self.bcs_endpoint,
                },
                exc_info=True,
            )
            raise

    async def report_phase_completion(
        self,
        batch_id: str,
        completed_phase: PhaseName,
        success: bool = True,
    ) -> None:
        """
        Report phase completion to BCS for tracking and dependency resolution.

        This enables BCS to:
        1. Track which phases have been completed for a batch
        2. Skip completed phases in subsequent pipeline requests
        3. Support multi-pipeline workflows efficiently

        Args:
            batch_id: The unique identifier of the batch
            completed_phase: The phase that has completed
            success: Whether the phase completed successfully

        Note: This is a best-effort operation - failures are logged but don't block
        pipeline progression to maintain resilience.
        """
        # Construct phase completion endpoint
        completion_endpoint = f"{self.settings.BCS_BASE_URL}/internal/v1/phases/complete"

        # Prepare request payload
        request_data = {
            "batch_id": batch_id,
            "phase_name": completed_phase.value,
            "success": success,
        }

        self.logger.info(
            f"Reporting phase completion to BCS: {completed_phase.value} for batch {batch_id}",
            extra={
                "batch_id": batch_id,
                "phase": completed_phase.value,
                "success": success,
                "endpoint": completion_endpoint,
            },
        )

        try:
            # Make HTTP POST request to BCS
            async with self.http_session.post(
                completion_endpoint,
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=5),  # Short timeout for non-blocking
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status >= 400:
                    response_text = await response.text()
                    self.logger.warning(
                        f"BCS phase completion report failed with status {response.status}",
                        extra={
                            "batch_id": batch_id,
                            "phase": completed_phase.value,
                            "status_code": response.status,
                            "response": response_text,
                        },
                    )
                else:
                    self.logger.info(
                        "Successfully reported phase completion to BCS",
                        extra={
                            "batch_id": batch_id,
                            "phase": completed_phase.value,
                        },
                    )

        except aiohttp.ClientError as e:
            # Log but don't raise - this is best-effort
            self.logger.warning(
                f"Failed to report phase completion to BCS: {e}",
                extra={
                    "batch_id": batch_id,
                    "phase": completed_phase.value,
                    "error": str(e),
                },
            )
        except Exception as e:
            # Log unexpected errors but don't raise
            self.logger.error(
                f"Unexpected error reporting phase completion to BCS: {e}",
                extra={
                    "batch_id": batch_id,
                    "phase": completed_phase.value,
                },
                exc_info=True,
            )
