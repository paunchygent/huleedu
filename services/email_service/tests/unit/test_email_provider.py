"""
Unit tests for MockEmailProvider behavioral compliance.

Tests focus on EmailProvider protocol compliance without implementation details.
Uses behavioral validation following Rule 075 methodology for statistical
randomness testing and Swedish character support validation.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from services.email_service.config import Settings
from services.email_service.implementations.provider_mock_impl import MockEmailProvider
from services.email_service.protocols import EmailSendResult


class TestMockEmailProviderCompliance:
    """Test suite for EmailProvider protocol compliance and basic behavior."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings for testing."""
        settings = AsyncMock(spec=Settings)
        settings.DEFAULT_FROM_EMAIL = "noreply@huledu.com"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        settings.MOCK_PROVIDER_FAILURE_RATE = 0.0  # Deterministic tests by default
        return settings

    @pytest.fixture
    def email_provider(self, mock_settings: Settings) -> MockEmailProvider:
        """Create MockEmailProvider instance with mock settings."""
        return MockEmailProvider(settings=mock_settings)

    def test_protocol_implementation(self, email_provider: MockEmailProvider) -> None:
        """Should implement EmailProvider protocol with required methods."""
        # Verify protocol compliance through duck typing
        assert hasattr(email_provider, "send_email")
        assert hasattr(email_provider, "get_provider_name")
        assert callable(email_provider.send_email)
        assert callable(email_provider.get_provider_name)
        assert email_provider.get_provider_name() == "mock"

    def test_initialization(self, mock_settings: Settings) -> None:
        """Should initialize correctly with provided settings."""
        provider = MockEmailProvider(settings=mock_settings)
        assert provider.settings is mock_settings
        assert provider._sent_emails == []

    @pytest.mark.parametrize(
        "to_email, subject, html_content",
        [
            ("student@huledu.se", "Welcome Email", "<h1>Welcome!</h1>"),
            ("teacher@school.edu", "Password Reset", "<p>Click to reset</p>"),
            ("admin@huledu.com", "Notification", "<div>Account activated</div>"),
        ],
    )
    async def test_email_send_result_structure(
        self,
        email_provider: MockEmailProvider,
        to_email: str,
        subject: str,
        html_content: str,
    ) -> None:
        """Should return properly structured EmailSendResult."""
        result = await email_provider.send_email(
            to=to_email, subject=subject, html_content=html_content
        )

        # Validate EmailSendResult structure
        assert isinstance(result, EmailSendResult)
        assert isinstance(result.success, bool)

        if result.success:
            assert result.provider_message_id is not None
            assert isinstance(result.provider_message_id, str)
            assert result.error_message is None
        else:
            assert result.provider_message_id is None
            assert isinstance(result.error_message, str)

    async def test_sender_defaults_and_custom_behavior(
        self, email_provider: MockEmailProvider, mock_settings: Settings
    ) -> None:
        """Should handle both default and custom sender information."""
        # Test default sender behavior
        result1 = await email_provider.send_email(
            to="test1@example.com",
            subject="Default Test",
            html_content="<p>Testing defaults</p>",
        )

        if result1.success:
            sent_emails = email_provider.get_sent_emails()
            sent_email = sent_emails[-1]
            assert sent_email["from_email"] == mock_settings.DEFAULT_FROM_EMAIL
            assert sent_email["from_name"] == mock_settings.DEFAULT_FROM_NAME

        # Test custom sender behavior
        result2 = await email_provider.send_email(
            to="test2@example.com",
            subject="Custom Test",
            html_content="<p>Testing custom sender</p>",
            from_email="custom@huledu.se",
            from_name="Custom Sender",
        )

        if result2.success:
            sent_emails = email_provider.get_sent_emails()
            sent_email = sent_emails[-1]
            assert sent_email["from_email"] == "custom@huledu.se"
            assert sent_email["from_name"] == "Custom Sender"

    async def test_text_content_handling(self, email_provider: MockEmailProvider) -> None:
        """Should handle text content variations properly."""
        test_cases = [("Plain text", "Plain text"), ("", ""), (None, None)]

        for text_content, expected in test_cases:
            email_provider.clear_sent_emails()
            result = await email_provider.send_email(
                to="test@example.com",
                subject="Text Test",
                html_content="<h1>HTML</h1>",
                text_content=text_content,
            )

            if result.success:
                sent_emails = email_provider.get_sent_emails()
                assert sent_emails[-1]["text_content"] == expected


