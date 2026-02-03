"""Tests for development JWT authentication and production safety gates."""

from __future__ import annotations

import importlib
import sys
from datetime import datetime

import jwt
import pytest


class TestProductionSafetyGates:
    """Test that dev_auth module is blocked in production environments."""

    def test_import_blocked_in_production_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate 1: Module import fails when ENVIRONMENT=production."""
        # Set production environment BEFORE import
        monkeypatch.setenv("ENVIRONMENT", "production")

        # Remove module from cache if it was imported
        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        # Attempt import - should raise RuntimeError
        with pytest.raises(RuntimeError, match="dev_auth.py cannot be imported in production"):
            import scripts.cj_experiments_runners.eng5_np.dev_auth  # noqa: F401

    def test_import_blocked_in_staging_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gate 1: Module import fails when ENVIRONMENT=staging."""
        monkeypatch.setenv("ENVIRONMENT", "staging")

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        with pytest.raises(RuntimeError, match="dev_auth.py cannot be imported in production"):
            import scripts.cj_experiments_runners.eng5_np.dev_auth  # noqa: F401

    def test_import_blocked_with_huleedu_environment_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate 1: Module import fails when HULEEDU_ENVIRONMENT=production."""
        monkeypatch.setenv("HULEEDU_ENVIRONMENT", "production")

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        with pytest.raises(RuntimeError, match="dev_auth.py cannot be imported in production"):
            import scripts.cj_experiments_runners.eng5_np.dev_auth  # noqa: F401

    def test_import_blocked_with_prod_abbreviation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gate 1: Module import fails when ENVIRONMENT=prod."""
        monkeypatch.setenv("ENVIRONMENT", "PROD")

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        with pytest.raises(RuntimeError, match="dev_auth.py cannot be imported in production"):
            import scripts.cj_experiments_runners.eng5_np.dev_auth  # noqa: F401

    def test_import_allowed_in_development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Module import succeeds in development environment."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("HULEEDU_ENVIRONMENT", raising=False)

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        # Should not raise
        import scripts.cj_experiments_runners.eng5_np.dev_auth  # noqa: F401

    def test_runtime_check_blocks_production(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gate 2: Runtime check blocks token creation even if module loaded."""
        # Import in development
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("HULEEDU_ENVIRONMENT", raising=False)

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        from scripts.cj_experiments_runners.eng5_np.dev_auth import create_dev_admin_token

        # Change to production after import
        monkeypatch.setenv("ENVIRONMENT", "production")

        # Runtime check should block
        with pytest.raises(RuntimeError, match="forbidden in production"):
            create_dev_admin_token()


class TestDevAuthTokenGeneration:
    """Test JWT token generation in development environment."""

    def test_creates_valid_jwt_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token generation creates valid JWT with expected claims."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-min-32-bytes")

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        from scripts.cj_experiments_runners.eng5_np.dev_auth import create_dev_admin_token

        token = create_dev_admin_token(subject="test-subject")

        # Decode without verification (just inspect claims)
        claims = jwt.decode(token, options={"verify_signature": False})

        assert claims["sub"] == "test-subject"
        assert claims["roles"] == ["admin"]
        assert claims["iss"] == "huleedu-identity-service"
        assert claims["aud"] == "huleedu-platform"
        assert "exp" in claims
        assert "iat" in claims

    def test_token_expiration_set_correctly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Token expiration is set to 1 hour by default."""
        from datetime import timedelta

        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-min-32-bytes")

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        from scripts.cj_experiments_runners.eng5_np.dev_auth import create_dev_admin_token

        token = create_dev_admin_token()
        claims = jwt.decode(token, options={"verify_signature": False})

        exp_time = datetime.fromtimestamp(claims["exp"])
        iat_time = datetime.fromtimestamp(claims["iat"])
        delta = exp_time - iat_time

        # Should be approximately 1 hour (within 5 seconds tolerance)
        expected_delta = timedelta(hours=1)
        assert abs(delta - expected_delta).total_seconds() < 5

    def test_custom_subject_and_org_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom subject and org_id are included in token."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-min-32-bytes")

        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]

        from scripts.cj_experiments_runners.eng5_np.dev_auth import create_dev_admin_token

        token = create_dev_admin_token(subject="custom-subject", org_id="org-123")
        claims = jwt.decode(token, options={"verify_signature": False})

        assert claims["sub"] == "custom-subject"
        assert claims["org_id"] == "org-123"


