#!/usr/bin/env python3
"""
Seed script to populate courses in the Class Management Service database.

This script ensures all CourseCode enum values have corresponding records in the database.
Run this after setting up the database but before running tests.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Imports after sys.path modification
from common_core.domain_enums import CourseCode, Language  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from services.class_management_service.models_db import Course  # noqa: E402


async def seed_courses():
    """Seed all courses defined in CourseCode enum."""
    # Get database credentials from environment
    db_user = os.getenv("HULEEDU_DB_USER")
    db_password = os.getenv("HULEEDU_DB_PASSWORD")
    
    if not db_user or not db_password:
        raise ValueError("HULEEDU_DB_USER and HULEEDU_DB_PASSWORD environment variables must be set")
    db_host = os.getenv("HULEEDU_DB_HOST", "localhost")
    db_port = os.getenv("CLASS_MANAGEMENT_DB_PORT", "5435")
    db_name = "huleedu_class_management"

    database_url = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    print(f"🔗 Connecting to database: {db_name} on port {db_port}")

    # Create engine and session
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Course definitions mapping CourseCode to details
    course_definitions = {
        CourseCode.ENG5: {"name": "English 5", "language": Language.ENGLISH},
        CourseCode.ENG6: {"name": "English 6", "language": Language.ENGLISH},
        CourseCode.ENG7: {"name": "English 7", "language": Language.ENGLISH},
        CourseCode.SV1: {"name": "Svenska 1", "language": Language.SWEDISH},
        CourseCode.SV2: {"name": "Svenska 2", "language": Language.SWEDISH},
        CourseCode.SV3: {"name": "Svenska 3", "language": Language.SWEDISH},
    }

    async with async_session() as session:
        created_count = 0
        existing_count = 0

        for course_code, details in course_definitions.items():
            # Check if course already exists
            result = await session.execute(select(Course).where(Course.course_code == course_code))
            existing_course = result.scalar_one_or_none()

            if not existing_course:
                # Create new course
                new_course = Course(
                    course_code=course_code, name=details["name"], language=details["language"]
                )
                session.add(new_course)
                created_count += 1
                print(f"✅ Created course: {course_code.value} - {details['name']}")
            else:
                existing_count += 1
                print(f"ℹ️  Course already exists: {course_code.value} - {existing_course.name}")

        # Commit all changes
        await session.commit()

        print("\n📊 Summary:")
        print(f"   • Created: {created_count} courses")
        print(f"   • Existing: {existing_count} courses")
        print(f"   • Total: {len(course_definitions)} courses")

    await engine.dispose()
    print("\n✅ Course seeding complete!")


if __name__ == "__main__":
    print("🌱 Starting course seeding for Class Management Service...")
    asyncio.run(seed_courses())