class TestSwedishCharacterSupport:
    """Test suite for Swedish character preservation (åäöÅÄÖ)."""

    @pytest.fixture
    def email_provider(self) -> MockEmailProvider:
        """Create MockEmailProvider instance."""
        settings = AsyncMock(spec=Settings)
        settings.DEFAULT_FROM_EMAIL = "noreply@huledu.com"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        settings.MOCK_PROVIDER_FAILURE_RATE = 0.0  # Deterministic tests by default
        return MockEmailProvider(settings=settings)

    @pytest.mark.parametrize(
        "to_email, subject, content, from_name",
        [
            (
                "åsa.lindström@huledu.se",
                "Välkommen till HuleEdu",
                "<p>Hej Åsa!</p>",
                "Åsa Lindström",
            ),
            (
                "björn.öström@skola.se",
                "Lösenordsåterställning",
                "<h1>Återställ lösenord</h1>",
                "Björn Öström",
            ),
            ("support@huledu.se", "Stöd: åäöÅÄÖ", "<p>Svenska tecken: åäöÅÄÖ</p>", "HuleEdu Stöd"),
        ],
    )
    async def test_swedish_character_preservation(
        self,
        email_provider: MockEmailProvider,
        to_email: str,
        subject: str,
        content: str,
        from_name: str,
    ) -> None:
        """Should preserve Swedish characters in all email fields."""
        result = await email_provider.send_email(
            to=to_email, subject=subject, html_content=content, from_name=from_name
        )

        if result.success:
            sent_emails = email_provider.get_sent_emails()
            sent_email = sent_emails[-1]

            assert sent_email["to"] == to_email
            assert sent_email["subject"] == subject
            assert sent_email["html_content"] == content
            assert sent_email["from_name"] == from_name

            # Verify Swedish characters present
            combined_text = (
                sent_email["to"]
                + sent_email["subject"]
                + sent_email["html_content"]
                + sent_email["from_name"]
            )
            swedish_chars = set("åäöÅÄÖ")
            found_chars = swedish_chars.intersection(set(combined_text))
            assert len(found_chars) > 0, "Should contain Swedish characters"


class TestNetworkBehaviorAndFailures:
    """Test suite for network delays and failure simulation validation."""

    @pytest.fixture
    def email_provider(self) -> MockEmailProvider:
        """Create MockEmailProvider with 5% failure rate.

        Used for testing statistical behavior.
        """
        settings = AsyncMock(spec=Settings)
        settings.DEFAULT_FROM_EMAIL = "noreply@huledu.com"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        settings.MOCK_PROVIDER_FAILURE_RATE = 0.05  # 5% failure rate for statistical testing
        return MockEmailProvider(settings=settings)

    async def test_network_delay_behavior(self, email_provider: MockEmailProvider) -> None:
        """Should simulate network delays in email sending."""
        start_time = asyncio.get_event_loop().time()

        # Send multiple emails to test cumulative delays
        for i in range(3):
            await email_provider.send_email(
                to=f"test{i}@example.com",
                subject=f"Delay Test {i}",
                html_content=f"<p>Content {i}</p>",
            )

        end_time = asyncio.get_event_loop().time()
        total_time = end_time - start_time

        # Should take some time due to simulated delays (3 * ~0.3s average)
        assert total_time >= 0.15, f"Expected cumulative delays, got {total_time}s"

    async def test_statistical_failure_rate_validation(
        self, email_provider: MockEmailProvider
    ) -> None:
        """Should maintain approximately 5% failure rate over multiple attempts."""
        total_attempts = 100
        failures = 0

        for i in range(total_attempts):
            # Clear storage periodically to prevent memory issues
            if i > 0 and i % 20 == 0:
                email_provider.clear_sent_emails()

            result = await email_provider.send_email(
                to=f"test{i}@example.com",
                subject=f"Test {i}",
                html_content=f"<p>Attempt {i}</p>",
            )

            if not result.success:
                failures += 1

        failure_rate = failures / total_attempts

        # Validate failure rate (allow reasonable variance: 1%-10% range for statistical testing)
        assert 0.01 <= failure_rate <= 0.10, (
            f"Failure rate {failure_rate:.3f} outside expected 1-10% range"
        )

    async def test_failure_result_structure(self, email_provider: MockEmailProvider) -> None:
        """Should return proper structure for both success and failure cases."""
        # Sample to get both success and failure cases
        results = []
        for i in range(50):
            result = await email_provider.send_email(
                to=f"structure{i}@test.com",
                subject=f"Structure Test {i}",
                html_content=f"<p>Testing {i}</p>",
            )
            results.append(result)

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        # Validate successful result structure
        if successes:
            success_result = successes[0]
            assert success_result.success is True
            assert success_result.provider_message_id is not None
            assert success_result.error_message is None

        # Validate failure result structure
        if failures:
            failure_result = failures[0]
            assert failure_result.success is False
            assert failure_result.provider_message_id is None
            assert failure_result.error_message == "Mock provider: Simulated delivery failure"


