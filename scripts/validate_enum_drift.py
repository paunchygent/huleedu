# ruff: noqa: E402

"""Enum drift validator for HuleEdu services.

Checks that all Python enum values used by services are present in the
corresponding Postgres enum types created by Alembic migrations. Fails if any
Python value is missing in the database type (DB may contain extra legacy
values).

# ruff: noqa: E402

Usage:
    pdm run validate-enum-drift
    pdm run validate-enum-drift --strict  # also fails on extra DB values

The script expects local dev databases (docker compose dev) to be running and
credentials in `.env` (HULEEDU_DB_USER / HULEEDU_DB_PASSWORD).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Ensure repository modules resolve when run as a standalone script
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(REPO_ROOT))
sys.path.append(str(REPO_ROOT / "libs" / "common_core" / "src"))

from common_core.status_enums import BatchStatus, CJBatchStateEnum, EssayStatus
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.email_service.models_db import EmailStatus
from services.entitlements_service.models_db import OperationStatus


@dataclass
class EnumCheck:
    service: str
    enum_name: str
    expected: set[str]
    database: str
    port: int
    ignore_missing: set[str] | None = None


SQL = """
SELECT enumlabel
FROM pg_enum e
JOIN pg_type t ON t.oid = e.enumtypid
WHERE t.typname = :enum_name
ORDER BY enumsortorder
"""


def build_connection_url(database: str, port: int) -> str:
    user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
    password = os.getenv("HULEEDU_DB_PASSWORD", "huleedu_password")
    return f"postgresql+asyncpg://{user}:{password}@localhost:{port}/{database}"


async def fetch_db_values(engine: AsyncEngine, enum_name: str) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text(SQL), {"enum_name": enum_name})
        return list(rows.scalars())


async def check_enum(check: EnumCheck, strict: bool) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the given enum."""
    url = build_connection_url(check.database, check.port)
    engine = create_async_engine(url, echo=False)
    try:
        db_values = set(await fetch_db_values(engine, check.enum_name))
    finally:
        await engine.dispose()

    ignored = check.ignore_missing or set()
    missing = (check.expected - db_values) - ignored
    extra = db_values - check.expected if strict else set()

    errors: list[str] = []
    warnings: list[str] = []
    if missing:
        errors.append(
            f"[{check.service}] enum '{check.enum_name}' missing values in DB: {sorted(missing)}"
        )
    ignored_missing_detected = (check.expected - db_values) & ignored
    if ignored_missing_detected:
        warnings.append(
            f"[{check.service}] ignored missing values for '{check.enum_name}': "
            f"{sorted(ignored_missing_detected)} (acknowledged legacy mismatch)"
        )
    if extra:
        msg = (
            f"[{check.service}] enum '{check.enum_name}' has unexpected DB-only values "
            f"(strict mode): {sorted(extra)}"
        )
        errors.append(msg)
    return errors, warnings


def get_checks() -> Iterable[EnumCheck]:
    return [
        EnumCheck(
            service="essay_lifecycle_service",
            enum_name="essay_status_enum",
            expected={v.value for v in EssayStatus},
            database="huleedu_essay_lifecycle",
            port=5433,
        ),
        EnumCheck(
            service="batch_orchestrator_service",
            enum_name="batch_status_enum",
            expected={v.value for v in BatchStatus},
            database="huleedu_batch_orchestrator",
            port=5438,
        ),
        EnumCheck(
            service="result_aggregator_service",
            enum_name="batchstatus",
            expected={v.value for v in BatchStatus},
            database="huleedu_result_aggregator",
            port=5436,
        ),
        EnumCheck(
            service="cj_assessment_service",
            enum_name="cj_batch_status_enum",
            expected={v.value for v in CJBatchStatusEnum},
            database="huleedu_cj_assessment",
            port=5434,
        ),
        EnumCheck(
            service="cj_assessment_service",
            enum_name="cj_batch_state_enum",
            expected={v.value for v in CJBatchStateEnum},
            database="huleedu_cj_assessment",
            port=5434,
        ),
        EnumCheck(
            service="email_service",
            enum_name="email_status_enum",
            expected={v.value for v in EmailStatus},
            database="huleedu_email",
            port=5443,
        ),
        EnumCheck(
            service="entitlements_service",
            enum_name="operation_status_enum",
            expected={v.value for v in OperationStatus},
            database="huleedu_entitlements",
            port=5444,
        ),
    ]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Python enums against DB enums.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail when DB contains extra values not present in Python.",
    )
    args = parser.parse_args()

    load_dotenv()

    checks = list(get_checks())
    all_errors: list[str] = []
    warnings: list[str] = []

    for check in checks:
        errors, warn = await check_enum(check, strict=args.strict)
        all_errors.extend(errors)
        warnings.extend(warn)

    for warn in warnings:
        print(f"⚠️  {warn}")
    if all_errors:
        print("\nEnum drift detected:")
        for err in all_errors:
            print(f" - {err}")
        raise SystemExit(1)

    print("✅ Enum drift check passed (all Python enum values present in DB types).")


if __name__ == "__main__":
    asyncio.run(main())
