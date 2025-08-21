"""
Unit tests for JwksStore in-memory JWKS store implementation.

Tests the core key management behavior for OAuth/OIDC compliance, focusing
on key lifecycle operations, kid-based replacement logic, and proper
JwksResponseV1 structure generation for /.well-known/jwks.json endpoint.
"""

from __future__ import annotations

from typing import List

import pytest
from common_core.identity_models import JwksPublicKeyV1, JwksResponseV1

from services.identity_service.implementations.jwks_store import JwksStore


class TestJwksStore:
    """Tests for in-memory JWKS store key management operations."""

    @pytest.fixture
    def jwks_store(self) -> JwksStore:
        """Create a fresh JwksStore instance for testing."""
        return JwksStore()

    @pytest.fixture
    def sample_rsa_key(self) -> JwksPublicKeyV1:
        """Create a sample RSA public key for testing."""
        return JwksPublicKeyV1(
            kid="test-key-rsa-2024",
            kty="RSA",
            n="sample-modulus-value-base64url-encoded",
            e="AQAB",
            alg="RS256",
            use="sig"
        )

    @pytest.fixture
    def swedish_key(self) -> JwksPublicKeyV1:
        """Create a key with Swedish characters in kid for locale testing."""
        return JwksPublicKeyV1(
            kid="nyckel-åäö-2024",
            kty="RSA", 
            n="swedish-modulus-värde",
            e="AQAB",
            alg="RS256",
            use="sig"
        )

    @pytest.fixture
    def rotation_keys(self) -> List[JwksPublicKeyV1]:
        """Create multiple keys for rotation testing scenarios."""
        return [
            JwksPublicKeyV1(
                kid="active-key-2024-12",
                kty="RSA",
                n="current-active-modulus",
                e="AQAB",
                alg="RS256",
                use="sig"
            ),
            JwksPublicKeyV1(
                kid="backup-key-2024-11",
                kty="RSA",
                n="previous-backup-modulus", 
                e="AQAB",
                alg="RS256",
                use="sig"
            ),
            JwksPublicKeyV1(
                kid="future-key-2025-01",
                kty="RSA",
                n="next-rotation-modulus",
                e="AQAB",
                alg="RS256",
                use="sig"
            )
        ]

    def test_init_creates_empty_store(self, jwks_store: JwksStore) -> None:
        """Test that JwksStore initializes with empty key list."""
        # Act
        jwks_response = jwks_store.get_jwks()
        
        # Assert
        assert isinstance(jwks_response, JwksResponseV1)
        assert jwks_response.keys == []
        assert len(jwks_response.keys) == 0

    def test_set_keys_replaces_all_keys(
        self, 
        jwks_store: JwksStore,
        rotation_keys: List[JwksPublicKeyV1]
    ) -> None:
        """Test that set_keys completely replaces the key list."""
        # Arrange - Start with one key
        initial_key = JwksPublicKeyV1(
            kid="initial-key",
            kty="RSA",
            n="initial-modulus",
            e="AQAB"
        )
        jwks_store.add_key(initial_key)
        
        # Act - Replace with multiple keys
        jwks_store.set_keys(rotation_keys)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 3
        assert jwks_response.keys == rotation_keys
        
        # Verify initial key was replaced
        key_ids = [key.kid for key in jwks_response.keys]
        assert "initial-key" not in key_ids
        assert "active-key-2024-12" in key_ids

    @pytest.mark.parametrize("key_count", [0, 1, 3, 10])
    def test_set_keys_with_various_counts(
        self, 
        jwks_store: JwksStore,
        key_count: int
    ) -> None:
        """Test set_keys operation with different key counts."""
        # Arrange
        test_keys = []
        for i in range(key_count):
            key = JwksPublicKeyV1(
                kid=f"test-key-{i}",
                kty="RSA", 
                n=f"modulus-{i}",
                e="AQAB"
            )
            test_keys.append(key)
        
        # Act
        jwks_store.set_keys(test_keys)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == key_count
        assert jwks_response.keys == test_keys

    def test_add_key_to_empty_store(
        self, 
        jwks_store: JwksStore,
        sample_rsa_key: JwksPublicKeyV1
    ) -> None:
        """Test adding a key to an empty store."""
        # Act
        jwks_store.add_key(sample_rsa_key)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 1
        assert jwks_response.keys[0] == sample_rsa_key
        assert jwks_response.keys[0].kid == "test-key-rsa-2024"

    def test_add_key_appends_different_kid(
        self, 
        jwks_store: JwksStore,
        sample_rsa_key: JwksPublicKeyV1,
        swedish_key: JwksPublicKeyV1
    ) -> None:
        """Test adding keys with different kid values appends them."""
        # Act
        jwks_store.add_key(sample_rsa_key)
        jwks_store.add_key(swedish_key)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 2
        
        key_ids = [key.kid for key in jwks_response.keys]
        assert "test-key-rsa-2024" in key_ids
        assert "nyckel-åäö-2024" in key_ids

    def test_add_key_replaces_same_kid(
        self, 
        jwks_store: JwksStore
    ) -> None:
        """Test that add_key replaces existing key with same kid."""
        # Arrange - Add initial key
        original_key = JwksPublicKeyV1(
            kid="rotation-key-001",
            kty="RSA",
            n="original-modulus", 
            e="AQAB",
            alg="RS256",
            use="sig"
        )
        jwks_store.add_key(original_key)
        
        # Act - Add key with same kid but different modulus
        replacement_key = JwksPublicKeyV1(
            kid="rotation-key-001",  # Same kid
            kty="RSA",
            n="replacement-modulus",  # Different modulus
            e="AQAB",
            alg="RS256", 
            use="sig"
        )
        jwks_store.add_key(replacement_key)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 1  # Only one key remains
        assert jwks_response.keys[0] == replacement_key
        assert jwks_response.keys[0].n == "replacement-modulus"  # Replaced

    def test_add_key_replacement_order_independence(
        self, 
        jwks_store: JwksStore
    ) -> None:
        """Test that kid replacement works regardless of original key position."""
        # Arrange - Add multiple keys
        keys = [
            JwksPublicKeyV1(kid="key-1", kty="RSA", n="mod-1", e="AQAB"),
            JwksPublicKeyV1(kid="key-2", kty="RSA", n="mod-2", e="AQAB"),
            JwksPublicKeyV1(kid="key-3", kty="RSA", n="mod-3", e="AQAB")
        ]
        for key in keys:
            jwks_store.add_key(key)
        
        # Act - Replace middle key
        replacement_key = JwksPublicKeyV1(
            kid="key-2", 
            kty="RSA",
            n="replacement-mod-2",
            e="AQAB"
        )
        jwks_store.add_key(replacement_key)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 3
        
        # Find the replaced key
        key_2 = next(key for key in jwks_response.keys if key.kid == "key-2")
        assert key_2.n == "replacement-mod-2"
        
        # Verify other keys unchanged
        key_1 = next(key for key in jwks_response.keys if key.kid == "key-1")
        key_3 = next(key for key in jwks_response.keys if key.kid == "key-3")
        assert key_1.n == "mod-1"
        assert key_3.n == "mod-3"

    def test_get_jwks_returns_valid_structure(
        self, 
        jwks_store: JwksStore,
        rotation_keys: List[JwksPublicKeyV1]
    ) -> None:
        """Test that get_jwks returns properly structured JwksResponseV1."""
        # Arrange
        jwks_store.set_keys(rotation_keys)
        
        # Act
        jwks_response = jwks_store.get_jwks()
        
        # Assert
        assert isinstance(jwks_response, JwksResponseV1)
        assert hasattr(jwks_response, 'keys')
        assert isinstance(jwks_response.keys, list)
        assert len(jwks_response.keys) == 3
        
        # Verify all keys are JwksPublicKeyV1 instances
        for key in jwks_response.keys:
            assert isinstance(key, JwksPublicKeyV1)
            assert hasattr(key, 'kid')
            assert hasattr(key, 'kty') 
            assert hasattr(key, 'n')
            assert hasattr(key, 'e')

    def test_get_jwks_pydantic_serialization_compliance(
        self, 
        jwks_store: JwksStore
    ) -> None:
        """Test that get_jwks response is properly Pydantic V2 serializable."""
        # Arrange
        test_key = JwksPublicKeyV1(
            kid="serialization-test",
            kty="RSA",
            n="test-modulus-value",
            e="AQAB"
            # alg and use will use defaults
        )
        jwks_store.add_key(test_key)
        
        # Act
        jwks_response = jwks_store.get_jwks()
        
        # Assert - Test Pydantic V2 serialization
        serialized = jwks_response.model_dump(mode="json")
        assert isinstance(serialized, dict)
        assert "keys" in serialized
        assert isinstance(serialized["keys"], list)
        assert len(serialized["keys"]) == 1
        
        # Verify key structure includes defaults
        key_data = serialized["keys"][0]
        assert key_data["kid"] == "serialization-test"
        assert key_data["kty"] == "RSA"
        assert key_data["n"] == "test-modulus-value"
        assert key_data["e"] == "AQAB"
        assert key_data["alg"] == "RS256"  # Default value
        assert key_data["use"] == "sig"    # Default value

    def test_swedish_character_handling(
        self, 
        jwks_store: JwksStore,
        swedish_key: JwksPublicKeyV1
    ) -> None:
        """Test proper handling of Swedish characters in key identifiers."""
        # Act
        jwks_store.add_key(swedish_key)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 1
        
        key = jwks_response.keys[0]
        assert key.kid == "nyckel-åäö-2024"  # Swedish chars preserved
        assert key.n == "swedish-modulus-värde"  # Swedish chars in modulus
        
        # Verify serialization preserves Swedish characters
        serialized = jwks_response.model_dump(mode="json")
        assert serialized["keys"][0]["kid"] == "nyckel-åäö-2024"
        assert serialized["keys"][0]["n"] == "swedish-modulus-värde"

    def test_key_lifecycle_complex_scenario(
        self, 
        jwks_store: JwksStore
    ) -> None:
        """Test complex key lifecycle with multiple operations."""
        # Phase 1: Initial key setup
        initial_keys = [
            JwksPublicKeyV1(kid="prod-2024-q1", kty="RSA", n="q1-mod", e="AQAB"),
            JwksPublicKeyV1(kid="backup-2023-q4", kty="RSA", n="q4-mod", e="AQAB")
        ]
        jwks_store.set_keys(initial_keys)
        assert len(jwks_store.get_jwks().keys) == 2
        
        # Phase 2: Add rotation key
        rotation_key = JwksPublicKeyV1(
            kid="prod-2024-q2", 
            kty="RSA", 
            n="q2-rotation-mod", 
            e="AQAB"
        )
        jwks_store.add_key(rotation_key)
        assert len(jwks_store.get_jwks().keys) == 3
        
        # Phase 3: Replace existing key
        updated_backup = JwksPublicKeyV1(
            kid="backup-2023-q4",  # Same kid
            kty="RSA",
            n="updated-q4-mod",  # New modulus
            e="AQAB"
        )
        jwks_store.add_key(updated_backup)
        assert len(jwks_store.get_jwks().keys) == 3  # Still 3 keys
        
        # Phase 4: Complete key refresh
        new_generation_keys = [
            JwksPublicKeyV1(kid="prod-2025-h1", kty="RSA", n="2025-mod", e="AQAB")
        ]
        jwks_store.set_keys(new_generation_keys)
        
        # Final verification
        final_response = jwks_store.get_jwks()
        assert len(final_response.keys) == 1
        assert final_response.keys[0].kid == "prod-2025-h1"
        assert final_response.keys[0].n == "2025-mod"

    @pytest.mark.parametrize(
        "kid_pattern,expected_kid",
        [
            # Edge case: empty kid handling
            ("", ""),
            # Security: special characters in kid
            ("key-with-dashes-123", "key-with-dashes-123"),
            ("key.with.dots", "key.with.dots"),
            ("key_with_underscores", "key_with_underscores"),
            # Locale: Unicode characters
            ("ключ-русский", "ключ-русский"),
            ("키-한국어", "키-한국어"),
            ("鍵-中文", "鍵-中文"),
        ]
    )
    def test_kid_edge_cases(
        self, 
        jwks_store: JwksStore,
        kid_pattern: str,
        expected_kid: str
    ) -> None:
        """Test kid handling with various character patterns and edge cases."""
        # Arrange
        test_key = JwksPublicKeyV1(
            kid=kid_pattern,
            kty="RSA",
            n="test-modulus-for-edge-case",
            e="AQAB"
        )
        
        # Act
        jwks_store.add_key(test_key)
        
        # Assert
        jwks_response = jwks_store.get_jwks()
        assert len(jwks_response.keys) == 1
        assert jwks_response.keys[0].kid == expected_kid

    def test_empty_store_operations(self, jwks_store: JwksStore) -> None:
        """Test operations on empty store behave correctly."""
        # Test get_jwks on empty store
        empty_response = jwks_store.get_jwks()
        assert isinstance(empty_response, JwksResponseV1)
        assert empty_response.keys == []
        
        # Test set_keys with empty list
        jwks_store.set_keys([])
        still_empty = jwks_store.get_jwks()
        assert still_empty.keys == []
        
        # Test that empty store serializes properly
        serialized = still_empty.model_dump(mode="json")
        assert serialized == {"keys": []}

    def test_oauth_oidc_compliance_structure(
        self, 
        jwks_store: JwksStore
    ) -> None:
        """Test that JWKS structure complies with OAuth/OIDC specifications."""
        # Arrange - Create realistic RSA key for OAuth/OIDC
        oauth_key = JwksPublicKeyV1(
            kid="oauth-rsa-key-2024-12-21", 
            kty="RSA",
            n="AQAB0N6X1Q2yfF7M...",  # Base64url-encoded modulus
            e="AQAB",  # Standard RSA exponent
            alg="RS256",  # Required for JWT signing
            use="sig"  # Key usage for signature
        )
        jwks_store.add_key(oauth_key)
        
        # Act
        jwks_response = jwks_store.get_jwks()
        
        # Assert - OAuth/OIDC compliance checks
        assert hasattr(jwks_response, 'keys')
        assert isinstance(jwks_response.keys, list)
        
        key = jwks_response.keys[0]
        # Required fields per RFC 7517
        assert hasattr(key, 'kid')  # Key ID
        assert hasattr(key, 'kty')  # Key Type  
        assert hasattr(key, 'use')  # Public Key Use
        assert hasattr(key, 'alg')  # Algorithm
        
        # RSA-specific fields per RFC 7518
        assert hasattr(key, 'n')  # Modulus
        assert hasattr(key, 'e')  # Exponent
        
        # Value validation
        assert key.kty == "RSA"
        assert key.use == "sig"
        assert key.alg == "RS256"
        assert key.e == "AQAB"