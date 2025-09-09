"""
Monorepo Outbox Index Verification across services using testcontainers.

For each curated service:
  - Start a disposable Postgres
  - Apply that service's Alembic migrations
  - Run the generic outbox index verifier against the DB

Exit codes:
  0 = All services verified successfully
  >0 = Number of services that failed verification (capped at 255)
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from subprocess import TimeoutExpired
from typing import Iterable

from testcontainers.postgres import PostgresContainer

# Make testcontainers and our own prints visible immediately
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@dataclass
class ServiceSpec:
    name: str
    workdir: str
    db_env_var: str


def _to_asyncpg_url(url: str) -> str:
    url = url.replace("+psycopg2://", "+asyncpg://")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


CURATED_SERVICES: list[ServiceSpec] = [
    ServiceSpec(
        "entitlements_service", "services/entitlements_service", "ENTITLEMENTS_SERVICE_DATABASE_URL"
    ),
    ServiceSpec(
        "class_management_service",
        "services/class_management_service",
        "CLASS_MANAGEMENT_SERVICE_DATABASE_URL",
    ),
    ServiceSpec(
        "essay_lifecycle_service",
        "services/essay_lifecycle_service",
        "ESSAY_LIFECYCLE_SERVICE_DATABASE_URL",
    ),
    ServiceSpec(
        "result_aggregator_service",
        "services/result_aggregator_service",
        "RESULT_AGGREGATOR_SERVICE_DATABASE_URL",
    ),
    ServiceSpec("nlp_service", "services/nlp_service", "NLP_SERVICE_DATABASE_URL"),
    ServiceSpec(
        "batch_orchestrator_service",
        "services/batch_orchestrator_service",
        "BATCH_ORCHESTRATOR_SERVICE_DATABASE_URL",
    ),
    ServiceSpec("email_service", "services/email_service", "EMAIL_SERVICE_DATABASE_URL"),
    ServiceSpec("identity_service", "services/identity_service", "IDENTITY_SERVICE_DATABASE_URL"),
    ServiceSpec("file_service", "services/file_service", "FILE_SERVICE_DATABASE_URL"),
    ServiceSpec(
        "cj_assessment_service",
        "services/cj_assessment_service",
        "CJ_ASSESSMENT_SERVICE_DATABASE_URL",
    ),
]


def _run_alembic_upgrade(workdir: str, env: dict, timeout: int) -> tuple[bool, str]:
    """Run alembic upgrade with fallback for multiple heads.

    Returns (ok, note) where note describes fallback used if any.
    """
    try:
        res = subprocess.run(
            ["pdm", "run", "alembic", "upgrade", "head"],
            cwd=workdir,
            env=env,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except TimeoutExpired:
        return False, "alembic upgrade head timed out"

    if res.returncode == 0:
        # Stream captured output minimally to aid debugging
        if res.stdout:
            print(res.stdout, end="", flush=True)
        if res.stderr:
            print(res.stderr, end="", flush=True)
        return True, ""

    stderr = res.stderr or ""
    if "Multiple head revisions" in stderr or "Multiple heads" in stderr:
        print("Detected multiple head revisions; retrying with 'alembic upgrade heads'", flush=True)
        try:
            res2 = subprocess.run(
                ["pdm", "run", "alembic", "upgrade", "heads"],
                cwd=workdir,
                env=env,
                timeout=timeout,
                capture_output=True,
                text=True,
            )
        except TimeoutExpired:
            return False, "alembic upgrade heads timed out"
        if res2.stdout:
            print(res2.stdout, end="", flush=True)
        if res2.stderr:
            print(res2.stderr, end="", flush=True)
        return (res2.returncode == 0), (
            "used 'heads' due to multiple heads"
            if res2.returncode == 0
            else "alembic upgrade heads failed"
        )

    # Unknown failure – emit stderr to help diagnosis
    if stderr:
        print(stderr, end="", flush=True)
    return False, "alembic upgrade failed"


def verify_service(
    spec: ServiceSpec, migrate_timeout: int = 240, verify_timeout: int = 120
) -> bool:
    print(f"\n=== Verifying outbox indexes for {spec.name} ===", flush=True)
    print("Starting Postgres test container (postgres:15)...", flush=True)
    container = PostgresContainer("postgres:15")
    try:
        container.start()
    except Exception as e:
        print(
            f"[FAIL] Could not start Postgres container for {spec.name}: {e}",
            file=sys.stderr,
            flush=True,
        )
        return False
    try:
        sync_url = container.get_connection_url()
        async_url = _to_asyncpg_url(sync_url)

        env = os.environ.copy()
        env[spec.db_env_var] = async_url

        # Apply migrations for the service
        print(f"Postgres ready. Applying Alembic migrations for {spec.name}...", flush=True)
        ok, note = _run_alembic_upgrade(spec.workdir, env, timeout=migrate_timeout)
        if not ok:
            print(
                f"[FAIL] Alembic upgrade failed for {spec.name} ({note})",
                file=sys.stderr,
                flush=True,
            )
            return False

        # Verify outbox indexes using shared verifier
        print(f"Verifying outbox index alignment for {spec.name}...", flush=True)
        verifier = "services/entitlements_service/scripts/verify_outbox_indexes.py"
        try:
            res2 = subprocess.run(
                ["python", verifier, "--database-url", async_url], env=env, timeout=verify_timeout
            )
        except TimeoutExpired:
            print(
                f"[FAIL] Outbox index verification timed out for {spec.name}",
                file=sys.stderr,
                flush=True,
            )
            return False
        if res2.returncode != 0:
            print(
                f"[FAIL] Outbox index verification failed for {spec.name}",
                file=sys.stderr,
                flush=True,
            )
            return False

        print(f"[OK] {spec.name} outbox indexes aligned.", flush=True)
        return True
    finally:
        container.stop()


def _select_services(only: Iterable[str] | None) -> list[ServiceSpec]:
    if not only:
        return CURATED_SERVICES
    only_set = {name.strip() for name in only}
    return [s for s in CURATED_SERVICES if s.name in only_set]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify outbox index alignment across services")
    parser.add_argument(
        "--only", nargs="*", help="Limit to specific services by name", default=None
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument(
        "--migrate-timeout", type=int, default=240, help="Seconds before migration times out"
    )
    parser.add_argument(
        "--verify-timeout", type=int, default=120, help="Seconds before verify times out"
    )
    args = parser.parse_args()

    failures = 0
    selected = _select_services(args.only)
    if not selected:
        print("No services selected; nothing to do.")
        return 0

    for spec in selected:
        ok = verify_service(
            spec, migrate_timeout=args.migrate_timeout, verify_timeout=args.verify_timeout
        )
        if not ok:
            failures += 1
            if args.fail_fast:
                break

    if failures == 0:
        print("\nSUCCESS: All selected services verified.")
        return 0
    print(f"\nFAIL: {failures} service(s) failed verification.")
    return min(255, failures)


if __name__ == "__main__":
    raise SystemExit(main())
