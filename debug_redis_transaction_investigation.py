#!/usr/bin/env python3
"""
ULTRATHINK Debug Script: Redis Transaction and Database Integrity Investigation
Purpose: Analyze the complete state of Redis transactions, database constraints, and system behavior
"""

import asyncio
from uuid import uuid4

from huleedu_service_libs.redis_client import RedisClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Test configuration
REDIS_URL = "redis://localhost:6379"
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5433/essay_lifecycle"


async def investigate_redis_state():
    """Agent Alpha: Redis State Inspector"""
    print("\n=== AGENT ALPHA: Redis State Investigation ===")
    
    redis_client = RedisClient(client_id="debug-redis", redis_url=REDIS_URL)
    await redis_client.start()
    
    try:
        # Check for any existing batch data
        batch_keys = await redis_client.scan_pattern("batch:*")
        print(f"Found {len(batch_keys)} batch-related keys in Redis")
        
        for key in batch_keys[:5]:  # Sample first 5
            key_type = await redis_client.client.type(key)
            print(f"  Key: {key}, Type: {key_type}")
            
            if key_type == "set":
                members = await redis_client.client.smembers(key)
                print(f"    Members: {len(members)} items")
            elif key_type == "hash":
                fields = await redis_client.client.hkeys(key)
                print(f"    Fields: {fields}")
        
        # Test transaction behavior
        print("\n--- Testing Redis Transaction Pattern ---")
        test_batch_id = f"debug_test_{uuid4().hex[:8]}"
        slots_key = f"batch:{test_batch_id}:available_slots"
        assignments_key = f"batch:{test_batch_id}:assignments"
        
        # Add test slots
        await redis_client.sadd(slots_key, "slot1", "slot2", "slot3")
        
        # Test transaction
        await redis_client.watch(slots_key, assignments_key)
        await redis_client.multi()
        
        # This should queue the operation, not execute
        result = await redis_client.spop(slots_key)
        print(f"SPOP during transaction returned: {result} (should be None)")
        
        # Execute transaction
        exec_results = await redis_client.exec()
        print(f"EXEC results: {exec_results}")
        
        # Verify final state
        remaining = await redis_client.scard(slots_key)
        print(f"Remaining slots: {remaining} (should be 2)")
        
        # Cleanup
        await redis_client.client.delete(slots_key, assignments_key)
        
    finally:
        await redis_client.stop()


async def investigate_database_constraints():
    """Agent Beta: Database Constraint Analyzer"""
    print("\n=== AGENT BETA: Database Constraint Investigation ===")
    
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Check existing constraints
        result = await session.execute(text("""
            SELECT 
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name,
                tc.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_schema = 'public'
                AND tc.table_name IN ('essay', 'batch_expectation')
            ORDER BY tc.table_name, tc.constraint_type;
        """))
        
        constraints = result.fetchall()
        print(f"Found {len(constraints)} constraints:")
        for constraint in constraints:
            print(f"  {constraint.table_name}.{constraint.column_name}: {constraint.constraint_type} ({constraint.constraint_name})")
        
        # Check for duplicate data patterns
        print("\n--- Checking for Duplicate Patterns ---")
        result = await session.execute(text("""
            SELECT batch_id, text_storage_id, COUNT(*) as count
            FROM essay
            WHERE batch_id IS NOT NULL AND text_storage_id IS NOT NULL
            GROUP BY batch_id, text_storage_id
            HAVING COUNT(*) > 1
            LIMIT 5;
        """))
        
        duplicates = result.fetchall()
        if duplicates:
            print(f"Found {len(duplicates)} duplicate (batch_id, text_storage_id) combinations!")
            for dup in duplicates:
                print(f"  Batch: {dup.batch_id}, Storage: {dup.text_storage_id}, Count: {dup.count}")
        else:
            print("No duplicates found in existing data")
        
        # Check batch_expectation state
        result = await session.execute(text("""
            SELECT batch_id, expected_count, created_at
            FROM batch_expectation
            ORDER BY created_at DESC
            LIMIT 5;
        """))
        
        expectations = result.fetchall()
        print(f"\n--- Recent Batch Expectations ({len(expectations)} found) ---")
        for exp in expectations:
            print(f"  Batch: {exp.batch_id}, Expected: {exp.expected_count}, Created: {exp.created_at}")
    
    await engine.dispose()


async def test_concurrent_operations():
    """Agent Charlie: Concurrency Stress Tester"""
    print("\n=== AGENT CHARLIE: Concurrent Operation Testing ===")
    
    redis_client = RedisClient(client_id="debug-concurrent", redis_url=REDIS_URL)
    await redis_client.start()
    
    try:
        test_batch_id = f"concurrent_test_{uuid4().hex[:8]}"
        slots_key = f"batch:{test_batch_id}:available_slots"
        
        # Add 10 slots
        slots = [f"essay_{i}" for i in range(10)]
        await redis_client.sadd(slots_key, *slots)
        
        # Simulate 5 concurrent slot assignments
        async def assign_slot(client_id: int):
            await redis_client.watch(slots_key)
            await redis_client.multi()
            await redis_client.spop(slots_key)
            result = await redis_client.exec()
            return result
        
        print("Simulating 5 concurrent slot assignments...")
        tasks = [assign_slot(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        failed = sum(1 for r in results if r is None)
        errors = sum(1 for r in results if isinstance(r, Exception))
        
        print(f"Results: {successful} successful, {failed} failed transactions, {errors} errors")
        print(f"Transaction results: {results}")
        
        remaining = await redis_client.scard(slots_key)
        print(f"Remaining slots: {remaining} (should be 5)")
        
        # Cleanup
        await redis_client.client.delete(slots_key)
        
    finally:
        await redis_client.stop()


async def analyze_integration_flow():
    """Agent Delta: Integration Flow Analyzer"""
    print("\n=== AGENT DELTA: Integration Flow Analysis ===")
    
    # This would analyze the actual flow but for now we'll check the patterns
    print("Analyzing Essay Lifecycle Service integration patterns...")
    
    # Check if services are healthy
    import httpx
    async with httpx.AsyncClient() as client:
        services = [
            ("Essay Lifecycle API", "http://localhost:6000/healthz"),
            ("Content Service", "http://localhost:5000/healthz"),
            ("File Service", "http://localhost:7000/healthz"),
        ]
        
        for name, url in services:
            try:
                response = await client.get(url, timeout=2.0)
                status = "HEALTHY" if response.status_code == 200 else f"UNHEALTHY ({response.status_code})"
            except Exception as e:
                status = f"UNREACHABLE ({type(e).__name__})"
            print(f"  {name}: {status}")


async def main():
    """ULTRATHINK Coordinator: Execute all agent investigations"""
    print("=" * 80)
    print("ULTRATHINK INVESTIGATION: Redis Transaction & Database Integrity")
    print("=" * 80)
    
    # Deploy all agents
    await investigate_redis_state()
    await investigate_database_constraints()
    await test_concurrent_operations()
    await analyze_integration_flow()
    
    print("\n" + "=" * 80)
    print("INVESTIGATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())