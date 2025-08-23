#!/usr/bin/env python3
"""
Comprehensive Database Initialization Script for HuleEdu Services.

This script ensures all service databases are properly initialized with:
1. Applied migrations (via Alembic)
2. Seeded reference data (courses, etc.)

Run this after docker-compose up or database reset.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# Service database configuration
SERVICE_DB_CONFIG = {
    "batch_orchestrator_service": {
        "port": 5438,
        "db_name": "huleedu_batch_orchestrator",
        "has_alembic": True,
        "needs_seed": False,
    },
    "class_management_service": {
        "port": 5435,
        "db_name": "huleedu_class_management",
        "has_alembic": True,
        "needs_seed": True,  # Needs courses seeded
    },
    "essay_lifecycle_service": {
        "port": 5433,
        "db_name": "huleedu_essay_lifecycle",
        "has_alembic": True,
        "needs_seed": False,
    },
    "cj_assessment_service": {
        "port": 5434,
        "db_name": "huleedu_cj_assessment",
        "has_alembic": True,
        "needs_seed": False,
    },
    "result_aggregator_service": {
        "port": 5436,
        "db_name": "huleedu_result_aggregator",
        "has_alembic": True,
        "needs_seed": False,
    },
    "spellchecker_service": {
        "port": 5437,
        "db_name": "huleedu_spellchecker",
        "has_alembic": True,
        "needs_seed": False,
    },
    "file_service": {
        "port": 5439,
        "db_name": "huleedu_file_service",
        "has_alembic": True,
        "needs_seed": False,
    },
    "nlp_service": {
        "port": 5440,
        "db_name": "huleedu_nlp",
        "has_alembic": True,
        "needs_seed": False,
    },
}


def run_command(cmd: str, cwd: str = None) -> Tuple[bool, str, str]:
    """Run a shell command and return success status, stdout, and stderr."""
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=30
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_database_connection(service: str, config: Dict) -> bool:
    """Check if database is accessible."""
    db_user = os.getenv("HULEEDU_DB_USER")
    db_password = os.getenv("HULEEDU_DB_PASSWORD")
    
    if not db_user or not db_password:
        raise ValueError("HULEEDU_DB_USER and HULEEDU_DB_PASSWORD environment variables must be set")

    cmd = (
        f"PGPASSWORD={db_password} psql -h localhost -p {config['port']} "
        f"-U {db_user} -d {config['db_name']} -c '\\dt' 2>&1"
    )
    success, _, _ = run_command(cmd)

    return success


def check_migration_status(service: str) -> Tuple[bool, str]:
    """Check current migration status for a service."""
    service_dir = project_root / "services" / service
    cmd = "../../.venv/bin/alembic current 2>&1"

    success, stdout, stderr = run_command(cmd, cwd=str(service_dir))

    if success or "Context impl PostgresqlImpl" in stdout + stderr:
        # Parse the output to see if migrations are applied
        output = stdout + stderr
        if "head" in output.lower() or "(head)" in output:
            return True, "At head revision"
        elif "Running upgrade" in output:
            return False, "Migrations pending"
        else:
            return False, "No migrations applied"

    return False, f"Error checking status: {stderr}"


def apply_migrations(service: str) -> Tuple[bool, str]:
    """Apply all pending migrations for a service."""
    print(f"  📦 Applying migrations for {service}...")

    service_dir = project_root / "services" / service
    cmd = "../../.venv/bin/alembic upgrade head"

    success, stdout, stderr = run_command(cmd, cwd=str(service_dir))

    if success:
        # Count how many migrations were applied
        migration_count = stdout.count("Running upgrade")
        if migration_count > 0:
            return True, f"Applied {migration_count} migration(s)"
        else:
            return True, "Already at head revision"
    else:
        return False, f"Migration failed: {stderr}"


async def seed_courses():
    """Seed course reference data for Class Management Service."""
    from common_core.domain_enums import CourseCode, Language
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from services.class_management_service.models_db import Course

    db_user = os.getenv("HULEEDU_DB_USER")
    db_password = os.getenv("HULEEDU_DB_PASSWORD")
    
    if not db_user or not db_password:
        raise ValueError("HULEEDU_DB_USER and HULEEDU_DB_PASSWORD environment variables must be set")
    database_url = (
        f"postgresql+asyncpg://{db_user}:{db_password}@localhost:5435/huleedu_class_management"
    )

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    course_definitions = {
        CourseCode.ENG5: {"name": "English 5", "language": Language.ENGLISH},
        CourseCode.ENG6: {"name": "English 6", "language": Language.ENGLISH},
        CourseCode.ENG7: {"name": "English 7", "language": Language.ENGLISH},
        CourseCode.SV1: {"name": "Svenska 1", "language": Language.SWEDISH},
        CourseCode.SV2: {"name": "Svenska 2", "language": Language.SWEDISH},
        CourseCode.SV3: {"name": "Svenska 3", "language": Language.SWEDISH},
    }

    created = 0
    async with async_session() as session:
        for course_code, details in course_definitions.items():
            result = await session.execute(select(Course).where(Course.course_code == course_code))
            if not result.scalar_one_or_none():
                new_course = Course(
                    course_code=course_code, name=details["name"], language=details["language"]
                )
                session.add(new_course)
                created += 1

        await session.commit()

    await engine.dispose()
    return created


def main():
    """Main initialization workflow."""
    print("🚀 HuleEdu Database Initialization")
    print("=" * 50)

    # Load environment variables
    env_file = project_root / ".env"
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(env_file)
        print("✅ Loaded environment variables from .env")

    # Track results
    results = {
        "migrations_applied": [],
        "migrations_failed": [],
        "already_migrated": [],
        "seeded": [],
        "connection_failed": [],
    }

    # Process each service
    for service, config in SERVICE_DB_CONFIG.items():
        print(f"\n📋 Processing: {service}")
        print("-" * 40)

        # Check database connection
        if not check_database_connection(service, config):
            print(f"  ❌ Database connection failed (port {config['port']})")
            results["connection_failed"].append(service)
            continue

        print(f"  ✅ Database accessible on port {config['port']}")

        # Check and apply migrations if service has Alembic
        if config["has_alembic"]:
            is_migrated, status = check_migration_status(service)

            if not is_migrated:
                success, message = apply_migrations(service)
                if success:
                    print(f"  ✅ Migrations: {message}")
                    results["migrations_applied"].append(service)
                else:
                    print(f"  ❌ Migrations: {message}")
                    results["migrations_failed"].append(service)
            else:
                print(f"  ℹ️  Migrations: {status}")
                results["already_migrated"].append(service)

    # Seed reference data
    print("\n📋 Seeding Reference Data")
    print("-" * 40)

    # Seed courses for Class Management Service
    if "class_management_service" not in results["connection_failed"]:
        print("  🌱 Seeding courses...")
        try:
            created = asyncio.run(seed_courses())
            print(f"  ✅ Seeded {created} new course(s)")
            results["seeded"].append("courses")
        except Exception as e:
            print(f"  ❌ Failed to seed courses: {e}")

    # Summary
    print("\n" + "=" * 50)
    print("📊 SUMMARY")
    print("=" * 50)

    print(f"✅ Migrations Applied: {len(results['migrations_applied'])}")
    if results["migrations_applied"]:
        for service in results["migrations_applied"]:
            print(f"   • {service}")

    print(f"ℹ️  Already Migrated: {len(results['already_migrated'])}")
    if results["already_migrated"]:
        for service in results["already_migrated"]:
            print(f"   • {service}")

    if results["migrations_failed"]:
        print(f"❌ Migrations Failed: {len(results['migrations_failed'])}")
        for service in results["migrations_failed"]:
            print(f"   • {service}")

    if results["connection_failed"]:
        print(f"❌ Connection Failed: {len(results['connection_failed'])}")
        for service in results["connection_failed"]:
            print(f"   • {service}")

    if results["seeded"]:
        print(f"🌱 Data Seeded: {', '.join(results['seeded'])}")

    # Exit code
    if results["migrations_failed"] or results["connection_failed"]:
        print("\n⚠️  Some operations failed. Please check the logs above.")
        sys.exit(1)
    else:
        print("\n✅ All databases initialized successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
