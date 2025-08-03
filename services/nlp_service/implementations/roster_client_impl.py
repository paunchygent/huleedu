"""Default implementation of ClassManagementClientProtocol for NLP Service."""

from __future__ import annotations

import asyncio
from uuid import UUID

import aiohttp
from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.nlp_service.protocols import ClassManagementClientProtocol

logger = create_service_logger("nlp_service.roster_client_impl")


class DefaultClassManagementClient(ClassManagementClientProtocol):
    """Default implementation for fetching class rosters from Class Management Service."""

    def __init__(self, class_management_url: str) -> None:
        """Initialize class management client.

        Args:
            class_management_url: Base URL for Class Management Service
        """
        self.class_management_url = class_management_url

    async def get_class_roster(
        self,
        class_id: str,
        http_session: aiohttp.ClientSession,
        correlation_id: UUID,
    ) -> list[dict]:
        """Fetch student roster from Class Management Service.

        Args:
            class_id: ID of the class to fetch roster for
            http_session: HTTP client session
            correlation_id: Request correlation ID for tracing

        Returns:
            List of student dictionaries with fields matching StudentInfo model

        Raises:
            HuleEduError: On any failure to fetch roster
        """
        url = f"{self.class_management_url}/v1/classes/{class_id}/roster"

        logger.debug(
            f"Fetching class roster from URL: {url}",
            extra={"correlation_id": str(correlation_id), "class_id": class_id},
        )

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            headers = {
                "X-Correlation-ID": str(correlation_id),
                "Accept": "application/json",
            }

            async with http_session.get(url, timeout=timeout, headers=headers) as response:
                response.raise_for_status()

                # Parse JSON response
                data = await response.json()

                # Validate response structure
                if not isinstance(data, dict) or "students" not in data:
                    raise_external_service_error(
                        service="nlp_service",
                        operation="get_class_roster",
                        external_service="class_management",
                        message="Invalid response format: missing 'students' field",
                        correlation_id=correlation_id,
                        url=url,
                        response_data=str(data)[:200],
                    )

                students = data["students"]
                if not isinstance(students, list):
                    raise_external_service_error(
                        service="nlp_service",
                        operation="get_class_roster",
                        external_service="class_management",
                        message="Invalid response format: 'students' is not a list",
                        correlation_id=correlation_id,
                        url=url,
                        response_data=str(students)[:200],
                    )

                # Validate each student record has required fields
                validated_students = []
                for idx, student in enumerate(students):
                    if not isinstance(student, dict):
                        logger.warning(
                            f"Skipping invalid student record at index {idx}: not a dictionary",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        continue

                    # Check required fields match StudentInfo model
                    required_fields = {"student_id", "first_name", "last_name", "full_legal_name"}
                    if not all(field in student for field in required_fields):
                        missing_fields = required_fields - set(student.keys())
                        logger.warning(
                            f"Skipping student record at index {idx}: "
                            f"missing fields {missing_fields}",
                            extra={"correlation_id": str(correlation_id)},
                        )
                        continue

                    validated_students.append(student)

                logger.info(
                    f"Successfully fetched roster for class {class_id} with "
                    f"{len(validated_students)} students",
                    extra={"correlation_id": str(correlation_id), "class_id": class_id},
                )

                return validated_students

        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                raise_external_service_error(
                    service="nlp_service",
                    operation="get_class_roster",
                    external_service="class_management",
                    message=f"Class not found: {class_id}",
                    correlation_id=correlation_id,
                    url=url,
                    status_code=e.status,
                    class_id=class_id,
                )
            else:
                raise_external_service_error(
                    service="nlp_service",
                    operation="get_class_roster",
                    external_service="class_management",
                    message=f"HTTP error: {e.status} - {e.message}",
                    correlation_id=correlation_id,
                    url=url,
                    status_code=e.status,
                    class_id=class_id,
                )

        except asyncio.TimeoutError:
            logger.error(
                "Request to Class Management Service timed out after 10 seconds",
                extra={"correlation_id": str(correlation_id)},
            )
            raise_external_service_error(
                service="nlp_service",
                operation="get_class_roster",
                external_service="class_management",
                message=f"Timeout fetching roster for class {class_id}",
                correlation_id=correlation_id,
                url=url,
                class_id=class_id,
            )

        except aiohttp.ClientError as e:
            logger.error(
                f"HTTP client error: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise_external_service_error(
                service="nlp_service",
                operation="get_class_roster",
                external_service="class_management",
                message=f"Client error: {str(e)}",
                correlation_id=correlation_id,
                url=url,
                class_id=class_id,
                error_type=type(e).__name__,
            )

        except Exception as e:
            logger.error(
                f"Unexpected error fetching class roster: {e}",
                exc_info=True,
                extra={"correlation_id": str(correlation_id)},
            )
            raise_external_service_error(
                service="nlp_service",
                operation="get_class_roster",
                external_service="class_management",
                message=f"Unexpected error: {str(e)}",
                correlation_id=correlation_id,
                url=url,
                class_id=class_id,
                error_type=type(e).__name__,
            )
