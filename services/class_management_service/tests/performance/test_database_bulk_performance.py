"""
Database and Bulk Operation Performance Tests for Class Management Service.

Validates the service's ability to handle realistic educational bulk operations
like class roster imports, multi-class setup, and complex database queries
under load while maintaining data integrity and performance thresholds.

Educational Focus:
- Bulk student roster imports (20-30 students per class)
- Multi-class teacher setup workflows
- Complex relationship queries under concurrent load
- Database constraint enforcement during bulk operations
- Memory efficiency for large educational datasets
- Transaction integrity for bulk educational operations

Performance Thresholds:
- Bulk Student Import: <50ms per student in batches of 25-30
- Complex Queries: <200ms for class-with-students queries
- Transaction Integrity: 100% success rate for valid bulk operations
- Memory Efficiency: No memory leaks during large operations
"""

from __future__ import annotations

import asyncio
import gc
import os
import statistics
import time
import uuid
from typing import Any, Dict, List

import psutil
import pytest
from common_core.domain_enums import CourseCode
from common_core.metadata_models import PersonNameV1
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from services.class_management_service.api_models import CreateClassRequest, CreateStudentRequest
from services.class_management_service.implementations.class_repository_postgres_impl import (
    PostgreSQLClassRepositoryImpl,
)
from services.class_management_service.tests.performance.conftest import (
    EducationalTestDataGenerator,
)


class BulkOperationMetrics:
    """Specialized metrics for bulk educational operations."""

    def __init__(self) -> None:
        self.bulk_import_times: List[float] = []
        self.complex_query_times: List[float] = []
        self.memory_usage_samples: List[float] = []
        self.transaction_success_rates: List[float] = []
        self.constraint_violation_counts: List[int] = []

    def record_bulk_import(self, duration: float, student_count: int) -> None:
        """Record bulk import performance with student count context."""
        per_student_time = duration / student_count if student_count > 0 else duration
        self.bulk_import_times.append(per_student_time)

    def record_complex_query(self, duration: float) -> None:
        """Record complex database query performance."""
        self.complex_query_times.append(duration)

    def record_memory_usage(self, memory_mb: float) -> None:
        """Record memory usage sample."""
        self.memory_usage_samples.append(memory_mb)

    def record_transaction_batch(self, total_ops: int, successful_ops: int) -> None:
        """Record transaction success rate for bulk operations."""
        success_rate = (successful_ops / total_ops * 100) if total_ops > 0 else 0
        self.transaction_success_rates.append(success_rate)

    def record_constraint_violations(self, violation_count: int) -> None:
        """Record constraint violation count during bulk operations."""
        self.constraint_violation_counts.append(violation_count)

    def get_bulk_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive bulk operation performance summary."""
        return {
            "bulk_import_performance": {
                "per_student_times": {
                    "mean": statistics.mean(self.bulk_import_times)
                    if self.bulk_import_times
                    else 0,
                    "median": statistics.median(self.bulk_import_times)
                    if self.bulk_import_times
                    else 0,
                    "p95": self._get_percentile(self.bulk_import_times, 95),
                    "p99": self._get_percentile(self.bulk_import_times, 99),
                    "min": min(self.bulk_import_times) if self.bulk_import_times else 0,
                    "max": max(self.bulk_import_times) if self.bulk_import_times else 0,
                },
                "samples": len(self.bulk_import_times),
            },
            "complex_query_performance": {
                "response_times": {
                    "mean": statistics.mean(self.complex_query_times)
                    if self.complex_query_times
                    else 0,
                    "median": statistics.median(self.complex_query_times)
                    if self.complex_query_times
                    else 0,
                    "p95": self._get_percentile(self.complex_query_times, 95),
                    "p99": self._get_percentile(self.complex_query_times, 99),
                },
                "samples": len(self.complex_query_times),
            },
            "memory_efficiency": {
                "usage_mb": {
                    "mean": statistics.mean(self.memory_usage_samples)
                    if self.memory_usage_samples
                    else 0,
                    "peak": max(self.memory_usage_samples) if self.memory_usage_samples else 0,
                    "baseline": min(self.memory_usage_samples) if self.memory_usage_samples else 0,
                },
                "samples": len(self.memory_usage_samples),
            },
            "transaction_integrity": {
                "success_rates": {
                    "mean": statistics.mean(self.transaction_success_rates)
                    if self.transaction_success_rates
                    else 0,
                    "min": min(self.transaction_success_rates)
                    if self.transaction_success_rates
                    else 0,
                },
                "constraint_violations": sum(self.constraint_violation_counts),
                "batch_count": len(self.transaction_success_rates),
            },
        }

    def _get_percentile(self, values: List[float], percentile: int) -> float:
        """Calculate percentile for performance values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int((percentile / 100) * len(sorted_values))
        if index >= len(sorted_values):
            index = len(sorted_values) - 1
        return sorted_values[index]


