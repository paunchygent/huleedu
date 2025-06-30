#!/usr/bin/env python3
"""
Fixed test isolation script that waits for Kafka topics to be available.

This addresses the critical issue where topics are deleted/recreated
but not available when the consumer starts.
"""

import asyncio
import redis.asyncio as redis
import subprocess


async def clear_test_redis_keys():
    """Clear all test-related Redis keys to ensure test isolation."""
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    try:
        # Clear ALL Redis keys (not just idempotency)
        print("🧹 Clearing ALL Redis data for complete isolation...")
        await redis_client.flushall()
        print("🗑️  Flushed all Redis databases")
        
        # Verify cleanup
        all_keys = await redis_client.keys("*")
        print(f"🔍 Total keys after flush: {len(all_keys)}")
        
    except Exception as e:
        print(f"❌ Error accessing Redis: {e}")
        return False
    finally:
        await redis_client.aclose()
    
    return True


async def reset_kafka_consumer_groups():
    """Reset Kafka consumer groups for test isolation."""
    print("🔄 Resetting Kafka consumer groups...")
    
    consumer_groups = [
        "essay-lifecycle-consumer-group",
        "batch-orchestrator-consumer-group", 
        "spell-checker-consumer-group",
        "cj-assessment-consumer-group",
        "comprehensive_real_batch"
    ]
    
    for group in consumer_groups:
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


async def wait_for_topic_availability(topic: str, max_attempts: int = 20) -> bool:
    """Wait for a specific Kafka topic to be available."""
    describe_cmd = [
        "docker", "exec", "huleedu_kafka",
        "kafka-topics.sh",
        "--bootstrap-server", "localhost:9092",
        "--describe", "--topic", topic
    ]
    
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(describe_cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and "Leader:" in result.stdout:
                return True
            await asyncio.sleep(0.5)
        except Exception:
            await asyncio.sleep(0.5)
    
    return False


async def clear_kafka_topics_with_verification():
    """Clear messages from Kafka topics by recreating them and wait for availability."""
    print("🔄 Clearing Kafka topics with availability verification...")
    
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
    
    # First, delete all topics
    for topic in topics:
        delete_cmd = [
            "docker", "exec", "huleedu_kafka",
            "kafka-topics.sh",
            "--bootstrap-server", "localhost:9092",
            "--delete", "--topic", topic
        ]
        
        try:
            subprocess.run(delete_cmd, capture_output=True, text=True, timeout=5)
            print(f"🗑️  Deleted topic: {topic}")
        except Exception:
            pass
    
    # Wait a bit for deletion to propagate
    await asyncio.sleep(2)
    
    # Now recreate all topics
    for topic in topics:
        create_cmd = [
            "docker", "exec", "huleedu_kafka",
            "kafka-topics.sh",
            "--bootstrap-server", "localhost:9092",
            "--create", "--topic", topic,
            "--partitions", "1",
            "--replication-factor", "1"
        ]
        
        try:
            result = subprocess.run(create_cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                print(f"✅ Created topic: {topic}")
            else:
                print(f"ℹ️  Topic {topic} might already exist")
        except Exception as e:
            print(f"⚠️  Failed to create topic {topic}: {e}")
    
    # CRITICAL: Wait for all topics to be available
    print("\n⏳ Waiting for Kafka topics to become available...")
    all_available = True
    
    for topic in topics:
        print(f"   Checking {topic}...", end="", flush=True)
        if await wait_for_topic_availability(topic):
            print(" ✅")
        else:
            print(" ❌")
            all_available = False
    
    if all_available:
        print("✅ All Kafka topics are available and ready!")
    else:
        print("⚠️  Some topics are not available - test may fail")
    
    return all_available


async def verify_kafka_connectivity():
    """Verify that Kafka is accessible and responsive."""
    print("🔍 Verifying Kafka connectivity...")
    
    list_cmd = [
        "docker", "exec", "huleedu_kafka",
        "kafka-topics.sh",
        "--bootstrap-server", "localhost:9092",
        "--list"
    ]
    
    try:
        result = subprocess.run(list_cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            topic_count = len(result.stdout.strip().split('\n')) if result.stdout.strip() else 0
            print(f"✅ Kafka is responsive - found {topic_count} topics")
            return True
        else:
            print(f"❌ Kafka is not responding properly: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Cannot connect to Kafka: {e}")
        return False


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


def run_e2e_test():
    """Run the E2E test after proper isolation."""
    print("\n🚀 Running E2E comprehensive real batch test...")
    
    cmd = [
        "pdm", "run", "pytest", 
        "tests/functional/test_e2e_comprehensive_real_batch.py::test_comprehensive_real_batch_pipeline",
        "-v", "-s", "--tb=short"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        print("\n📋 Test Output:")
        print("STDOUT:", result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        if result.returncode == 0:
            print("\n✅ Test PASSED!")
        else:
            print(f"\n❌ Test FAILED with return code: {result.returncode}")
            
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("\n⏰ Test timed out after 60 seconds")
        return False
    except Exception as e:
        print(f"\n❌ Error running test: {e}")
        return False


async def main():
    """Main test isolation with Kafka topic availability fix."""
    print("🔬 Testing with COMPLETE isolation + Kafka topic availability fix")
    print("=" * 60)
    
    # Step 1: Verify Kafka connectivity first
    if not await verify_kafka_connectivity():
        print("❌ Kafka is not available - aborting test")
        return False
    
    # Step 2: Clear Redis keys
    if not await clear_test_redis_keys():
        print("❌ Redis cleanup failed - aborting test")
        return False
    
    # Step 3: Clear and verify Kafka topics
    kafka_ready = await clear_kafka_topics_with_verification()
    
    # Step 4: Reset Kafka consumer groups
    await reset_kafka_consumer_groups()
    
    # Step 5: Clear test databases
    await clear_test_databases()
    
    print("\n✅ Complete test environment isolation achieved:")
    print("   - Redis: All keys flushed")
    print("   - Kafka: Topics cleared, verified available, consumer groups deleted")
    print("   - Databases: Test data truncated")
    print("=" * 60)
    
    if not kafka_ready:
        print("\n⚠️  WARNING: Not all Kafka topics are available!")
        print("The test will likely fail due to missing topics.")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return False
    
    # Step 6: Give services a moment to stabilize
    print("\n⏳ Waiting 5 seconds for services to stabilize...")
    await asyncio.sleep(5)
    
    # Step 7: Run the E2E test
    test_success = run_e2e_test()
    
    print("\n" + "=" * 60)
    if test_success:
        print("🎉 SUCCESS! The Kafka topic availability fix worked!")
        print("✅ The E2E test now passes with proper topic verification")
        print("\nKey insight: Topics must be available before consumers start")
    else:
        print("🔍 Test still failed - investigating next issues...")
        print("\nPossible remaining issues:")
        print("1. Authentication for file upload")
        print("2. Service health check endpoints")
        print("3. Deterministic ID generation")
    
    return test_success


if __name__ == "__main__":
    asyncio.run(main())