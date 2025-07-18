"""Batch Orchestrator Service client implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import aiohttp
from huleedu_service_libs.logging_utils import create_service_logger

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.protocols import BatchOrchestratorClientProtocol

logger = create_service_logger("result_aggregator.bos_client")


class BatchOrchestratorClientImpl(BatchOrchestratorClientProtocol):
    """HTTP client for communicating with Batch Orchestrator Service."""

    def __init__(self, settings: Settings, http_session: aiohttp.ClientSession):
        """Initialize the BOS client."""
        self.settings = settings
        self.http_session = http_session

    async def get_pipeline_state(self, batch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get pipeline state from BOS for batch consistency fallback.

        This method implements the internal consistency logic that was previously
        handled in the API Gateway. It queries BOS directly when batch data is
        not available in the Result Aggregator's own database.

        Args:
            batch_id: The batch identifier to query

        Returns:
            Pipeline state data from BOS, or None if batch not found

        Raises:
            Exception: For unexpected errors during BOS communication
        """
        try:
            bos_url = f"{self.settings.BOS_URL}/internal/v1/batches/{batch_id}/pipeline-state"

            logger.info("Querying BOS for batch pipeline state", batch_id=batch_id, bos_url=bos_url)

            timeout = aiohttp.ClientTimeout(total=self.settings.BOS_TIMEOUT_SECONDS)
            async with self.http_session.get(bos_url, timeout=timeout) as response:
                if response.status == 404:
                    logger.info(
                        "Batch not found in BOS", batch_id=batch_id, status_code=response.status
                    )
                    return None

                response.raise_for_status()
                bos_data: Dict[str, Any] = await response.json()

                logger.info(
                    "Successfully retrieved batch pipeline state from BOS",
                    batch_id=batch_id,
                    status_code=response.status,
                )

                return bos_data

        except asyncio.TimeoutError:
            logger.error(
                "Timeout while querying BOS for batch",
                batch_id=batch_id,
                timeout_seconds=self.settings.BOS_TIMEOUT_SECONDS,
            )
            raise
        except aiohttp.ClientError as e:
            logger.error(
                "HTTP client error while querying BOS",
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error while querying BOS",
                batch_id=batch_id,
                error=str(e),
                exc_info=True,
            )
            raise
