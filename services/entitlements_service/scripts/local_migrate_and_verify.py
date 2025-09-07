"""
Run Alembic migrations against a disposable Postgres (testcontainers) and verify outbox indexes.

Requirements:
  - Docker available locally
  - testcontainers installed (already used by integration tests)

Usage:
  pdm run python services/entitlements_service/scripts/local_migrate_and_verify.py
"""

from __future__ import annotations

import os
import subprocess
import sys

from testcontainers.postgres import PostgresContainer


def _to_asyncpg_url(url: str) -> str:
    url = url.replace("+psycopg2://", "+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


def run() -> int:
    # Start Postgres container
    container = PostgresContainer("postgres:15")
    container.start()
    try:
        sync_url = container.get_connection_url()
        async_url = _to_asyncpg_url(sync_url)

        env = os.environ.copy()
        env["ENTITLEMENTS_SERVICE_DATABASE_URL"] = async_url

        # Apply migrations from service directory
        print("Applying Alembic migrations to disposable database...")
        res = subprocess.run(
            ["pdm", "run", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
        )
        if res.returncode != 0:
            print("ERROR: alembic upgrade failed", file=sys.stderr)
            return res.returncode

        # Verify outbox indexes
        print("Verifying outbox indexes...")
        res2 = subprocess.run(
            [
                "python",
                os.path.join(
                    os.path.dirname(__file__),
                    "verify_outbox_indexes.py",
                ),
                "--database-url",
                async_url,
            ],
            env=env,
        )
        if res2.returncode != 0:
            print("ERROR: outbox index verification failed", file=sys.stderr)
            return res2.returncode

        print("SUCCESS: Migrations applied and outbox indexes verified.")
        return 0
    finally:
        container.stop()


if __name__ == "__main__":
    raise SystemExit(run())
