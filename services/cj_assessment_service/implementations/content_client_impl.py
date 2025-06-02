"""Content client implementation for the CJ Assessment Service.

This module provides the concrete implementation of ContentClientProtocol,
enabling the CJ service to fetch spellchecked essay content from the Content Service.
"""

from __future__ import annotations

import asyncio

import aiohttp

from ..config import Settings
from ..protocols import ContentClientProtocol


class ContentClientImpl(ContentClientProtocol):
    """Implementation of ContentClientProtocol for fetching essay content."""

    def __init__(self, session: aiohttp.ClientSession, settings: Settings) -> None:
        """Initialize the content client with HTTP session and settings."""
        self.session = session
        self.settings = settings
        self.content_service_base_url = settings.CONTENT_SERVICE_URL.rstrip("/")

    async def fetch_content(self, storage_id: str) -> str:
        """Fetch essay text content by storage ID from Content Service.

        Args:
            storage_id: The storage reference ID for the essay text

        Returns:
            The essay text content

        Raises:
            aiohttp.ClientError: If HTTP request fails
            ValueError: If content cannot be decoded or is empty
        """
        endpoint = f"{self.content_service_base_url}/content/{storage_id}"

        timeout_config = aiohttp.ClientTimeout(total=self.settings.LLM_REQUEST_TIMEOUT_SECONDS)

        try:
            async with self.session.get(endpoint, timeout=timeout_config) as response:
                if response.status == 200:
                    content = await response.text()
                    if not content.strip():
                        raise ValueError(f"Empty content received for storage_id: {storage_id}")
                    return content
                elif response.status == 404:
                    raise ValueError(f"Content not found for storage_id: {storage_id}")
                else:
                    error_text = await response.text()
                    raise aiohttp.ClientResponseError(
                        request_info=response.request_info,
                        history=response.history,
                        status=response.status,
                        message=f"Content Service error: {error_text}",
                    )

        except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as e:
            raise ValueError(f"Timeout fetching content for storage_id: {storage_id}") from e
        except aiohttp.ClientError:
            raise  # Re-raise aiohttp errors
        except Exception as e:
            raise ValueError(
                f"Unexpected error fetching content for storage_id {storage_id}: {e!s}"
            ) from e
