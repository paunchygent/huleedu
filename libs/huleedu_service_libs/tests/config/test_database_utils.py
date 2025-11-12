from __future__ import annotations

from urllib.parse import quote_plus

import pytest

from huleedu_service_libs.config.database_utils import build_database_url


class TestBuildDatabaseUrl:
    def test_service_specific_override(self) -> None:
        override = "postgresql+asyncpg://u:p@h:5432/db"
        env = {
            "IDENTITY_SERVICE_DATABASE_URL": override,
            "HULEEDU_DB_USER": "ignored",
            "HULEEDU_DB_PASSWORD": "ignored",
        }
        with pytest.MonkeyPatch().context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            url = build_database_url(
                database_name="huleedu_identity",
                service_env_var_prefix="IDENTITY_SERVICE",
                is_production=False,
                dev_port=5442,
            )
        assert url == override

    def test_generic_override(self) -> None:
        override = "postgresql+asyncpg://u:p@h:5432/db"
        env = {
            "SERVICE_DATABASE_URL": override,
            "HULEEDU_DB_USER": "ignored",
            "HULEEDU_DB_PASSWORD": "ignored",
        }
        with pytest.MonkeyPatch().context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            url = build_database_url(
                database_name="huleedu_identity",
                service_env_var_prefix="IDENTITY_SERVICE",
                is_production=False,
                dev_port=5442,
            )
        assert url == override

    def test_production_encoding_with_special_chars(self) -> None:
        env = {
            "HULEEDU_DB_USER": "huleedu_user",
            "HULEEDU_PROD_DB_HOST": "prod.db.local",
            "HULEEDU_PROD_DB_PORT": "5432",
            "HULEEDU_PROD_DB_PASSWORD": "omT9VJ#1cvqPjuMzP5exdGp9h#m3zmQn",
        }
        with pytest.MonkeyPatch().context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            url = build_database_url(
                database_name="huleedu_identity",
                service_env_var_prefix="IDENTITY_SERVICE",
                is_production=True,
                dev_port=5442,
            )
        expected_pw = quote_plus(env["HULEEDU_PROD_DB_PASSWORD"])
        assert url == (
            f"postgresql+asyncpg://huleedu_user:{expected_pw}@prod.db.local:5432/huleedu_identity"
        )

    def test_development_encoding_with_special_chars(self) -> None:
        env = {
            "HULEEDU_DB_USER": "huleedu_user",
            "HULEEDU_DB_PASSWORD": "pa#ss:@/w?rd&=100%",
        }
        with pytest.MonkeyPatch().context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            url = build_database_url(
                database_name="huleedu_identity",
                service_env_var_prefix="IDENTITY_SERVICE",
                is_production=False,
                dev_port=5442,
                dev_host="localhost",
            )
        expected_pw = quote_plus(env["HULEEDU_DB_PASSWORD"])
        assert url == (
            f"postgresql+asyncpg://huleedu_user:{expected_pw}@localhost:5442/huleedu_identity"
        )

    def test_development_missing_credentials_raises(self) -> None:
        with pytest.MonkeyPatch().context() as mp:
            mp.delenv("HULEEDU_DB_USER", raising=False)
            mp.delenv("HULEEDU_DB_PASSWORD", raising=False)
            with pytest.raises(ValueError):
                _ = build_database_url(
                    database_name="huleedu_identity",
                    service_env_var_prefix="IDENTITY_SERVICE",
                    is_production=False,
                    dev_port=5442,
                )

    def test_disable_url_encoding(self) -> None:
        env = {
            "HULEEDU_DB_USER": "huleedu_user",
            "HULEEDU_DB_PASSWORD": "pa#ss",
        }
        with pytest.MonkeyPatch().context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            url = build_database_url(
                database_name="huleedu_identity",
                service_env_var_prefix="IDENTITY_SERVICE",
                is_production=False,
                dev_port=5442,
                dev_host="localhost",
                url_encode_password=False,
            )
        assert url == ("postgresql+asyncpg://huleedu_user:pa#ss@localhost:5442/huleedu_identity")

    def test_custom_dev_host(self) -> None:
        env = {
            "HULEEDU_DB_USER": "huleedu_user",
            "HULEEDU_DB_PASSWORD": "password",
        }
        with pytest.MonkeyPatch().context() as mp:
            for k, v in env.items():
                mp.setenv(k, v)
            url = build_database_url(
                database_name="huleedu_identity",
                service_env_var_prefix="IDENTITY_SERVICE",
                is_production=False,
                dev_port=5432,
                dev_host="identity_db",
            )
        assert url == (
            "postgresql+asyncpg://huleedu_user:password@identity_db:5432/huleedu_identity"
        )
