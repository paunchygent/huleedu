"""
Unit tests for Token Issuer implementation behavior.

Tests focus on JWT token generation, validation, and security properties.
Uses direct instantiation following established patterns for implementation testing.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import jwt
import pytest

from services.identity_service.implementations.jwks_store import JwksStore
from services.identity_service.implementations.token_issuer_impl import DevTokenIssuer
from services.identity_service.implementations.token_issuer_rs256_impl import Rs256TokenIssuer


class TestDevTokenIssuer:
    """Tests for DevTokenIssuer JWT token behavior."""

    @pytest.fixture
    def issuer(self) -> DevTokenIssuer:
        """Create DevTokenIssuer instance for testing."""
        return DevTokenIssuer()

    @pytest.fixture
    def sample_user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_org_id(self) -> str:
        """Sample org ID for testing."""
        return str(uuid4())

    class TestAccessTokenGeneration:
        """Tests for access token generation behavior."""

        def test_generates_valid_jwt_structure(
            self, issuer: DevTokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should generate JWT with proper header.payload.signature structure."""
            roles = ["teacher", "admin"]
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            parts = token.split(".")
            assert len(parts) == 3, "JWT should have three parts separated by dots"

            # Verify header structure
            header = json.loads(jwt.utils.base64url_decode(parts[0] + "==="))
            assert header["alg"] == "HS256"
            assert header["typ"] == "JWT"

        def test_includes_required_claims(
            self, issuer: DevTokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should include all required JWT claims in access token."""
            roles = ["student"]
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            # Decode payload manually for testing
            parts = token.split(".")
            payload = json.loads(jwt.utils.base64url_decode(parts[1] + "==="))

            assert payload["sub"] == sample_user_id
            assert payload["org"] == sample_org_id
            assert payload["roles"] == roles
            assert "exp" in payload
            assert "iss" in payload

        def test_handles_none_org_id(self, issuer: DevTokenIssuer, sample_user_id: str) -> None:
            """Should handle None org_id gracefully in access token."""
            roles = ["teacher"]
            token = issuer.issue_access_token(sample_user_id, None, roles)

            parts = token.split(".")
            payload = json.loads(jwt.utils.base64url_decode(parts[1] + "==="))

            assert payload["sub"] == sample_user_id
            assert payload["org"] is None
            assert payload["roles"] == roles

        @pytest.mark.parametrize(
            "roles",
            [
                [],  # Empty roles
                ["student"],  # Single role
                ["teacher", "admin", "coordinator"],  # Multiple roles
                ["Göteborgs Universitet Admin"],  # Swedish characters
            ],
        )
        def test_handles_various_role_combinations(
            self, issuer: DevTokenIssuer, sample_user_id: str, sample_org_id: str, roles: list[str]
        ) -> None:
            """Should handle different role combinations including Swedish characters."""
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            parts = token.split(".")
            payload = json.loads(jwt.utils.base64url_decode(parts[1] + "==="))

            assert payload["roles"] == roles
            assert payload["sub"] == sample_user_id

        def test_sets_proper_expiration(
            self, issuer: DevTokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should set appropriate expiration time for access token."""
            current_time = int(time.time())
            token = issuer.issue_access_token(sample_user_id, sample_org_id, ["teacher"])

            parts = token.split(".")
            payload = json.loads(jwt.utils.base64url_decode(parts[1] + "==="))

            # Should expire in reasonable future (within expected range)
            assert payload["exp"] > current_time
            assert payload["exp"] <= current_time + 7200  # 2 hours max

    class TestRefreshTokenGeneration:
        """Tests for refresh token generation behavior."""

        def test_generates_valid_refresh_token_structure(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should generate refresh token with proper JWT structure and return JTI."""
            token, jti = issuer.issue_refresh_token(sample_user_id)

            # Verify token structure
            parts = token.split(".")
            assert len(parts) == 3

            # Verify JTI format
            assert jti.startswith("r-")
            assert len(jti) > 10  # Should have timestamp

        def test_includes_refresh_token_claims(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should include proper claims for refresh token."""
            token, jti = issuer.issue_refresh_token(sample_user_id)

            parts = token.split(".")
            payload = json.loads(jwt.utils.base64url_decode(parts[1] + "==="))

            assert payload["sub"] == sample_user_id
            assert payload["typ"] == "refresh"
            assert payload["jti"] == jti
            assert "exp" in payload

        def test_generates_unique_jti_across_calls(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should generate unique JTI for each refresh token."""
            token1, jti1 = issuer.issue_refresh_token(sample_user_id)
            time.sleep(0.001)  # Ensure different timestamp
            token2, jti2 = issuer.issue_refresh_token(sample_user_id)

            assert jti1 != jti2
            assert token1 != token2

        def test_refresh_token_longer_expiration(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should set longer expiration for refresh tokens."""
            current_time = int(time.time())
            token, _ = issuer.issue_refresh_token(sample_user_id)

            parts = token.split(".")
            payload = json.loads(jwt.utils.base64url_decode(parts[1] + "==="))

            # Refresh token should have 24x longer expiration (24 * 3600 = 86400 seconds)
            assert payload["exp"] >= current_time + 86400  # Exactly 1 day

    class TestTokenVerification:
        """Tests for token verification behavior."""

        def test_verifies_valid_access_token(
            self, issuer: DevTokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should successfully verify valid access token."""
            roles = ["teacher"]
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            result = issuer.verify(token)

            assert result["sub"] == sample_user_id
            assert result["org"] == sample_org_id
            assert result["roles"] == roles

        def test_verifies_valid_refresh_token(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should successfully verify valid refresh token."""
            token, jti = issuer.issue_refresh_token(sample_user_id)

            result = issuer.verify(token)

            assert result["sub"] == sample_user_id
            assert result["typ"] == "refresh"
            assert result["jti"] == jti

        @pytest.mark.parametrize(
            "invalid_token",
            [
                "invalid.token.format",  # Invalid JWT format
                "not-a-jwt-at-all",  # Not JWT structure
                "",  # Empty token
                "a.b",  # Only two parts
                "a.b.c.d",  # Too many parts
            ],
        )
        def test_returns_empty_dict_for_invalid_tokens(
            self, issuer: DevTokenIssuer, invalid_token: str
        ) -> None:
            """Should return empty dict for malformed tokens."""
            result = issuer.verify(invalid_token)
            assert result == {}

        def test_handles_swedish_org_names_in_verification(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should properly handle Swedish characters in org names during verification."""
            swedish_org = "Göteborgs Universitet"
            roles = ["Lärare"]  # Teacher in Swedish
            token = issuer.issue_access_token(sample_user_id, swedish_org, roles)

            result = issuer.verify(token)

            assert result["org"] == swedish_org
            assert result["roles"] == roles

        def test_expired_token_still_decoded_in_dev_mode(
            self, issuer: DevTokenIssuer, sample_user_id: str
        ) -> None:
            """Should decode expired tokens in dev mode (no signature verification)."""
            # Create token with past expiration
            with patch("time.time", return_value=1000000000):  # Fixed past time
                token = issuer.issue_access_token(sample_user_id, None, ["test"])

            # Verify token in "future" (token is expired)
            with patch("time.time", return_value=2000000000):  # Much later time
                result = issuer.verify(token)

            # Dev mode doesn't check expiration
            assert result["sub"] == sample_user_id
            assert (
                result["exp"]
                == 1000000000
                + issuer._encode.__globals__["settings"].JWT_ACCESS_TOKEN_EXPIRES_SECONDS
            )


class TestRs256TokenIssuer:
    """Tests for Rs256TokenIssuer JWT token behavior."""

    @pytest.fixture
    def mock_jwks_store(self) -> MagicMock:
        """Create mock JWKS store for testing."""
        return MagicMock(spec=JwksStore)

    @pytest.fixture
    def mock_settings(self) -> MagicMock:
        """Mock settings for RS256 testing."""
        from pydantic import SecretStr

        mock = MagicMock()
        mock.JWT_RS256_PRIVATE_KEY_PATH = SecretStr("/test/key.pem")
        mock.JWT_RS256_PUBLIC_JWKS_KID = "test-kid"
        mock.JWT_ACCESS_TOKEN_EXPIRES_SECONDS = 3600
        mock.JWT_ISSUER = "huleedu-identity-service"
        mock.JWT_AUDIENCE = "huleedu-platform"
        mock.SERVICE_NAME = "identity_service"
        return mock

    @pytest.fixture
    def sample_private_key_pem(self) -> bytes:
        """Generate a test RSA private key for testing."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    @pytest.fixture
    def issuer(
        self, mock_jwks_store: MagicMock, mock_settings: MagicMock, sample_private_key_pem: bytes
    ) -> Rs256TokenIssuer:
        """Create Rs256TokenIssuer instance for testing."""
        with (
            patch(
                "services.identity_service.implementations.token_issuer_rs256_impl.settings",
                mock_settings,
            ),
            patch("pathlib.Path.read_bytes", return_value=sample_private_key_pem),
        ):
            return Rs256TokenIssuer(mock_jwks_store)

    @pytest.fixture
    def sample_user_id(self) -> str:
        """Sample user ID for testing."""
        return str(uuid4())

    @pytest.fixture
    def sample_org_id(self) -> str:
        """Sample org ID for testing."""
        return str(uuid4())

    class TestRs256AccessTokenGeneration:
        """Tests for RS256 access token generation."""

        def test_generates_valid_rs256_jwt(
            self, issuer: Rs256TokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should generate valid RS256 JWT with proper headers."""
            roles = ["teacher"]
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            # Decode header without verification
            header = jwt.get_unverified_header(token)
            assert header["alg"] == "RS256"
            assert header["typ"] == "JWT"
            assert header["kid"] == "test-kid"

        def test_includes_proper_rs256_claims(
            self, issuer: Rs256TokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should include all required claims in RS256 access token."""
            roles = ["admin", "teacher"]
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            # Decode payload without verification for testing
            payload = jwt.decode(token, options={"verify_signature": False})

            assert payload["sub"] == sample_user_id
            assert payload["org"] == sample_org_id
            assert payload["roles"] == roles
            assert payload["iss"] == "huleedu-identity-service"
            assert "exp" in payload

        def test_registers_jwk_on_initialization(
            self,
            mock_jwks_store: MagicMock,
            mock_settings: MagicMock,
            sample_private_key_pem: bytes,
        ) -> None:
            """Should register JWK with JWKS store during initialization."""
            with (
                patch(
                    "services.identity_service.implementations.token_issuer_rs256_impl.settings",
                    mock_settings,
                ),
                patch("pathlib.Path.read_bytes", return_value=sample_private_key_pem),
            ):
                Rs256TokenIssuer(mock_jwks_store)

            # Should have called add_key with proper JWK
            mock_jwks_store.add_key.assert_called_once()
            call_args = mock_jwks_store.add_key.call_args[0][0]
            assert call_args.kid == "test-kid"
            assert call_args.kty == "RSA"
            assert call_args.n is not None
            assert call_args.e is not None

    class TestRs256RefreshTokenGeneration:
        """Tests for RS256 refresh token generation."""

        def test_generates_rs256_refresh_token(
            self, issuer: Rs256TokenIssuer, sample_user_id: str
        ) -> None:
            """Should generate RS256 refresh token with proper structure."""
            token, jti = issuer.issue_refresh_token(sample_user_id)

            header = jwt.get_unverified_header(token)
            assert header["alg"] == "RS256"
            assert header["kid"] == "test-kid"

            payload = jwt.decode(token, options={"verify_signature": False})
            assert payload["sub"] == sample_user_id
            assert payload["typ"] == "refresh"
            assert payload["jti"] == jti

    class TestRs256TokenVerification:
        """Tests for RS256 token verification behavior."""

        def test_verifies_own_tokens_successfully(
            self, issuer: Rs256TokenIssuer, sample_user_id: str, sample_org_id: str
        ) -> None:
            """Should successfully verify tokens it generates."""
            roles = ["teacher"]
            token = issuer.issue_access_token(sample_user_id, sample_org_id, roles)

            result = issuer.verify(token)

            assert result["sub"] == sample_user_id
            assert result["org"] == sample_org_id
            assert result["roles"] == roles

        def test_verifies_refresh_tokens(
            self, issuer: Rs256TokenIssuer, sample_user_id: str
        ) -> None:
            """Should successfully verify refresh tokens."""
            token, jti = issuer.issue_refresh_token(sample_user_id)

            result = issuer.verify(token)

            assert result["sub"] == sample_user_id
            assert result["typ"] == "refresh"
            assert result["jti"] == jti

        def test_returns_empty_dict_for_invalid_signature(
            self, issuer: Rs256TokenIssuer, sample_user_id: str
        ) -> None:
            """Should return empty dict for tokens with invalid signatures."""
            # Create a token with wrong signature
            invalid_token = (
                "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0In0.invalid_signature"
            )

            result = issuer.verify(invalid_token)
            assert result == {}

        def test_handles_malformed_tokens_gracefully(self, issuer: Rs256TokenIssuer) -> None:
            """Should handle malformed tokens without raising exceptions."""
            malformed_tokens = [
                "not.a.token",
                "",
                "malformed-token",
                "too.many.parts.here.invalid",
            ]

            for token in malformed_tokens:
                result = issuer.verify(token)
                assert result == {}

        def test_handles_swedish_characters_in_verification(
            self, issuer: Rs256TokenIssuer, sample_user_id: str
        ) -> None:
            """Should properly handle Swedish characters in RS256 tokens."""
            swedish_org = "Stockholms Universitet"
            swedish_roles = ["Universitetslektor", "Forskare"]
            token = issuer.issue_access_token(sample_user_id, swedish_org, swedish_roles)

            result = issuer.verify(token)

            assert result["org"] == swedish_org
            assert result["roles"] == swedish_roles

    class TestRs256KeyHandling:
        """Tests for RSA key handling in Rs256TokenIssuer."""

        def test_raises_error_for_missing_key_path(self, mock_jwks_store: MagicMock) -> None:
            """Should raise error when private key path is not configured."""
            mock_settings = MagicMock()
            mock_settings.JWT_RS256_PRIVATE_KEY_PATH = None

            with patch(
                "services.identity_service.implementations.token_issuer_rs256_impl.settings",
                mock_settings,
            ):
                with pytest.raises(RuntimeError, match="JWT_RS256_PRIVATE_KEY_PATH must be set"):
                    Rs256TokenIssuer(mock_jwks_store)

        def test_raises_error_for_non_rsa_key(
            self, mock_jwks_store: MagicMock, mock_settings: MagicMock
        ) -> None:
            """Should raise error when provided key is not RSA."""
            # Generate EC key instead of RSA
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            ec_key = ec.generate_private_key(ec.SECP256R1())
            ec_key_pem = ec_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )

            with (
                patch(
                    "services.identity_service.implementations.token_issuer_rs256_impl.settings",
                    mock_settings,
                ),
                patch("pathlib.Path.read_bytes", return_value=ec_key_pem),
            ):
                with pytest.raises(RuntimeError, match="Expected RSA private key"):
                    Rs256TokenIssuer(mock_jwks_store)
