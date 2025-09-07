"""Credit provisioning helper for pipeline tests."""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.utils.auth_manager import AuthTestUser
    from tests.utils.service_test_manager import ServiceTestManager

logger = logging.getLogger(__name__)


class CreditProvisioningHelper:
    """Helper class for provisioning credits during tests."""

    @staticmethod
    async def provision_credits(
        teacher_user: "AuthTestUser",
        service_manager: "ServiceTestManager",
        correlation_id: str,
        amount: int = 10000,
        enabled: bool = True,
    ) -> None:
        """
        Provision credits for test user to ensure pipelines can execute.

        BOS checks org credits first, then user credits. We provision to both
        to ensure tests pass regardless of user type.

        Args:
            teacher_user: The test user to provision credits for
            service_manager: Service manager for making API requests
            correlation_id: Correlation ID for tracking
            amount: Credit amount to provision (default 10000 is sufficient for most tests)
            enabled: Set to False to test credit denial scenarios
        """
        if not enabled:
            logger.info("Credit provisioning disabled for this test")
            return

        # Provision to org if user has one
        if hasattr(teacher_user, "organization_id") and teacher_user.organization_id:
            try:
                await service_manager.make_request(
                    method="POST",
                    service="entitlements_service",
                    path="/v1/admin/credits/set",
                    json={
                        "subject_type": "org",
                        "subject_id": teacher_user.organization_id,
                        "balance": amount,
                    },
                    user=teacher_user,
                    correlation_id=correlation_id,
                )
                logger.info(
                    f"💳 Provisioned {amount} credits to org {teacher_user.organization_id}"
                )
            except Exception as e:
                logger.warning(f"Could not provision org credits: {e}")

        # Always provision to user as fallback
        try:
            await service_manager.make_request(
                method="POST",
                service="entitlements_service",
                path="/v1/admin/credits/set",
                json={
                    "subject_type": "user",
                    "subject_id": teacher_user.user_id,
                    "balance": amount,
                },
                user=teacher_user,
                correlation_id=correlation_id,
            )
            logger.info(f"💳 Provisioned {amount} credits to user {teacher_user.user_id}")
        except Exception as e:
            logger.warning(f"Could not provision user credits: {e}")
            logger.warning("⚠️ Tests may fail with 402 insufficient credits errors")
