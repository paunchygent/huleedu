"""
Alembic environment configuration for File Service.

This module configures Alembic to work with the File Service database,
handling both online and offline migrations with proper async support.
"""

from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncEngine

# Add project root to Python path for imports
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

# Now we can import from the project
# Load configuration
from dotenv import find_dotenv, load_dotenv

from libs.huleedu_service_libs.src.huleedu_service_libs.outbox.models import Base as OutboxBase

load_dotenv(find_dotenv(".env"))

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
# Currently File Service only uses the outbox table, but can be extended
target_metadata = OutboxBase.metadata


def get_url() -> str:
    """Get database URL following secure configuration pattern."""
    # Check for environment variable first (Docker environment)
    env_url = os.getenv("FILE_SERVICE_DATABASE_URL")
    if env_url:
        url = env_url
    else:
        # Fallback to local development configuration
        db_user = os.getenv("HULEEDU_DB_USER")
        db_password = os.getenv("HULEEDU_DB_PASSWORD")

        if not db_user or not db_password:
            raise ValueError(
                "Missing required database credentials. Please ensure HULEEDU_DB_USER and "
                "HULEEDU_DB_PASSWORD are set in your .env file."
            )

        # File Service specific database
        db_name = "file_service_db"
        db_host = os.getenv("HULEEDU_DB_HOST", "localhost")
        db_port = os.getenv("HULEEDU_DB_PORT", "5439")  # File Service specific port

        url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    # Convert asyncpg to psycopg2 for synchronous operations
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql://")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    # Get the database URL (will be async version)
    url = get_url()
    # Convert back to async for online mode
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")

    # Create async engine configuration
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = url

    # Create async engine
    connectable = AsyncEngine(
        engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
            future=True,
        )
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
