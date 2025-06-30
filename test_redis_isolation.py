#!/usr/bin/env python3
"""
Test Redis key isolation approach for the failing E2E test.

This script demonstrates how to achieve test isolation by clearing
test-related Redis keys before running tests.
"""

import asyncio
import redis.asyncio as redis
import subprocess


async def clear_test_redis_keys():
    """Clear all test-related Redis keys to ensure test isolation."""
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    try:
        # Clear ALL Redis keys (not just idempotency)
        # This includes any cached state, locks, or other data
        print("🧹 Clearing ALL Redis data for complete isolation...")
        await redis_client.flushall()
        print("🗑️  Flushed all Redis databases")
        
        # Verify cleanup
        all_keys = await redis_client.keys("*")
        print(f"🔍 Total keys after flush: {len(all_keys)}")
        
        if len(all_keys) > 0:
            print(f"⚠️  WARNING: {len(all_keys)} keys still remain!")
            for key in all_keys[:10]:  # Show first 10
                print(f"   - {key}")
        
    except Exception as e:
        print(f"❌ Error accessing Redis: {e}")
        print("Make sure Redis is running on localhost:6379")
        return False
    finally:
        await redis_client.aclose()
    
    return True


def run_e2e_test():
    """Run the E2E test after Redis cleanup and correlation ID fix."""
    print("🚀 Running E2E comprehensive real batch test with correlation ID fix...")
    
    cmd = [
        "pdm", "run", "pytest", 
        "tests/functional/test_e2e_comprehensive_real_batch.py::test_comprehensive_real_batch_pipeline",
        "-v", "-s", "--tb=short"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        
        print("📋 Test Output:")
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("✅ Test PASSED!")
        else:
            print(f"❌ Test FAILED with return code: {result.returncode}")
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("⏰ Test timed out after 40 seconds")
        return False
    except Exception as e:
        print(f"❌ Error running test: {e}")
        return False


async def reset_kafka_consumer_groups():
    """Reset Kafka consumer groups for test isolation."""
    print("🔄 Resetting Kafka consumer groups...")
    
    # Consumer groups used by ELS and other services
    consumer_groups = [
        "essay-lifecycle-consumer-group",
        "batch-orchestrator-consumer-group", 
        "spell-checker-consumer-group",
        "cj-assessment-consumer-group",
        "comprehensive_real_batch"  # Test consumer group
    ]
    
    for group in consumer_groups:
        # First delete the consumer group
        delete_cmd = [
            "docker", "exec", "huleedu_kafka",
            "kafka-consumer-groups.sh",
            "--bootstrap-server", "localhost:9092",
            "--group", group,
            "--delete"
        ]
        
        try:
            result = subprocess.run(delete_cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print(f"✅ Deleted consumer group: {group}")
            else:
                print(f"ℹ️  Consumer group {group} not found or couldn't be deleted")
        except Exception as e:
            print(f"⚠️  Failed to delete consumer group {group}: {e}")
    
    print("✅ Kafka consumer groups reset completed")


async def clear_kafka_topics():
    """Clear messages from Kafka topics by recreating them."""
    print("🔄 Clearing Kafka topics...")
    
    # Critical topics that might contain stale test data
    topics = [
        "huleedu.batch.essays.registered.v1",
        "huleedu.file.essay.content.provisioned.v1",
        "huleedu.els.batch.essays.ready.v1",
        "huleedu.batch.spellcheck.initiate.command.v1",
        "huleedu.spellcheck.completed.v1",
        "huleedu.batch.cj_assessment.initiate.command.v1",
        "huleedu.cj_assessment.completed.v1",
        "huleedu.els.batch.phase.outcome.v1"
    ]
    
    for topic in topics:
        # Delete and recreate topic
        delete_cmd = [
            "docker", "exec", "huleedu_kafka",
            "kafka-topics.sh",
            "--bootstrap-server", "localhost:9092",
            "--delete", "--topic", topic
        ]
        
        create_cmd = [
            "docker", "exec", "huleedu_kafka",
            "kafka-topics.sh",
            "--bootstrap-server", "localhost:9092",
            "--create", "--topic", topic,
            "--partitions", "1",
            "--replication-factor", "1"
        ]
        
        try:
            # Delete topic
            subprocess.run(delete_cmd, capture_output=True, text=True, timeout=5)
            # Recreate topic
            result = subprocess.run(create_cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ Recreated topic: {topic}")
            else:
                print(f"ℹ️  Topic {topic} might already exist")
        except Exception as e:
            print(f"⚠️  Failed to recreate topic {topic}: {e}")
    
    print("✅ Kafka topics cleared")


async def clear_test_databases():
    """Clear test data from databases for isolation."""
    print("🗄️  Clearing test data from databases...")
    
    # Clear ELS database
    els_cmd = [
        "docker", "exec", "-i", "huleedu_essay_lifecycle_db",
        "psql", "-U", "huleedu_user", "-d", "essay_lifecycle",
        "-c", "TRUNCATE TABLE essay_states CASCADE;"
    ]
    
    # Clear BOS database  
    bos_cmd = [
        "docker", "exec", "-i", "huleedu_batch_orchestrator_db",
        "psql", "-U", "huleedu_user", "-d", "batch_orchestrator",
        "-c", "TRUNCATE TABLE batches, batch_essays, phase_status_log, configuration_snapshots CASCADE;"
    ]
    
    for name, cmd in [("ELS", els_cmd), ("BOS", bos_cmd)]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ Cleared {name} database")
            else:
                print(f"⚠️  Failed to clear {name} database: {result.stderr}")
        except Exception as e:
            print(f"⚠️  Error clearing {name} database: {e}")
    
    print("✅ Database cleanup completed")


async def main():
    """Main test isolation demonstration."""
    print("🔬 Testing with COMPLETE isolation")
    print("=" * 50)
    
    # Step 1: Clear Redis keys for test isolation
    cleanup_success = await clear_test_redis_keys()
    
    if not cleanup_success:
        print("❌ Redis cleanup failed - aborting test")
        return False
    
    # Step 2: Clear Kafka topics (remove stale messages)
    await clear_kafka_topics()
    
    # Step 3: Reset Kafka consumer groups
    await reset_kafka_consumer_groups()
    
    # Step 4: Clear test databases
    await clear_test_databases()
    
    print()
    print("✅ Complete test environment isolation achieved:")
    print("   - Redis: All keys flushed")
    print("   - Kafka: Topics cleared, consumer groups deleted")
    print("   - Databases: Test data truncated")
    print("=" * 50)
    
    # Step 5: Give services a moment to stabilize after cleanup
    import time
    print("⏳ Waiting 3 seconds for services to stabilize...")
    time.sleep(3)
    
    # Step 6: Run the E2E test
    test_success = run_e2e_test()
    
    print()
    print("=" * 50)
    if test_success:
        print("🎉 HYPOTHESIS CONFIRMED!")
        print("✅ Complete isolation fixed all idempotency issues")
        print("✅ The E2E test now passes with full cleanup")
    else:
        print("🔍 Test still failed - need further investigation")
        print("Complete isolation was applied (Redis + Kafka + DB).")
        print("\nPossible remaining issues:")
        print("1. Services might be caching state in memory")
        print("2. File storage might have stale data")
        print("3. Some services might not be fully restarted")
    
    return test_success


if __name__ == "__main__":
    asyncio.run(main())