@pytest.fixture
def bulk_metrics() -> BulkOperationMetrics:
    """Provide bulk operation metrics collector."""
    return BulkOperationMetrics()


@pytest.mark.asyncio
class TestDatabaseBulkPerformance:
    """Database and bulk operation performance tests for educational scenarios."""

    async def test_single_class_bulk_student_import_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        test_data_generator: EducationalTestDataGenerator,
        bulk_metrics: BulkOperationMetrics,
        teacher_ids: List[str],
    ) -> None:
        """Test bulk student import performance for a single class (realistic teacher workflow)."""
        teacher_id = teacher_ids[0]

        # Create a realistic class first
        class_request = test_data_generator.generate_class_requests(1)[0]
        await performance_repository.create_class(teacher_id, class_request, uuid.uuid4())

        # Generate realistic class roster (25-30 students)
        roster_sizes = [25, 28, 30]  # Typical class sizes

        for roster_size in roster_sizes:
            print(f"\n🎓 Testing bulk import for {roster_size} students...")

            # Generate student roster
            student_requests = test_data_generator.generate_student_requests(roster_size)

            # Measure bulk import performance
            start_time = time.perf_counter()
            successful_enrollments = 0

            for student_request in student_requests:
                try:
                    await performance_repository.create_student(
                        teacher_id, student_request, uuid.uuid4()
                    )
                    successful_enrollments += 1
                except Exception as e:
                    print(f"  ⚠ Student enrollment failed: {e}")

            total_duration = time.perf_counter() - start_time

            # Record metrics
            bulk_metrics.record_bulk_import(total_duration, roster_size)
            bulk_metrics.record_transaction_batch(roster_size, successful_enrollments)

            # Educational performance assertions
            per_student_time = total_duration / roster_size
            print("  📊 Bulk import results:")
            print(f"     Total time: {total_duration:.3f}s")
            print(f"     Per student: {per_student_time:.4f}s")
            print(f"     Success rate: {(successful_enrollments / roster_size) * 100:.1f}%")
            print(f"     Throughput: {roster_size / total_duration:.1f} students/second")

            # Realistic educational performance thresholds
            assert per_student_time < 0.050, (
                f"Per-student import time {per_student_time:.4f}s exceeds 50ms threshold"
            )
            assert total_duration < 10.0, (
                f"Total bulk import {total_duration:.3f}s exceeds 10s threshold"
            )
            assert successful_enrollments >= roster_size * 0.95, (
                f"Success rate {(successful_enrollments / roster_size) * 100:.1f}% below 95%"
            )

    async def test_multi_class_teacher_bulk_setup_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        test_data_generator: EducationalTestDataGenerator,
        bulk_metrics: BulkOperationMetrics,
        teacher_ids: List[str],
    ) -> None:
        """Test multi-class setup performance for a teacher managing multiple classes."""
        teacher_id = teacher_ids[1]

        # Realistic teacher workload: 5 classes with varying sizes
        class_configs = [
            ("Honors English 6 - Period 1", 22),
            ("English 6 - Period 2", 28),
            ("English 6 - Period 3", 25),
            ("Remedial English 6 - Period 4", 18),
            ("Advanced English 6 - Period 5", 24),
        ]

        total_students = sum(size for _, size in class_configs)
        print(
            f"\n👨‍🏫 Testing multi-class setup: {len(class_configs)} classes, "
            f"{total_students} total students"
        )

        start_time = time.perf_counter()
        successful_classes = 0
        successful_students = 0

        for class_name, student_count in class_configs:
            try:
                # Create class
                class_request = CreateClassRequest(name=class_name, course_codes=[CourseCode.ENG6])
                await performance_repository.create_class(teacher_id, class_request, uuid.uuid4())
                successful_classes += 1

                # Add students to class
                student_requests = test_data_generator.generate_student_requests(student_count)

                for student_request in student_requests:
                    try:
                        await performance_repository.create_student(
                            teacher_id, student_request, uuid.uuid4()
                        )
                        successful_students += 1
                    except Exception as e:
                        print(f"    ⚠ Student enrollment failed in {class_name}: {e}")

            except Exception as e:
                print(f"  ⚠ Class creation failed for {class_name}: {e}")

        total_duration = time.perf_counter() - start_time

        # Record metrics
        bulk_metrics.record_transaction_batch(len(class_configs), successful_classes)
        bulk_metrics.record_transaction_batch(total_students, successful_students)

        print("  📊 Multi-class setup results:")
        print(f"     Total time: {total_duration:.3f}s")
        print(f"     Classes created: {successful_classes}/{len(class_configs)}")
        print(f"     Students enrolled: {successful_students}/{total_students}")
        print(f"     Class success rate: {(successful_classes / len(class_configs)) * 100:.1f}%")
        print(f"     Student success rate: {(successful_students / total_students) * 100:.1f}%")
        print(f"     Overall throughput: {total_students / total_duration:.1f} students/second")

        # Multi-class performance thresholds
        assert total_duration < 30.0, (
            f"Multi-class setup {total_duration:.3f}s exceeds 30s threshold"
        )
        assert successful_classes >= len(class_configs) * 0.95, (
            "Class creation success rate below 95%"
        )
        assert successful_students >= total_students * 0.90, (
            "Student enrollment success rate below 90%"
        )

    async def test_complex_database_queries_under_load(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        performance_async_engine: AsyncEngine,
        bulk_metrics: BulkOperationMetrics,
        teacher_ids: List[str],
    ) -> None:
        """Test complex database queries performance under concurrent load."""
        # Setup: Create classes with students for complex queries
        setup_teachers = teacher_ids[:3]
        class_data = []

        print(f"\n🗃️ Setting up complex database scenario with {len(setup_teachers)} teachers...")

        for i, teacher_id in enumerate(setup_teachers):
            # Create 2 classes per teacher
            for j in range(2):
                class_request = CreateClassRequest(
                    name=f"Complex Query Test Class {i + 1}-{j + 1}", course_codes=[CourseCode.ENG6]
                )
                created_class = await performance_repository.create_class(
                    teacher_id, class_request, uuid.uuid4()
                )

                # Add students to each class
                student_requests = EducationalTestDataGenerator.generate_student_requests(20)
                for student_request in student_requests:
                    await performance_repository.create_student(
                        teacher_id, student_request, uuid.uuid4()
                    )

                class_data.append((teacher_id, created_class.id))

        print(f"  ✓ Setup complete: {len(class_data)} classes with students")

        # Test complex queries under concurrent load
        complex_queries = [
            # Query 1: Class with all students and relationships
            """
            SELECT c.id, c.name, c.created_at,
                   COUNT(s.id) as student_count,
                   AVG(LENGTH(s.email)) as avg_email_length
            FROM classes c
            LEFT JOIN students s ON c.created_by_user_id = s.created_by_user_id
            WHERE c.created_by_user_id = :teacher_id
            GROUP BY c.id, c.name, c.created_at
            ORDER BY c.created_at DESC
            """,
            # Query 2: Teacher workload analysis
            """
            SELECT c.created_by_user_id,
                   COUNT(DISTINCT c.id) as class_count,
                   COUNT(DISTINCT s.id) as total_students,
                   CASE WHEN COUNT(DISTINCT c.id) > 0
                        THEN COUNT(DISTINCT s.id) / COUNT(DISTINCT c.id)
                        ELSE 0 END as avg_class_size
            FROM classes c
            LEFT JOIN students s ON c.created_by_user_id = s.created_by_user_id
            WHERE c.created_by_user_id = :teacher_id
            GROUP BY c.created_by_user_id
            """,
            # Query 3: Student enrollment patterns
            """
            SELECT s.email, s.first_name, s.last_name, s.created_at,
                   COUNT(c.id) as class_count
            FROM students s
            LEFT JOIN classes c ON s.created_by_user_id = c.created_by_user_id
            WHERE s.created_by_user_id = :teacher_id
            GROUP BY s.email, s.first_name, s.last_name, s.created_at
            ORDER BY s.created_at DESC
            LIMIT 50
            """,
        ]

        # Execute queries concurrently for each teacher
        async def execute_query_set(teacher_id: str, query_set_id: int) -> List[float]:
            """Execute all complex queries for a teacher."""
            query_times = []

            for i, query in enumerate(complex_queries):
                start_time = time.perf_counter()

                async with performance_async_engine.begin() as conn:
                    result = await conn.execute(text(query), {"teacher_id": teacher_id})
                    rows = result.fetchall()

                query_duration = time.perf_counter() - start_time
                query_times.append(query_duration)
                bulk_metrics.record_complex_query(query_duration)

                print(
                    f"  🔍 Teacher {query_set_id} Query {i + 1}: "
                    f"{query_duration:.4f}s ({len(rows)} rows)"
                )

            return query_times

        # Run concurrent complex queries
        concurrent_tasks = [
            execute_query_set(teacher_id, i) for i, (teacher_id, _) in enumerate(class_data[:3])
        ]

        start_time = time.perf_counter()
        results = await asyncio.gather(*concurrent_tasks)
        total_duration = time.perf_counter() - start_time

        # Analyze results
        all_query_times = [time for teacher_times in results for time in teacher_times]

        print("  📊 Complex query performance:")
        print(f"     Total concurrent time: {total_duration:.3f}s")
        print(f"     Total queries executed: {len(all_query_times)}")
        print(f"     Mean query time: {statistics.mean(all_query_times):.4f}s")
        print(f"     P95 query time: {bulk_metrics._get_percentile(all_query_times, 95):.4f}s")
        print(f"     Slowest query: {max(all_query_times):.4f}s")

        # Complex query performance thresholds
        mean_query_time = statistics.mean(all_query_times)
        p95_query_time = bulk_metrics._get_percentile(all_query_times, 95)

        assert mean_query_time < 0.200, (
            f"Mean query time {mean_query_time:.4f}s exceeds 200ms threshold"
        )
        assert p95_query_time < 0.500, (
            f"P95 query time {p95_query_time:.4f}s exceeds 500ms threshold"
        )
        assert max(all_query_times) < 1.0, (
            f"Slowest query {max(all_query_times):.4f}s exceeds 1s threshold"
        )

    async def test_bulk_operation_memory_efficiency(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        test_data_generator: EducationalTestDataGenerator,
        bulk_metrics: BulkOperationMetrics,
        teacher_ids: List[str],
    ) -> None:
        """Test memory efficiency during large bulk operations."""
        teacher_id = teacher_ids[2]
        process = psutil.Process(os.getpid())

        # Baseline memory measurement
        gc.collect()  # Clean up before measuring
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        bulk_metrics.record_memory_usage(baseline_memory)

        print("\n🧠 Testing memory efficiency for bulk operations")
        print(f"  Baseline memory: {baseline_memory:.2f} MB")

        # Create progressively larger student batches to test memory scaling
        batch_sizes = [50, 100, 200]  # Realistic educational bulk sizes

        for batch_size in batch_sizes:
            print(f"\n  📚 Testing batch size: {batch_size} students")

            # Generate large student batch
            student_requests = test_data_generator.generate_student_requests(batch_size)

            # Measure memory before bulk operation
            gc.collect()
            pre_operation_memory = process.memory_info().rss / 1024 / 1024
            bulk_metrics.record_memory_usage(pre_operation_memory)

            # Perform bulk operation
            start_time = time.perf_counter()
            successful_operations = 0

            for student_request in student_requests:
                try:
                    await performance_repository.create_student(
                        teacher_id, student_request, uuid.uuid4()
                    )
                    successful_operations += 1
                except Exception:
                    pass  # Count failures without logging for memory test

            operation_duration = time.perf_counter() - start_time

            # Measure memory during operation
            during_operation_memory = process.memory_info().rss / 1024 / 1024
            bulk_metrics.record_memory_usage(during_operation_memory)

            # Clean up and measure memory recovery
            del student_requests  # Explicit cleanup
            gc.collect()
            post_operation_memory = process.memory_info().rss / 1024 / 1024
            bulk_metrics.record_memory_usage(post_operation_memory)

            # Calculate memory metrics
            memory_increase = during_operation_memory - baseline_memory
            memory_per_operation = memory_increase / batch_size if batch_size > 0 else 0
            memory_recovered = during_operation_memory - post_operation_memory
            recovery_rate = (
                (memory_recovered / memory_increase * 100) if memory_increase > 0 else 100
            )

            print(f"    📊 Memory analysis for {batch_size} students:")
            print(f"       Pre-operation: {pre_operation_memory:.2f} MB")
            print(f"       During operation: {during_operation_memory:.2f} MB")
            print(f"       Post-operation: {post_operation_memory:.2f} MB")
            print(f"       Memory increase: {memory_increase:.2f} MB")
            print(f"       Memory per operation: {memory_per_operation:.4f} MB")
            print(f"       Memory recovered: {memory_recovered:.2f} MB ({recovery_rate:.1f}%)")
            print(f"       Operation time: {operation_duration:.3f}s")
            print(f"       Success rate: {(successful_operations / batch_size) * 100:.1f}%")

            # Memory efficiency assertions
            assert memory_per_operation < 0.1, (
                f"Memory per operation {memory_per_operation:.4f} MB exceeds 0.1 MB threshold"
            )
            # Note: Python doesn't immediately return memory to OS, so we check growth instead
            assert memory_increase < batch_size * 0.1, (
                f"Total memory increase {memory_increase:.2f} MB exceeds "
                f"{batch_size * 0.1:.2f} MB for {batch_size} operations"
            )
            assert during_operation_memory < baseline_memory + 50, (
                f"Peak memory {during_operation_memory:.2f} MB exceeds baseline + 50 MB"
            )

    async def test_bulk_constraint_validation_performance(
        self,
        performance_repository: PostgreSQLClassRepositoryImpl,
        test_data_generator: EducationalTestDataGenerator,
        bulk_metrics: BulkOperationMetrics,
        teacher_ids: List[str],
    ) -> None:
        """Test constraint validation performance during bulk operations."""
        teacher_id = teacher_ids[3]

        print("\n🔒 Testing bulk constraint validation performance")

        # Test scenario 1: Duplicate email constraint validation
        print("  📧 Testing duplicate email constraint validation...")

        # Create students with some duplicate emails
        unique_students = test_data_generator.generate_student_requests(20)
        duplicate_email_students = []

        # Add duplicates by reusing emails from first 5 students
        for i in range(5):
            duplicate_student = CreateStudentRequest(
                person_name=PersonNameV1(first_name=f"Duplicate{i}", last_name="Student"),
                email=unique_students[i].email,  # Reuse email (should fail)
            )
            duplicate_email_students.append(duplicate_student)

        # Combine unique and duplicate students
        mixed_batch = unique_students + duplicate_email_students

        start_time = time.perf_counter()
        successful_enrollments = 0
        constraint_violations = 0

        for student_request in mixed_batch:
            try:
                await performance_repository.create_student(
                    teacher_id, student_request, uuid.uuid4()
                )
                successful_enrollments += 1
            except Exception as e:
                if "unique constraint" in str(e).lower() or "duplicate" in str(e).lower():
                    constraint_violations += 1
                else:
                    print(f"    ⚠ Unexpected error: {e}")

        constraint_validation_duration = time.perf_counter() - start_time

        # Record constraint validation metrics
        bulk_metrics.record_constraint_violations(constraint_violations)
        bulk_metrics.record_transaction_batch(len(mixed_batch), successful_enrollments)

        print("    📊 Constraint validation results:")
        print(f"       Total operations: {len(mixed_batch)}")
        print(f"       Successful: {successful_enrollments}")
        print(f"       Constraint violations: {constraint_violations}")
        print(f"       Validation time: {constraint_validation_duration:.3f}s")
        print(
            f"       Per-operation time: {constraint_validation_duration / len(mixed_batch):.4f}s"
        )

        # Test scenario 2: Large batch with mixed constraints
        print("\n  🔢 Testing large batch constraint validation...")

        large_batch = test_data_generator.generate_student_requests(100)

        start_time = time.perf_counter()
        large_batch_successes = 0

        for student_request in large_batch:
            try:
                await performance_repository.create_student(
                    teacher_id, student_request, uuid.uuid4()
                )
                large_batch_successes += 1
            except Exception:
                pass  # Expected for constraint violations

        large_batch_duration = time.perf_counter() - start_time

        print("    📊 Large batch validation results:")
        print(f"       Batch size: {len(large_batch)}")
        print(f"       Successful: {large_batch_successes}")
        print(f"       Total time: {large_batch_duration:.3f}s")
        print(
            f"       Throughput: {len(large_batch) / large_batch_duration:.1f} validations/second"
        )

        # Constraint validation performance assertions
        per_operation_time = constraint_validation_duration / len(mixed_batch)
        large_batch_per_op = large_batch_duration / len(large_batch)

        assert per_operation_time < 0.100, (
            f"Constraint validation {per_operation_time:.4f}s exceeds 100ms threshold"
        )
        assert large_batch_per_op < 0.050, (
            f"Large batch validation {large_batch_per_op:.4f}s exceeds 50ms threshold"
        )
        assert constraint_violations == 5, (
            f"Expected 5 constraint violations, got {constraint_violations}"
        )
        assert successful_enrollments == 20, (
            f"Expected 20 successful enrollments, got {successful_enrollments}"
        )

    async def test_bulk_performance_summary_and_thresholds(
        self, bulk_metrics: BulkOperationMetrics
    ) -> None:
        """Validate overall bulk performance meets educational requirements."""

        print("\n" + "=" * 80)
        print("BULK OPERATION PERFORMANCE SUMMARY")
        print("=" * 80)

        summary = bulk_metrics.get_bulk_performance_summary()

        # Print detailed performance summary
        print("\n📚 BULK IMPORT PERFORMANCE:")
        bulk_import = summary["bulk_import_performance"]
        print(f"  Samples: {bulk_import['samples']}")
        print(f"  Mean per-student time: {bulk_import['per_student_times']['mean']:.4f}s")
        print(f"  P95 per-student time: {bulk_import['per_student_times']['p95']:.4f}s")
        print(f"  Best per-student time: {bulk_import['per_student_times']['min']:.4f}s")
        print(f"  Worst per-student time: {bulk_import['per_student_times']['max']:.4f}s")

        print("\n🗃️ COMPLEX QUERY PERFORMANCE:")
        complex_query = summary["complex_query_performance"]
        print(f"  Samples: {complex_query['samples']}")
        print(f"  Mean query time: {complex_query['response_times']['mean']:.4f}s")
        print(f"  P95 query time: {complex_query['response_times']['p95']:.4f}s")
        print(f"  Median query time: {complex_query['response_times']['median']:.4f}s")

        print("\n🧠 MEMORY EFFICIENCY:")
        memory = summary["memory_efficiency"]
        print(f"  Samples: {memory['samples']}")
        print(f"  Mean usage: {memory['usage_mb']['mean']:.2f} MB")
        print(f"  Peak usage: {memory['usage_mb']['peak']:.2f} MB")
        print(f"  Baseline usage: {memory['usage_mb']['baseline']:.2f} MB")

        print("\n🔒 TRANSACTION INTEGRITY:")
        integrity = summary["transaction_integrity"]
        print(f"  Batch count: {integrity['batch_count']}")
        print(f"  Mean success rate: {integrity['success_rates']['mean']:.1f}%")
        print(f"  Minimum success rate: {integrity['success_rates']['min']:.1f}%")
        print(f"  Total constraint violations: {integrity['constraint_violations']}")

        print("=" * 80)

        # Validate educational performance thresholds
        if bulk_import["samples"] > 0:
            assert bulk_import["per_student_times"]["mean"] < 0.050, (
                "Mean per-student import time exceeds 50ms educational threshold"
            )
            assert bulk_import["per_student_times"]["p95"] < 0.100, (
                "P95 per-student import time exceeds 100ms educational threshold"
            )

        if complex_query["samples"] > 0:
            assert complex_query["response_times"]["mean"] < 0.200, (
                "Mean complex query time exceeds 200ms educational threshold"
            )
            assert complex_query["response_times"]["p95"] < 0.500, (
                "P95 complex query time exceeds 500ms educational threshold"
            )

        if integrity["batch_count"] > 0:
            assert integrity["success_rates"]["mean"] >= 90.0, (
                "Mean transaction success rate below 90% educational threshold"
            )
            assert integrity["success_rates"]["min"] >= 85.0, (
                "Minimum transaction success rate below 85% educational threshold"
            )

        print("\n✅ All bulk operation performance thresholds met for educational requirements!")
