"""Integration tests for identity-based credit attribution in Entitlements Service.

Tests credit attribution logic with ResourceConsumptionV1 event processing,
focusing on identity-based billing decisions and Swedish character support.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.resource_consumption_events import ResourceConsumptionV1
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol

from services.entitlements_service.kafka_consumer import EntitlementsKafkaConsumer
from services.entitlements_service.protocols import (
    CreditConsumptionResult,
    CreditManagerProtocol,
)


class TestCreditAttribution:
    """Integration tests for identity-based credit attribution."""

    @pytest.fixture
    def mock_credit_manager(self) -> AsyncMock:
        """Mock credit manager with default successful response."""
        manager = AsyncMock(spec=CreditManagerProtocol)
        manager.consume_credits.return_value = CreditConsumptionResult(
            success=True, new_balance=100, consumed_from="user"
        )
        return manager

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client for idempotency."""
        return AsyncMock(spec=AtomicRedisClientProtocol)

    @pytest.fixture
    def kafka_consumer(
        self, mock_credit_manager: AsyncMock, mock_redis_client: AsyncMock
    ) -> EntitlementsKafkaConsumer:
        """Create Kafka consumer instance with mocked dependencies."""
        return EntitlementsKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-entitlements",
            credit_manager=mock_credit_manager,
            redis_client=mock_redis_client,
        )

    def create_kafka_message(
        self,
        user_id: str,
        org_id: str | None,
        resource_type: str,
        quantity: int,
        entity_id: str = "batch-123",
        entity_type: str = "batch",
    ) -> Any:
        """Create mock Kafka message with ResourceConsumptionV1 event."""
        event = ResourceConsumptionV1(
            event_name=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED,
            entity_id=entity_id,
            entity_type=entity_type,
            user_id=user_id,
            org_id=org_id,
            resource_type=resource_type,
            quantity=quantity,
            service_name="test_service",
            processing_id="test-job-123",
            consumed_at=datetime.now(UTC),
        )
        envelope = EventEnvelope[ResourceConsumptionV1](
            event_type="huleedu.resource.consumption.v1",
            source_service="test_service",
            correlation_id=uuid4(),
            data=event,
        )
        message = MagicMock()
        message.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        return message

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "user_id,org_id,billing_type",
        [
            ("teacher-123", "school-456", "organizational"),
            ("freelance-teacher", None, "individual"),
            ("admin-user", "district-789", "organizational"),
            ("consultant-abc", None, "individual"),
        ],
    )
    async def test_identity_based_credit_attribution(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        user_id: str,
        org_id: str | None,
        billing_type: str,
    ) -> None:
        """Test credit attribution based on identity data."""
        # Arrange
        message = self.create_kafka_message(user_id, org_id, "ai_feedback", 3)
        envelope_data = json.loads(message.value.decode("utf-8"))

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        mock_credit_manager.consume_credits.assert_called_once_with(
            user_id=user_id,
            org_id=org_id,
            metric="ai_feedback",
            amount=3,
            batch_id="batch-123",
            correlation_id=envelope_data["correlation_id"],
        )

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "resource_type,quantity",
        [
            ("cj_comparison", 5),
            ("spell_check", 1),
            ("essay_scoring", 10),
        ],
    )
    async def test_resource_consumption_processing(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        resource_type: str,
        quantity: int,
    ) -> None:
        """Test ResourceConsumptionV1 event processing."""
        # Arrange
        message = self.create_kafka_message(
            "user-123", "org-456", resource_type, quantity
        )

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        mock_credit_manager.consume_credits.assert_called_once()
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["metric"] == resource_type
        assert call_args.kwargs["amount"] == quantity

    @pytest.mark.integration
    async def test_individual_user_credit_attribution(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test individual user credit attribution when org_id is None."""
        # Arrange
        message = self.create_kafka_message("freelance-001", None, "ai_feedback", 2)

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        mock_credit_manager.consume_credits.assert_called_once()
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["user_id"] == "freelance-001"
        assert call_args.kwargs["org_id"] is None
        assert call_args.kwargs["metric"] == "ai_feedback"
        assert call_args.kwargs["amount"] == 2

    @pytest.mark.integration
    async def test_organizational_credit_attribution(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test organizational credit attribution when org_id is present."""
        # Arrange
        message = self.create_kafka_message(
            "teacher-456", "school-district-789", "cj_comparison", 8
        )

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        mock_credit_manager.consume_credits.assert_called_once()
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["user_id"] == "teacher-456"
        assert call_args.kwargs["org_id"] == "school-district-789"
        assert call_args.kwargs["metric"] == "cj_comparison"
        assert call_args.kwargs["amount"] == 8

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "user_id,org_id,resource_type,quantity",
        [
            ("lärare-åäö", None, "svenska_bedömning", 3),
            ("användare-123", "skola-malmö", "grammatik_kontroll", 5),
            ("elev-örebro", "gymnasiet-ÅÄÖ", "rättstavning", 1),
        ],
    )
    async def test_swedish_character_credit_attribution(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
        user_id: str,
        org_id: str | None,
        resource_type: str,
        quantity: int,
    ) -> None:
        """Test credit attribution with Swedish characters in identity fields."""
        # Arrange
        message = self.create_kafka_message(user_id, org_id, resource_type, quantity)

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        mock_credit_manager.consume_credits.assert_called_once()
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["user_id"] == user_id
        assert call_args.kwargs["org_id"] == org_id
        assert call_args.kwargs["metric"] == resource_type
        assert call_args.kwargs["amount"] == quantity

    @pytest.mark.integration
    async def test_swedish_org_billing(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test organizational billing with Swedish org_id."""
        # Arrange
        message = self.create_kafka_message(
            "teacher-swe", "skola-malmö-åäö", "ai_feedback", 4
        )

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        mock_credit_manager.consume_credits.assert_called_once()
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["org_id"] == "skola-malmö-åäö"
        assert call_args.kwargs["user_id"] == "teacher-swe"

    @pytest.mark.integration
    async def test_batch_id_attribution_logic(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test batch_id attribution from entity_id."""
        # Arrange
        message = self.create_kafka_message(
            "user-batch", "org-batch", "spell_check", 6, "custom-batch-xyz"
        )

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["batch_id"] == "custom-batch-xyz"

    @pytest.mark.integration
    async def test_credit_calculation_accuracy(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test credit calculation from quantity mapping."""
        # Arrange
        message = self.create_kafka_message(
            "user-calc", "org-calc", "essay_scoring", 25
        )

        # Act
        await kafka_consumer._handle_message(message)

        # Assert
        call_args = mock_credit_manager.consume_credits.call_args
        assert call_args.kwargs["amount"] == 25

    @pytest.mark.integration
    async def test_event_validation_error_handling(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test handling of malformed ResourceConsumption events."""
        # Arrange - Invalid event structure
        invalid_envelope = {
            "event_type": "huleedu.resource.consumption.v1",
            "source_service": "test_service",
            "correlation_id": str(uuid4()),
            "data": {
                "event_name": "RESOURCE_CONSUMPTION_REPORTED",
                # Missing required user_id field
                "resource_type": "test_metric",
                "quantity": 1,
            },
        }
        message = MagicMock()
        message.value = json.dumps(invalid_envelope).encode("utf-8")

        # Act & Assert
        with pytest.raises(Exception):  # Pydantic validation error expected
            await kafka_consumer._handle_message(message)

        mock_credit_manager.consume_credits.assert_not_called()

    @pytest.mark.integration
    async def test_missing_user_id_validation(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test validation failure when user_id is missing."""
        # Arrange - Event missing required user_id
        invalid_event_data = {
            "event_name": "RESOURCE_CONSUMPTION_REPORTED",
            "entity_id": "batch-missing-user",
            "entity_type": "batch",
            # user_id missing
            "org_id": "org-test",
            "resource_type": "test_metric",
            "quantity": 1,
            "service_name": "test_service",
            "processing_id": "test-job",
        }
        envelope = {
            "event_type": "huleedu.resource.consumption.v1",
            "source_service": "test_service", 
            "correlation_id": str(uuid4()),
            "data": invalid_event_data,
        }
        message = MagicMock()
        message.value = json.dumps(envelope).encode("utf-8")

        # Act & Assert
        with pytest.raises(Exception):  # Should fail validation
            await kafka_consumer._handle_message(message)

    @pytest.mark.integration
    async def test_malformed_identity_data_handling(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test handling of malformed identity data in events."""
        # Arrange - Event with invalid data types
        invalid_envelope = {
            "event_type": "huleedu.resource.consumption.v1",
            "source_service": "test_service",
            "correlation_id": str(uuid4()),
            "data": {
                "event_name": "RESOURCE_CONSUMPTION_REPORTED",
                "entity_id": "batch-malformed",
                "entity_type": "batch",
                "user_id": 12345,  # Invalid type (should be string)
                "org_id": "org-test",
                "resource_type": "test_metric",
                "quantity": "invalid",  # Invalid type (should be int)
                "service_name": "test_service",
                "processing_id": "test-job",
            },
        }
        message = MagicMock()
        message.value = json.dumps(invalid_envelope).encode("utf-8")

        # Act & Assert
        with pytest.raises(Exception):  # Should fail validation
            await kafka_consumer._handle_message(message)

    @pytest.mark.integration
    async def test_credit_attribution_error_scenarios(
        self,
        kafka_consumer: EntitlementsKafkaConsumer,
        mock_credit_manager: AsyncMock,
    ) -> None:
        """Test credit attribution behavior when credit manager fails."""
        # Arrange
        mock_credit_manager.consume_credits.side_effect = Exception(
            "Credit system temporarily unavailable"
        )
        message = self.create_kafka_message("user-error", "org-error", "ai_feedback", 1)

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await kafka_consumer._handle_message(message)

        assert "Credit system temporarily unavailable" in str(exc_info.value)
        mock_credit_manager.consume_credits.assert_called_once()