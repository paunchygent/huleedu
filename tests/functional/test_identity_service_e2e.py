"""
Identity Service End-to-End Tests

Tests comprehensive user journeys through the Identity Service with real infrastructure.
Uses Docker Compose services for full integration testing.

ARCHITECTURAL NOTE:
- Uses direct aiohttp calls (not ServiceTestManager) because Identity Service is a client-facing
  authentication provider, not an internal service consumer
- Tests real JWT tokens issued by Identity Service, not fake tokens from AuthTestManager
- Follows actual client authentication patterns

Test Scenarios:
1. Complete User Lifecycle: Registration → Email Verification → Login → Session → Logout
2. Token Management Flow: Login → Refresh → Revoke → Expiry
3. Password Reset Journey: Request → Verify → Reset → Login
4. Security and Rate Limiting: Failed Attempts → Lockout → Recovery
"""

import asyncio
import json
from typing import Any, Dict, Optional
from uuid import uuid4

import aiohttp
import pytest

# Identity Service and event models
from common_core.event_enums import ProcessingEvent, topic_name

from tests.utils.event_factory import reset_test_event_factory

# Test utilities (existing only - DO NOT create new utilities)
from tests.utils.kafka_test_manager import KafkaTestManager, create_kafka_test_config


@pytest.mark.slow
@pytest.mark.e2e
@pytest.mark.functional
@pytest.mark.asyncio
class TestIdentityServiceE2E:
    """Comprehensive E2E tests for Identity Service user journeys."""

    # Identity Service runs on port 7005 in Docker Compose
    IDENTITY_SERVICE_BASE_URL = "http://localhost:7005"

    @pytest.fixture
    def kafka_manager(self) -> KafkaTestManager:
        """Create KafkaTestManager for event verification."""
        config = create_kafka_test_config()
        return KafkaTestManager(config)

    @pytest.fixture
    def identity_event_topics(self) -> list[str]:
        """Define Identity Service event topics to monitor."""
        return [
            topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
            topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED),
            topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFIED),
            topic_name(ProcessingEvent.IDENTITY_LOGIN_SUCCEEDED),
            topic_name(ProcessingEvent.IDENTITY_LOGIN_FAILED),
            topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED),
            topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_COMPLETED),
        ]

    @pytest.fixture
    def swedish_test_data(self) -> Dict[str, Any]:
        """Test data with Swedish characters for comprehensive testing."""
        unique_id = str(uuid4())[:8]
        return {
            "email": f"test.användare.{unique_id}@huledu.se",
            "password": "TestLösenord123!",
            "person_name": {"first_name": "Erik", "last_name": "Åström"},
            "organization_name": "Göteborgs Universitet",
            "correlation_id": str(uuid4()),
        }

    @pytest.mark.timeout(120)  # 2 minute timeout for complete user lifecycle
    async def test_complete_user_lifecycle(
        self,
        clean_distributed_state,
        kafka_manager: KafkaTestManager,
        identity_event_topics: list[str],
        swedish_test_data: Dict[str, Any],
    ):
        """
        Test complete user lifecycle with corrected email verification flow.

        CORRECTED FLOW: Registration → Verify Email → Login → Session → Logout
        - Email verification is required BEFORE login (security best practice)
        - Registration automatically sends verification email
        - Users cannot login with unverified email addresses
        """
        # Ensure clean state
        _ = clean_distributed_state

        # Initialize unique correlation ID for this test
        event_factory = reset_test_event_factory()
        correlation_id = str(event_factory.create_unique_correlation_id())

        print(f"🔍 Test correlation ID: {correlation_id}")
        print(f"📧 Testing with Swedish email: {swedish_test_data['email']}")

        # CRITICAL: Set up Kafka consumer BEFORE triggering any actions
        async with kafka_manager.consumer("identity_lifecycle", identity_event_topics) as consumer:
            print("✅ Identity event monitoring consumer ready")

            async with aiohttp.ClientSession() as session:
                # Step 1: User Registration (Auto-sends verification email)
                print("📝 Step 1: User registration with auto-verification email...")
                registration_payload = {
                    "email": swedish_test_data["email"],
                    "password": swedish_test_data["password"],
                    "person_name": swedish_test_data["person_name"],
                    "organization_name": swedish_test_data["organization_name"],
                }

                async with session.post(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/auth/register",
                    json=registration_payload,
                    headers={"X-Correlation-ID": correlation_id},
                ) as response:
                    assert response.status == 201
                    registration_data = await response.json()
                    user_id = registration_data["user_id"]
                    print(f"✅ User registered successfully: {user_id}")

                # Verify UserRegisteredV1 event
                user_registered_event = await self._wait_for_event(
                    consumer,
                    topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
                    correlation_id,
                    timeout=10,
                )
                assert user_registered_event is not None
                assert user_registered_event["user_id"] == user_id
                assert user_registered_event["email"] == swedish_test_data["email"]
                print("✅ UserRegisteredV1 event verified")

                # Verify EmailVerificationRequestedV1 event (auto-sent after registration)
                verification_requested_event = await self._wait_for_event(
                    consumer,
                    topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED),
                    correlation_id,
                    timeout=10,
                )
                assert verification_requested_event is not None
                assert verification_requested_event["email"] == swedish_test_data["email"]
                verification_token = verification_requested_event.get("token_id")
                assert verification_token is not None
                print("✅ EmailVerificationRequestedV1 event verified (auto-sent)")

                # Step 2: Attempt Login with Unverified Email (SHOULD FAIL)
                print("❌ Step 2: Attempting login with unverified email (should fail)...")
                async with session.post(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/auth/login",
                    json={
                        "email": swedish_test_data["email"],
                        "password": swedish_test_data["password"],
                    },
                    headers={"X-Correlation-ID": correlation_id},
                ) as response:
                    assert response.status == 400  # Should fail with EMAIL_NOT_VERIFIED
                    error_data = await response.json()
                    print(
                        f"✅ Login correctly blocked: {error_data.get('error', {}).get('message', 'Unknown error')}"
                    )

                # Verify LoginFailedV1 event with EMAIL_UNVERIFIED reason
                login_failed_event = await self._wait_for_event(
                    consumer,
                    topic_name(ProcessingEvent.IDENTITY_LOGIN_FAILED),
                    correlation_id,
                    timeout=10,
                )
                assert login_failed_event is not None
                assert login_failed_event["email"] == swedish_test_data["email"]
                assert login_failed_event["reason"] == "email_unverified"
                print("✅ LoginFailedV1 event verified (EMAIL_UNVERIFIED)")

                # Step 3: Email Verification (Public endpoint - no auth needed)
                print("✉️ Step 3: Email verification with token...")
                async with session.post(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/auth/verify-email",
                    json={
                        "email": swedish_test_data["email"],
                        "token": verification_token,
                    },
                    headers={"X-Correlation-ID": correlation_id},
                ) as response:
                    assert response.status == 200
                    print("✅ Email verified successfully")

                # Verify EmailVerifiedV1 event
                email_verified_event = await self._wait_for_event(
                    consumer,
                    topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFIED),
                    correlation_id,
                    timeout=10,
                )
                assert email_verified_event is not None
                assert email_verified_event["user_id"] == user_id
                print("✅ EmailVerifiedV1 event verified")

                # Step 4: Login with Verified Email (NOW SHOULD SUCCEED)
                print("🔐 Step 4: Login with verified email (should succeed)...")
                async with session.post(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/auth/login",
                    json={
                        "email": swedish_test_data["email"],
                        "password": swedish_test_data["password"],
                    },
                    headers={"X-Correlation-ID": correlation_id},
                ) as response:
                    assert response.status == 200
                    login_data = await response.json()
                    access_token = login_data["access_token"]
                    refresh_token = login_data["refresh_token"]
                    assert access_token is not None
                    assert refresh_token is not None
                    print("✅ Login successful with verified email, real tokens received")

                # Verify LoginSucceededV1 event
                login_succeeded_event = await self._wait_for_event(
                    consumer,
                    topic_name(ProcessingEvent.IDENTITY_LOGIN_SUCCEEDED),
                    correlation_id,
                    timeout=10,
                )
                assert login_succeeded_event is not None
                assert login_succeeded_event["user_id"] == user_id
                print("✅ LoginSucceededV1 event verified")

                # Step 5: Access Protected Endpoint (with real JWT token)
                print("🛡️ Step 5: Accessing protected endpoint...")
                async with session.get(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/users/{user_id}/profile",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-Correlation-ID": correlation_id,
                    },
                ) as response:
                    assert response.status == 200
                    profile_data = await response.json()
                    assert profile_data["user_id"] == user_id
                    assert profile_data["email"] == swedish_test_data["email"]
                    assert profile_data["person_name"]["first_name"] == "Erik"
                    assert profile_data["person_name"]["last_name"] == "Åström"
                    print("✅ Protected endpoint access successful")

                # Step 6: Logout (with real JWT token)
                print("🚪 Step 6: User logout...")
                async with session.post(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/auth/logout",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-Correlation-ID": correlation_id,
                    },
                ) as response:
                    assert response.status == 200
                    print("✅ Logout successful")

                # Step 7: Verify session invalidated
                print("🔒 Step 7: Verifying session invalidation...")
                async with session.get(
                    f"{self.IDENTITY_SERVICE_BASE_URL}/v1/users/{user_id}/profile",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-Correlation-ID": correlation_id,
                    },
                ) as response:
                    assert response.status == 401
                    print("✅ Session properly invalidated after logout")

        print("🎉 CORRECTED user lifecycle test PASSED!")
        print("   → Registration auto-sends verification email")
        print("   → Login blocked until email verified")
        print("   → Verification enables login access")
        print("   → Full session management working")

    async def _wait_for_event(
        self, consumer: Any, expected_topic: str, expected_correlation_id: str, timeout: int = 15
    ) -> Optional[Dict[str, Any]]:
        """
        Wait for a specific event on the consumer with correlation ID matching.

        Args:
            consumer: Kafka consumer instance
            expected_topic: Topic name to match
            expected_correlation_id: Correlation ID to match
            timeout: Timeout in seconds

        Returns:
            Event data if found, None if timeout
        """
        print(f"🔍 Waiting for event on topic: {expected_topic}")

        start_time = asyncio.get_event_loop().time()

        async for message in consumer:
            try:
                current_time = asyncio.get_event_loop().time()
                if current_time - start_time > timeout:
                    print(f"⏰ Timeout waiting for event on {expected_topic}")
                    return None

                if not hasattr(message, "value") or not message.value:
                    continue

                # Parse message
                if isinstance(message.value, bytes):
                    raw_message = message.value.decode("utf-8")
                else:
                    raw_message = message.value

                envelope_data = json.loads(raw_message)

                # Check if this matches our expected event
                if (
                    message.topic == expected_topic
                    and envelope_data.get("correlation_id") == expected_correlation_id
                ):
                    event_data: Dict[str, Any] = envelope_data.get("data", {})
                    print(f"✅ Found matching event on {expected_topic}")
                    return event_data

            except Exception as e:
                print(f"⚠️ Error processing event: {e}")
                continue

        return None
