"""Contract tests for Identity Service event schemas.

These tests ensure that the event schemas published by the Identity Service
remain backward compatible and conform to the expected contracts that
downstream consumers depend on.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from common_core.events.envelope import EventEnvelope
from common_core.identity_enums import LoginFailureReason
from common_core.identity_models import (
    EmailVerificationRequestedV1,
    EmailVerifiedV1,
    LoginFailedV1,
    LoginSucceededV1,
    PasswordResetCompletedV1,
    PasswordResetRequestedV1,
    UserRegisteredV1,
)
from pydantic import ValidationError


class TestUserRegisteredV1Contract:
    """Test UserRegisteredV1 event schema contract."""

    def test_valid_schema_passes_validation(self) -> None:
        """Test that a valid UserRegisteredV1 event passes validation."""
        valid_event_data = {
            "user_id": str(uuid4()),
            "org_id": "org_123",
            "email": "test@example.com",
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = UserRegisteredV1(**valid_event_data)

        assert event.user_id == valid_event_data["user_id"]
        assert event.org_id == valid_event_data["org_id"]
        assert event.email == valid_event_data["email"]
        assert event.correlation_id == valid_event_data["correlation_id"]

    def test_missing_required_field_fails(self) -> None:
        """Test that missing required fields cause validation failure."""
        invalid_event_data = {
            "org_id": "org_123",
            "email": "test@example.com",
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        with pytest.raises(ValidationError) as exc_info:
            UserRegisteredV1(**invalid_event_data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("user_id",) for error in errors)

    def test_invalid_email_format_fails(self) -> None:
        """Test that invalid email format causes validation failure."""
        invalid_event_data = {
            "user_id": str(uuid4()),
            "org_id": "org_123",
            "email": "not-an-email",
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        with pytest.raises(ValidationError) as exc_info:
            UserRegisteredV1(**invalid_event_data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("email",) for error in errors)

    def test_event_envelope_wrapping(self) -> None:
        """Test that event can be wrapped in EventEnvelope."""
        event = UserRegisteredV1(
            user_id=str(uuid4()),
            org_id="org_123",
            email="test@example.com",
            registered_at=datetime.now(timezone.utc),
            correlation_id=str(uuid4()),
        )

        envelope = EventEnvelope[UserRegisteredV1](
            event_type="huleedu.identity.user.registered.v1",
            source_service="identity_service",
            schema_version=1,
            data=event,
            correlation_id=uuid4(),
        )

        assert envelope.event_type == "huleedu.identity.user.registered.v1"
        assert envelope.source_service == "identity_service"
        assert envelope.data == event


class TestLoginSucceededV1Contract:
    """Test LoginSucceededV1 event schema contract."""

    def test_valid_schema_passes_validation(self) -> None:
        """Test that a valid LoginSucceededV1 event passes validation."""
        valid_event_data = {
            "user_id": str(uuid4()),
            "org_id": "org_123",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = LoginSucceededV1(**valid_event_data)

        assert event.user_id == valid_event_data["user_id"]
        assert event.timestamp

    def test_optional_fields_can_be_omitted(self) -> None:
        """Test that optional org_id field can be omitted."""
        minimal_event_data = {
            "user_id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = LoginSucceededV1(**minimal_event_data)
        assert event.user_id == minimal_event_data["user_id"]
        assert event.org_id is None


class TestLoginFailedV1Contract:
    """Test LoginFailedV1 event schema contract."""

    def test_valid_schema_with_reason_enum(self) -> None:
        """Test that LoginFailedV1 validates reason enum correctly."""
        valid_event_data = {
            "email": "test@example.com",
            "reason": LoginFailureReason.INVALID_PASSWORD,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = LoginFailedV1(**valid_event_data)

        assert event.email == valid_event_data["email"]
        assert event.reason == LoginFailureReason.INVALID_PASSWORD

    def test_all_login_failed_reasons_valid(self) -> None:
        """Test that all valid reason enums are accepted."""
        base_data = {
            "email": "test@example.com",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        valid_reasons = [
            LoginFailureReason.USER_NOT_FOUND,
            LoginFailureReason.INVALID_PASSWORD,
            LoginFailureReason.ACCOUNT_LOCKED,
            LoginFailureReason.EMAIL_UNVERIFIED,
            LoginFailureReason.RATE_LIMIT_EXCEEDED,
        ]
        for reason in valid_reasons:
            event_data = {**base_data, "reason": reason}
            event = LoginFailedV1(**event_data)
            assert event.reason == reason

    def test_invalid_reason_fails(self) -> None:
        """Test that invalid reason value causes validation failure."""
        invalid_event_data = {
            "email": "test@example.com",
            "reason": "INVALID_REASON",  # String not an enum value
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        with pytest.raises(ValidationError) as exc_info:
            LoginFailedV1(**invalid_event_data)

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("reason",) for error in errors)


class TestEmailVerificationContracts:
    """Test email verification event schema contracts."""

    def test_email_verification_requested_schema(self) -> None:
        """Test EmailVerificationRequestedV1 schema validation."""
        valid_event_data = {
            "user_id": str(uuid4()),
            "email": "test@example.com",
            "token_id": str(uuid4()),
            "expires_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = EmailVerificationRequestedV1(**valid_event_data)

        assert event.user_id == valid_event_data["user_id"]
        assert event.token_id == valid_event_data["token_id"]
        assert event.expires_at

    def test_email_verified_schema(self) -> None:
        """Test EmailVerifiedV1 schema validation."""
        valid_event_data = {
            "user_id": str(uuid4()),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = EmailVerifiedV1(**valid_event_data)

        assert event.user_id == valid_event_data["user_id"]
        assert event.verified_at


class TestPasswordResetContracts:
    """Test password reset event schema contracts."""

    def test_password_reset_requested_schema(self) -> None:
        """Test PasswordResetRequestedV1 schema validation."""
        valid_event_data = {
            "user_id": str(uuid4()),
            "email": "test@example.com",
            "token_id": str(uuid4()),
            "expires_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = PasswordResetRequestedV1(**valid_event_data)

        assert event.user_id == valid_event_data["user_id"]
        assert event.token_id == valid_event_data["token_id"]

    def test_password_reset_completed_schema(self) -> None:
        """Test PasswordResetCompletedV1 schema validation."""
        valid_event_data = {
            "user_id": str(uuid4()),
            "reset_at": datetime.now(timezone.utc).isoformat(),
            "correlation_id": str(uuid4()),
        }

        event = PasswordResetCompletedV1(**valid_event_data)

        assert event.user_id == valid_event_data["user_id"]
        assert event.reset_at


class TestEventSerializationContract:
    """Test event serialization contracts."""

    def test_event_json_serialization(self) -> None:
        """Test that events can be serialized to JSON."""
        event = UserRegisteredV1(
            user_id=str(uuid4()),
            org_id="org_123",
            email="test@example.com",
            registered_at=datetime.now(timezone.utc),
            correlation_id=str(uuid4()),
        )

        json_data = event.model_dump_json()
        assert isinstance(json_data, str)

        # Can deserialize back
        deserialized = UserRegisteredV1.model_validate_json(json_data)
        assert deserialized.user_id == event.user_id

    def test_event_dict_serialization(self) -> None:
        """Test that events can be serialized to dict."""
        event = LoginSucceededV1(
            user_id=str(uuid4()),
            org_id="org_123",
            timestamp=datetime.now(timezone.utc),
            correlation_id=str(uuid4()),
        )

        dict_data = event.model_dump()
        assert isinstance(dict_data, dict)
        assert dict_data["user_id"] == event.user_id

        # Can reconstruct from dict
        reconstructed = LoginSucceededV1(**dict_data)
        assert reconstructed.user_id == event.user_id
