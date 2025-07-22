"""
Single operation performance tests for Class Management Service.

Tests baseline performance for individual educational operations.
Starts with short durations (10 seconds) to prove the pattern works.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import pytest
from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1

from services.class_management_service.api_models import CreateClassRequest, CreateStudentRequest
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.tests.performance.conftest import (
    EducationalPerformanceMetrics,
    measure_async_operation,
)


@pytest.mark.asyncio
class TestSingleOperationPerformance:
    """Test individual operation performance to establish baselines."""

    async def test_single_class_creation_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Test baseline performance for single class creation."""
        # Arrange
        teacher_id = "performance-teacher-001"
        class_request = CreateClassRequest(
            name="Performance Test Class", course_codes=[CourseCode.ENG5]
        )

        # Act - measure single operation
        duration, result, success = await measure_async_operation(
            performance_repository.create_class, teacher_id, class_request, uuid.uuid4()
        )

        # Assert - baseline performance thresholds
        assert success, f"Class creation failed: {result}"
        assert duration < 0.500, f"Class creation took {duration:.3f}s, expected < 0.500s"
        assert result is not None, "Class creation returned None"
        assert result.name == "Performance Test Class"
        assert result.course.course_code == CourseCode.ENG5

        # Record metrics
        performance_metrics.record_operation("class_creation", duration, success)

        print(f"✓ Single class creation: {duration:.3f}s")

    async def test_single_student_enrollment_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Test baseline performance for single student enrollment."""
        # Arrange
        teacher_id = "performance-teacher-002"
        student_request = CreateStudentRequest(
            person_name=PersonNameV1(first_name="Performance", last_name="Student"),
            email="performance.student@school.edu",
        )

        # Act - measure single operation
        duration, result, success = await measure_async_operation(
            performance_repository.create_student, teacher_id, student_request, uuid.uuid4()
        )

        # Assert - baseline performance thresholds
        assert success, f"Student enrollment failed: {result}"
        assert duration < 0.300, f"Student enrollment took {duration:.3f}s, expected < 0.300s"
        assert result is not None, "Student enrollment returned None"
        assert result.first_name == "Performance"
        assert result.last_name == "Student"
        assert result.email == "performance.student@school.edu"

        # Record metrics
        performance_metrics.record_operation("student_enrollment", duration, success)

        print(f"✓ Single student enrollment: {duration:.3f}s")

    async def test_sequential_operations_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Test performance of sequential operations (typical teacher workflow)."""
        # Arrange
        teacher_id = "performance-teacher-003"

        # Create class first
        class_request = CreateClassRequest(
            name="Sequential Test Class", course_codes=[CourseCode.SV1]
        )

        class_duration, class_result, class_success = await measure_async_operation(
            performance_repository.create_class, teacher_id, class_request, uuid.uuid4()
        )

        assert class_success, "Class creation failed in sequential test"
        performance_metrics.record_operation("class_creation", class_duration, class_success)

        # Create multiple students for the class
        student_requests = [
            CreateStudentRequest(
                person_name=PersonNameV1(first_name=f"Sequential{i}", last_name=f"Student{i}"),
                email=f"sequential{i}@school.edu",
            )
            for i in range(1, 6)  # 5 students
        ]

        total_enrollment_time = 0.0
        for student_request in student_requests:
            duration, result, success = await measure_async_operation(
                performance_repository.create_student, teacher_id, student_request, uuid.uuid4()
            )

            assert success, f"Student enrollment failed: {result}"
            performance_metrics.record_operation("student_enrollment", duration, success)
            total_enrollment_time += duration

        # Assert - sequential operations should be efficient
        avg_enrollment_time = total_enrollment_time / len(student_requests)
        assert avg_enrollment_time < 0.250, (
            f"Average enrollment time {avg_enrollment_time:.3f}s too high"
        )

        print(
            f"✓ Sequential operations: class={class_duration:.3f}s, "
            f"avg_enrollment={avg_enrollment_time:.3f}s"
        )

    async def test_short_burst_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Test performance with short burst of operations (10 seconds max)."""
        # Arrange
        teacher_id = "performance-teacher-004"

        # Create 5 classes rapidly (burst scenario)
        class_requests = [
            CreateClassRequest(name=f"Burst Class {i}", course_codes=[CourseCode.ENG6])
            for i in range(1, 6)
        ]

        # Act - measure burst operations
        start_time = time.perf_counter()
        results = []

        for class_request in class_requests:
            duration, result, success = await measure_async_operation(
                performance_repository.create_class, teacher_id, class_request, uuid.uuid4()
            )

            results.append((duration, success))
            performance_metrics.record_operation("class_creation", duration, success)

            # Small delay to simulate realistic burst (not hammering)
            await asyncio.sleep(0.1)

        total_burst_time = time.perf_counter() - start_time

        # Assert - burst operations performance
        assert total_burst_time < 10.0, f"Burst test took {total_burst_time:.3f}s, expected < 10s"

        success_count = sum(1 for _, success in results if success)
        assert success_count == len(class_requests), (
            f"Only {success_count}/{len(class_requests)} operations succeeded"
        )

        avg_operation_time = sum(duration for duration, _ in results) / len(results)
        assert avg_operation_time < 0.500, (
            f"Average operation time {avg_operation_time:.3f}s too high"
        )

        print(
            f"✓ Burst operations: {success_count}/{len(class_requests)} succeeded, "
            f"avg={avg_operation_time:.3f}s"
        )

    async def test_database_connection_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Test database connection reuse performance."""
        # Arrange
        teacher_id = "performance-teacher-005"

        # Measure connection time for first operation (cold start)
        first_request = CreateClassRequest(name="Connection Test 1", course_codes=[CourseCode.SV2])

        first_duration, first_result, first_success = await measure_async_operation(
            performance_repository.create_class, teacher_id, first_request, uuid.uuid4()
        )

        assert first_success, "First operation failed"
        performance_metrics.record_database_connection(first_duration)

        # Measure subsequent operations (should reuse connection)
        subsequent_times = []
        for i in range(2, 6):  # 4 more operations
            request = CreateClassRequest(name=f"Connection Test {i}", course_codes=[CourseCode.SV2])

            duration, result, success = await measure_async_operation(
                performance_repository.create_class, teacher_id, request, uuid.uuid4()
            )

            assert success, f"Operation {i} failed"
            subsequent_times.append(duration)
            performance_metrics.record_database_connection(duration)

        # Assert - connection reuse should be faster
        avg_subsequent = sum(subsequent_times) / len(subsequent_times)

        # Connection reuse should be at least as fast as first connection
        assert avg_subsequent <= first_duration * 1.2, (
            f"Connection reuse not efficient: first={first_duration:.3f}s, "
            f"avg={avg_subsequent:.3f}s"
        )

        print(
            f"✓ Database connections: first={first_duration:.3f}s, avg_reuse={avg_subsequent:.3f}s"
        )

    async def test_performance_summary(
        self,
        performance_metrics: EducationalPerformanceMetrics,
    ) -> None:
        """Print performance summary after all tests."""
        # This test should run last to show summary
        print("\n" + "=" * 60)
        print("SINGLE OPERATION PERFORMANCE SUMMARY")
        print("=" * 60)

        stats = performance_metrics.get_educational_statistics()

        for operation_type, operation_stats in stats.items():
            if operation_type in ["database_performance", "event_publishing"]:
                continue

            if operation_stats.get("total_operations", 0) > 0:
                print(f"\n{operation_type.upper()}:")
                print(f"  Operations: {operation_stats['total_operations']}")
                print(f"  Success rate: {operation_stats['success_rate']:.1f}%")
                print(f"  Mean time: {operation_stats['response_times']['mean']:.3f}s")
                print(f"  P95 time: {operation_stats['response_times']['p95']:.3f}s")

        print("\n" + "=" * 60)

        # Basic assertions for overall performance
        class_stats = stats.get("class_creation", {})
        if class_stats.get("total_operations", 0) > 0:
            assert class_stats["success_rate"] >= 99.0, "Class creation success rate too low"
            assert class_stats["response_times"]["mean"] < 0.500, (
                "Class creation mean time too high"
            )

        student_stats = stats.get("student_enrollment", {})
        if student_stats.get("total_operations", 0) > 0:
            assert student_stats["success_rate"] >= 99.0, "Student enrollment success rate too low"
            assert student_stats["response_times"]["mean"] < 0.300, (
                "Student enrollment mean time too high"
            )