class TestEmailStorageAndInspection:
    """Test suite for email storage and inspection capabilities."""

    @pytest.fixture
    def email_provider(self) -> MockEmailProvider:
        """Create MockEmailProvider instance."""
        settings = AsyncMock(spec=Settings)
        settings.DEFAULT_FROM_EMAIL = "noreply@huledu.com"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        settings.MOCK_PROVIDER_FAILURE_RATE = 0.0  # Deterministic tests by default
        return MockEmailProvider(settings=settings)

    async def test_email_storage_functionality(self, email_provider: MockEmailProvider) -> None:
        """Should store sent emails with complete metadata for inspection."""
        test_data = {
            "to": "storage@test.com",
            "subject": "Storage Test",
            "html_content": "<h1>Testing storage</h1>",
            "text_content": "Plain text version",
            "from_email": "sender@huledu.se",
            "from_name": "Test Sender",
        }

        await email_provider.send_email(**test_data)

        sent_emails = email_provider.get_sent_emails()
        assert isinstance(sent_emails, list)

        if len(sent_emails) > 0:
            stored_email = sent_emails[-1]
            assert stored_email["to"] == test_data["to"]
            assert stored_email["subject"] == test_data["subject"]
            assert stored_email["html_content"] == test_data["html_content"]
            assert stored_email["text_content"] == test_data["text_content"]
            assert isinstance(stored_email["sent_at"], datetime)

    def test_storage_isolation_and_clearing(self) -> None:
        """Should maintain separate storage for different instances and support clearing."""
        settings1 = AsyncMock(spec=Settings)
        settings1.DEFAULT_FROM_EMAIL = "provider1@test.com"
        settings2 = AsyncMock(spec=Settings)
        settings2.DEFAULT_FROM_EMAIL = "provider2@test.com"

        provider1 = MockEmailProvider(settings=settings1)
        provider2 = MockEmailProvider(settings=settings2)

        # Test isolation
        assert provider1.get_sent_emails() == []
        assert provider2.get_sent_emails() == []
        assert provider1._sent_emails is not provider2._sent_emails

        # Test clearing functionality
        provider1._sent_emails.append({"test": "data"})
        assert len(provider1._sent_emails) == 1
        provider1.clear_sent_emails()
        assert provider1._sent_emails == []

    async def test_message_id_generation(self, email_provider: MockEmailProvider) -> None:
        """Should generate unique message IDs with expected format."""
        message_ids = set()

        # Send multiple emails and collect successful message IDs
        for i in range(20):
            result = await email_provider.send_email(
                to=f"unique{i}@test.com",
                subject=f"Unique Test {i}",
                html_content=f"<p>Content {i}</p>",
            )

            if result.success and result.provider_message_id:
                message_ids.add(result.provider_message_id)

                # Validate format on first successful ID
                if len(message_ids) == 1:
                    message_id = result.provider_message_id
                    assert message_id.startswith("mock_")
                    # Format: mock_YYYYMMDD_HHMMSS_NNNN
                    pattern = r"mock_\d{8}_\d{6}_\d{4}"
                    assert re.match(pattern, message_id), (
                        f"Message ID '{message_id}' doesn't match expected format"
                    )

        # Should have unique IDs (allowing for some failures)
        assert len(message_ids) >= 15, "Should generate unique message IDs"
