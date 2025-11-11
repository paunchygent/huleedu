"""Database URL construction utilities for HuleEdu services.

Centralizes database connection string generation with proper password encoding
to handle special characters in URLs.
"""

from __future__ import annotations

from urllib.parse import quote_plus


def build_database_url(
    *,
    database_name: str,
    service_env_var_prefix: str,
    is_production: bool,
    dev_port: int,
    dev_host: str = "localhost",
    url_encode_password: bool = True,
) -> str:
    """Build environment-aware PostgreSQL database URL with proper password encoding.

    Constructs database URLs following HuleEdu standards:
    1. Check for service-specific override env var (SERVICE_DATABASE_URL)
    2. Production: Use HULEEDU_PROD_DB_* variables with URL-encoded password
    3. Development: Use localhost with service-specific port and URL-encoded password

    Password encoding uses urllib.parse.quote_plus() to handle special characters
    like #, @, %, :, /, etc. that have special meaning in URLs.

    Args:
        database_name: Full database name (e.g., 'huleedu_class_management')
        service_env_var_prefix: Service prefix for override var (e.g., 'CLASS_MANAGEMENT_SERVICE')
        is_production: Whether running in production environment
        dev_port: Development database port for localhost connection (e.g., 5435)
        dev_host: Development database host (default: 'localhost'). Use 'service_db'
                  when ENV_TYPE=docker and connecting to containerized database.
        url_encode_password: Whether to URL-encode passwords (default: True, RECOMMENDED).
                           Only set to False for testing or if password is pre-encoded.

    Returns:
        PostgreSQL connection URL with asyncpg driver and properly encoded password.
        Format: postgresql+asyncpg://user:encoded_password@host:port/database

    Raises:
        ValueError: If required credentials are missing for the environment.

    Example:
        >>> from huleedu_service_libs.config.database_utils import build_database_url
        >>> url = build_database_url(
        ...     database_name="huleedu_class_management",
        ...     service_env_var_prefix="CLASS_MANAGEMENT_SERVICE",
        ...     is_production=False,
        ...     dev_port=5435
        ... )
        >>> # Returns: postgresql+asyncpg://huleedu_user:encoded_pass@localhost:5435/huleedu_class_management

    Note:
        This function is designed to be called from service Settings.database_url property.
        It does NOT cache the connection string - caching should be done at the Settings level.
    """
    import os

    # 1. Check for explicit override (Docker environment, manual config, testing)
    override_var = f"{service_env_var_prefix}_DATABASE_URL"
    env_url = os.getenv(override_var)
    if env_url:
        return env_url
    # Fallback: generic override used by some tests and tools
    generic_env_url = os.getenv("SERVICE_DATABASE_URL")
    if generic_env_url:
        return generic_env_url

    # 2. Get shared database user (defaults to huleedu_user) - used for production
    db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")

    if is_production:
        # Production: External managed database
        prod_host = os.getenv("HULEEDU_PROD_DB_HOST")
        prod_port = os.getenv("HULEEDU_PROD_DB_PORT", "5432")
        prod_password = os.getenv("HULEEDU_PROD_DB_PASSWORD")

        if not all([prod_host, prod_password]):
            raise ValueError(
                "Production environment requires HULEEDU_PROD_DB_HOST and "
                "HULEEDU_PROD_DB_PASSWORD environment variables to be set."
            )

        # Type narrowing for mypy - after validation we know these are not None
        assert prod_host is not None
        assert prod_password is not None

        # URL-encode password to handle special characters
        password = quote_plus(prod_password) if url_encode_password else prod_password

        return (
            f"postgresql+asyncpg://{db_user}:{password}@"
            f"{prod_host}:{prod_port}/{database_name}"
        )
    else:
        # Development: Docker container with port mapping or local PostgreSQL
        dev_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not dev_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )

        # URL-encode password to handle special characters
        password = quote_plus(db_password) if url_encode_password else db_password

        return (
            f"postgresql+asyncpg://{dev_user}:{password}@"
            f"{dev_host}:{dev_port}/{database_name}"
        )