class TestBuildAdminHeaders:
    """Test build_admin_headers() priority and fallback behavior."""

    def test_uses_service_account_token_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Priority 1: Uses HULEEDU_SERVICE_ACCOUNT_TOKEN if set."""
        monkeypatch.setenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", "service-account-token-xyz")
        monkeypatch.setenv("HULEEDU_ADMIN_TOKEN", "admin-token-abc")
        monkeypatch.setenv("ENVIRONMENT", "development")

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        headers = build_admin_headers()

        assert headers["Authorization"] == "Bearer service-account-token-xyz"
        assert headers["Content-Type"] == "application/json"

    def test_uses_manual_admin_token_second(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Priority 2: Uses HULEEDU_ADMIN_TOKEN if service account not set."""
        monkeypatch.delenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", raising=False)
        monkeypatch.setenv("HULEEDU_ADMIN_TOKEN", "admin-token-abc")
        monkeypatch.setenv("ENVIRONMENT", "development")

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        headers = build_admin_headers()

        assert headers["Authorization"] == "Bearer admin-token-abc"
        assert headers["Content-Type"] == "application/json"

    def test_generates_dev_token_third(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Priority 3: Auto-generates dev token if no env tokens set."""
        monkeypatch.delenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", raising=False)
        monkeypatch.delenv("HULEEDU_ADMIN_TOKEN", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-with-min-32-bytes")

        # Reload module to clear import cache
        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]
        if "scripts.cj_experiments_runners.eng5_np.cj_client" in sys.modules:
            importlib.reload(sys.modules["scripts.cj_experiments_runners.eng5_np.cj_client"])

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        headers = build_admin_headers()

        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer eyJ")  # JWT format
        assert headers["Content-Type"] == "application/json"

    def test_production_blocks_dev_token_generation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """In production without service account token, import fails."""
        monkeypatch.delenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", raising=False)
        monkeypatch.delenv("HULEEDU_ADMIN_TOKEN", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        # Clear module cache
        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]
        if "scripts.cj_experiments_runners.eng5_np.cj_client" in sys.modules:
            importlib.reload(sys.modules["scripts.cj_experiments_runners.eng5_np.cj_client"])

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        # Should raise because dev_auth import will fail
        with pytest.raises(RuntimeError, match="dev_auth.py cannot be imported in production"):
            build_admin_headers()


class TestProductionDeploymentScenarios:
    """Test realistic production deployment scenarios."""

    def test_production_with_service_account_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Production deployment with service account token works correctly."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", "prod-service-token-xyz")

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        headers = build_admin_headers()
        assert headers["Authorization"] == "Bearer prod-service-token-xyz"

    def test_staging_without_token_fails_safely(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Staging without tokens fails with clear error."""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        monkeypatch.delenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", raising=False)
        monkeypatch.delenv("HULEEDU_ADMIN_TOKEN", raising=False)

        # Clear module cache
        if "scripts.cj_experiments_runners.eng5_np.dev_auth" in sys.modules:
            del sys.modules["scripts.cj_experiments_runners.eng5_np.dev_auth"]
        if "scripts.cj_experiments_runners.eng5_np.cj_client" in sys.modules:
            importlib.reload(sys.modules["scripts.cj_experiments_runners.eng5_np.cj_client"])

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        with pytest.raises(RuntimeError, match="dev_auth.py cannot be imported"):
            build_admin_headers()

    def test_development_with_service_account_prefers_service_account(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even in development, service account token is preferred over dev generation."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("HULEEDU_SERVICE_ACCOUNT_TOKEN", "dev-service-token")

        from scripts.cj_experiments_runners.eng5_np.cj_client import build_admin_headers

        headers = build_admin_headers()
        assert headers["Authorization"] == "Bearer dev-service-token"
