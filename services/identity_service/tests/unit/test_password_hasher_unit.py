"""
Unit tests for Argon2idPasswordHasher implementation behavior.

Tests focus on cryptographic implementation behavior rather than mocked dependencies.
Tests actual password hashing with Argon2id algorithm.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from services.identity_service.implementations.password_hasher_impl import (
    Argon2idPasswordHasher,
)


class TestArgon2idPasswordHasher:
    """Tests for Argon2idPasswordHasher implementation behavior."""

    @pytest.fixture
    def hasher(self) -> Argon2idPasswordHasher:
        """Create password hasher instance."""
        return Argon2idPasswordHasher()

    class TestHash:
        """Tests for hash method behavior."""

        @pytest.mark.parametrize(
            "password",
            [
                "simplepassword",
                "complex!P@ssw0rd123",
                "åäöÅÄÖ_swedish_chars",
                "🔐🗝️_emoji_password",
                "very_long_password_" * 10,  # 190 chars
                "with spaces and special chars!@#$%^&*()",
            ],
        )
        def test_hash_produces_valid_argon2id_format(
            self, hasher: Argon2idPasswordHasher, password: str
        ) -> None:
            """Should produce valid Argon2id hash format for various passwords."""
            result = hasher.hash(password)

            # Argon2id hashes start with $argon2id$
            assert result.startswith("$argon2id$")
            
            # Validate full Argon2id format: $argon2id$v=version$m=memory,t=time,p=parallelism$salt$hash
            argon2id_pattern = re.compile(
                r'^\$argon2id\$v=\d+\$m=\d+,t=\d+,p=\d+\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$'
            )
            assert argon2id_pattern.match(result), f"Invalid Argon2id format: {result}"

        def test_hash_produces_different_salts_for_same_password(
            self, hasher: Argon2idPasswordHasher
        ) -> None:
            """Should produce different hashes for same password due to salt uniqueness."""
            password = "testpassword123"
            
            hash1 = hasher.hash(password)
            hash2 = hasher.hash(password)
            
            assert hash1 != hash2, "Same password should produce different hashes"
            assert hash1.startswith("$argon2id$")
            assert hash2.startswith("$argon2id$")

        def test_hash_handles_empty_password(self, hasher: Argon2idPasswordHasher) -> None:
            """Should handle empty password without error."""
            result = hasher.hash("")
            
            assert result.startswith("$argon2id$")
            assert len(result) > 50  # Argon2id hashes are substantial

        def test_hash_handles_unicode_passwords(
            self, hasher: Argon2idPasswordHasher
        ) -> None:
            """Should properly handle Unicode characters in passwords."""
            unicode_passwords = [
                "café_password",  # accented chars
                "пароль",  # Cyrillic
                "密码",  # Chinese
                "🌟⭐🎉",  # Emoji only
                "Mixed_åäö_🔐_密码",  # Mixed unicode
            ]
            
            for password in unicode_passwords:
                result = hasher.hash(password)
                assert result.startswith("$argon2id$")
                # Verify we can verify the unicode password later
                assert hasher.verify(result, password)

    class TestVerify:
        """Tests for verify method behavior."""

        @pytest.fixture
        def password_and_hash(self, hasher: Argon2idPasswordHasher) -> tuple[str, str]:
            """Create password and its hash for testing."""
            password = "test_password_123"
            hash_value = hasher.hash(password)
            return password, hash_value

        def test_verify_returns_true_for_correct_password(
            self, 
            hasher: Argon2idPasswordHasher, 
            password_and_hash: tuple[str, str]
        ) -> None:
            """Should return True when password matches hash."""
            password, hash_value = password_and_hash
            
            result = hasher.verify(hash_value, password)
            
            assert result is True

        def test_verify_returns_false_for_incorrect_password(
            self, 
            hasher: Argon2idPasswordHasher, 
            password_and_hash: tuple[str, str]
        ) -> None:
            """Should return False when password doesn't match hash."""
            _, hash_value = password_and_hash
            
            result = hasher.verify(hash_value, "wrong_password")
            
            assert result is False

        @pytest.mark.parametrize(
            "wrong_password",
            [
                "",  # Empty password
                "almost_correct",  # Close but wrong
                "test_password_124",  # Off by one
                "TEST_PASSWORD_123",  # Wrong case
                "test_password_123 ",  # Extra space
            ],
        )
        def test_verify_returns_false_for_various_wrong_passwords(
            self, 
            hasher: Argon2idPasswordHasher, 
            password_and_hash: tuple[str, str],
            wrong_password: str
        ) -> None:
            """Should return False for various incorrect passwords."""
            _, hash_value = password_and_hash
            
            result = hasher.verify(hash_value, wrong_password)
            
            assert result is False

        def test_verify_handles_empty_password_verification(
            self, hasher: Argon2idPasswordHasher
        ) -> None:
            """Should handle verification of empty password correctly."""
            empty_password = ""
            hash_value = hasher.hash(empty_password)
            
            # Correct verification
            assert hasher.verify(hash_value, empty_password) is True
            
            # Incorrect verification
            assert hasher.verify(hash_value, "not_empty") is False

        def test_verify_handles_unicode_passwords(
            self, hasher: Argon2idPasswordHasher
        ) -> None:
            """Should properly verify Unicode passwords."""
            unicode_password = "Kära_användare_🔐_密码"
            hash_value = hasher.hash(unicode_password)
            
            # Correct verification
            assert hasher.verify(hash_value, unicode_password) is True
            
            # Incorrect verification with similar Unicode
            assert hasher.verify(hash_value, "Kära_användare_🗝️_密码") is False

        @pytest.mark.parametrize(
            "invalid_hash",
            [
                "",  # Empty hash
                "not_a_hash",  # Plain text
                "$argon2id$invalid",  # Invalid Argon2id format
                "$argon2id$v=19$m=65536,t=2,p=1$invalid_salt$invalid_hash",  # Malformed
                "bcrypt_hash_$2b$12$invalid",  # Different algorithm
            ],
        )
        def test_verify_returns_false_for_invalid_hash_formats(
            self, hasher: Argon2idPasswordHasher, invalid_hash: str
        ) -> None:
            """Should return False for invalid hash formats without raising exceptions."""
            result = hasher.verify(invalid_hash, "any_password")
            
            assert result is False

        def test_verify_round_trip_with_complex_passwords(
            self, hasher: Argon2idPasswordHasher
        ) -> None:
            """Should handle complete hash/verify cycle with complex passwords."""
            complex_passwords = [
                "P@ssw0rd!",
                "åäöÅÄÖ_svenska",
                "🔐secure🗝️password🎯",
                "very_long_password_with_many_chars_" * 5,
                "Mixed-Cases_123_åäö_🔐",
            ]
            
            for password in complex_passwords:
                hash_value = hasher.hash(password)
                assert hasher.verify(hash_value, password) is True
                assert hasher.verify(hash_value, password + "_wrong") is False