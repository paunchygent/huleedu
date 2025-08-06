"""HTTP operations for fetching and storing content."""

from __future__ import annotations

from uuid import UUID

import aiohttp
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_processing_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("spellchecker_service.http_operations")


async def default_fetch_content_impl(
    session: aiohttp.ClientSession,
    storage_id: str,
    content_service_url: str,
    correlation_id: UUID,
    essay_id: str | None = None,
) -> str:
    """
    Default implementation for fetching content from the content service.
    Uses structured error handling with HuleEduError exceptions.
    """
    url = f"{content_service_url}/{storage_id}"
    log_prefix = f"Essay {essay_id}: " if essay_id else ""

    logger.debug(
        f"{log_prefix}Fetching content from URL: {url}",
        extra={
            "correlation_id": str(correlation_id),
            "storage_id": storage_id,
            "content_service_url": content_service_url,
            "essay_id": essay_id,
        },
    )

    try:
        async with session.get(url) as response:
            if response.status == 200:
                text = await response.text()
                logger.info(
                    f"{log_prefix}Successfully fetched content (length: {len(text)})",
                    extra={
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "content_length": len(text),
                        "essay_id": essay_id,
                    },
                )
                return text
            elif response.status == 404:
                error_text = await response.text()
                logger.error(
                    f"{log_prefix}Content not found (404): {error_text}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "response_status": response.status,
                        "essay_id": essay_id,
                    },
                )
                raise_content_service_error(
                    service="spellchecker_service",
                    operation="fetch_content",
                    message=f"Content not found for storage_id: {storage_id}",
                    correlation_id=correlation_id,
                    content_service_url=url,
                    response_status_code=404,
                    storage_id=storage_id,
                    essay_id=essay_id,
                )
            else:
                error_text = await response.text()
                logger.error(
                    f"{log_prefix}Failed to fetch content: {response.status} - {error_text}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "response_status": response.status,
                        "essay_id": essay_id,
                    },
                )
                raise_content_service_error(
                    service="spellchecker_service",
                    operation="fetch_content",
                    message=f"HTTP {response.status}: {error_text}",
                    correlation_id=correlation_id,
                    content_service_url=url,
                    response_status_code=response.status,
                    storage_id=storage_id,
                    essay_id=essay_id,
                )

    except aiohttp.ClientError as e:
        logger.error(
            f"{log_prefix}Network error while fetching content: {str(e)}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id),
                "storage_id": storage_id,
                "error_type": type(e).__name__,
                "essay_id": essay_id,
            },
        )
        raise_content_service_error(
            service="spellchecker_service",
            operation="fetch_content",
            message=f"Network error: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=url,
            storage_id=storage_id,
            error_type=type(e).__name__,
            essay_id=essay_id,
        )
    except Exception as e:
        logger.error(
            f"{log_prefix}Unexpected error while fetching content: {str(e)}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id),
                "storage_id": storage_id,
                "error_type": type(e).__name__,
                "essay_id": essay_id,
            },
        )
        raise_processing_error(
            service="spellchecker_service",
            operation="fetch_content",
            message=f"Unexpected error fetching content: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=url,
            storage_id=storage_id,
            error_type=type(e).__name__,
            essay_id=essay_id,
        )


async def default_store_content_impl(
    session: aiohttp.ClientSession,
    content_service_url: str,
    original_storage_id: str,
    content_type: str,
    content: str,
    correlation_id: UUID,
    essay_id: str | None = None,
) -> str:
    """
    Default implementation for storing content to the content service.
    Uses structured error handling with HuleEduError exceptions.

    Returns:
        str: The storage ID returned by the content service
    """
    log_prefix = f"Essay {essay_id}: " if essay_id else ""

    logger.debug(
        f"{log_prefix}Storing content to: {content_service_url}",
        extra={
            "correlation_id": str(correlation_id),
            "original_storage_id": original_storage_id,
            "content_type": content_type,
            "content_length": len(content),
            "essay_id": essay_id,
        },
    )

    payload = {
        "text": content,
        "metadata": {
            "source_storage_id": original_storage_id,
            "content_type": content_type,
        },
    }

    try:
        async with session.post(content_service_url, json=payload) as response:
            if response.status == 200:
                response_data = await response.json()
                storage_id: str | None = response_data.get("storage_id")
                if not storage_id:
                    logger.error(
                        f"{log_prefix}Response missing storage_id: {response_data}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "response_data": response_data,
                            "essay_id": essay_id,
                        },
                    )
                    raise_content_service_error(
                        service="spellchecker_service",
                        operation="store_content",
                        message="Response missing storage_id field",
                        correlation_id=correlation_id,
                        content_service_url=content_service_url,
                        response_data=response_data,
                        essay_id=essay_id,
                    )

                logger.info(
                    f"{log_prefix}Successfully stored content with storage_id: {storage_id}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "storage_id": storage_id,
                        "content_length": len(content),
                        "essay_id": essay_id,
                    },
                )
                return storage_id
            else:
                error_text = await response.text()
                logger.error(
                    f"{log_prefix}Failed to store content: {response.status} - {error_text}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "response_status": response.status,
                        "content_length": len(content),
                        "essay_id": essay_id,
                    },
                )
                raise_content_service_error(
                    service="spellchecker_service",
                    operation="store_content",
                    message=f"HTTP {response.status}: {error_text}",
                    correlation_id=correlation_id,
                    content_service_url=content_service_url,
                    response_status_code=response.status,
                    content_length=len(content),
                    essay_id=essay_id,
                )

    except aiohttp.ClientError as e:
        logger.error(
            f"{log_prefix}Network error while storing content: {str(e)}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id),
                "error_type": type(e).__name__,
                "content_length": len(content),
                "essay_id": essay_id,
            },
        )
        raise_content_service_error(
            service="spellchecker_service",
            operation="store_content",
            message=f"Network error: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            content_length=len(content),
            error_type=type(e).__name__,
            essay_id=essay_id,
        )
    except Exception as e:
        logger.error(
            f"{log_prefix}Unexpected error while storing content: {str(e)}",
            exc_info=True,
            extra={
                "correlation_id": str(correlation_id),
                "error_type": type(e).__name__,
                "content_length": len(content),
                "essay_id": essay_id,
            },
        )
        raise_processing_error(
            service="spellchecker_service",
            operation="store_content",
            message=f"Unexpected error storing content: {str(e)}",
            correlation_id=correlation_id,
            content_service_url=content_service_url,
            content_length=len(content),
            error_type=type(e).__name__,
            essay_id=essay_id,
        )
