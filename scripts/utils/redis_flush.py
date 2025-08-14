#!/usr/bin/env python3
"""
Redis Flush Utility for Test Cleanup

This utility ensures complete Redis cleanup for test isolation by flushing all data.
Use this when tests are hanging due to stale idempotency keys or other Redis state.
"""

import subprocess
import sys

def flush_redis(container_name: str = "huleedu_redis") -> bool:
    """
    Flush all data from Redis container.
    
    Args:
        container_name: Name of the Redis Docker container
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if container exists and is running
        check_cmd = ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True, check=True)
        
        if container_name not in check_result.stdout:
            print(f"❌ Redis container '{container_name}' is not running")
            return False
        
        # Execute FLUSHALL command
        flush_cmd = ["docker", "exec", container_name, "redis-cli", "FLUSHALL"]
        result = subprocess.run(flush_cmd, capture_output=True, text=True, check=True)
        
        if "OK" in result.stdout:
            print(f"✅ Successfully flushed all data from Redis container '{container_name}'")
            return True
        else:
            print(f"⚠️ Unexpected Redis response: {result.stdout}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to flush Redis: {e}")
        print(f"   stdout: {e.stdout}")
        print(f"   stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def verify_redis_empty(container_name: str = "huleedu_redis") -> bool:
    """
    Verify that Redis is empty after flush.
    
    Args:
        container_name: Name of the Redis Docker container
        
    Returns:
        True if Redis is empty, False otherwise
    """
    try:
        # Check total key count
        count_cmd = ["docker", "exec", container_name, "redis-cli", "DBSIZE"]
        result = subprocess.run(count_cmd, capture_output=True, text=True, check=True)
        
        key_count = int(result.stdout.strip())
        
        if key_count == 0:
            print(f"✅ Verified: Redis container '{container_name}' is empty (0 keys)")
            return True
        else:
            print(f"⚠️ Redis container '{container_name}' still contains {key_count} keys")
            
            # Show sample keys for debugging
            keys_cmd = ["docker", "exec", container_name, "redis-cli", "KEYS", "*"]
            keys_result = subprocess.run(keys_cmd, capture_output=True, text=True, check=True)
            
            if keys_result.stdout.strip():
                sample_keys = keys_result.stdout.strip().split('\n')[:5]
                print(f"   Sample remaining keys: {sample_keys}")
                if len(sample_keys) == 5:
                    print("   (and possibly more...)")
            
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to verify Redis state: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error verifying Redis: {e}")
        return False


def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Redis flush utility for test cleanup")
    parser.add_argument(
        "--container", 
        default="huleedu_redis", 
        help="Redis container name (default: huleedu_redis)"
    )
    parser.add_argument(
        "--verify", 
        action="store_true", 
        help="Verify Redis is empty after flush"
    )
    
    args = parser.parse_args()
    
    print(f"🗑️ Flushing Redis container: {args.container}")
    
    # Flush Redis
    if not flush_redis(args.container):
        sys.exit(1)
    
    # Verify if requested
    if args.verify:
        if not verify_redis_empty(args.container):
            sys.exit(1)
    
    print("✅ Redis cleanup completed successfully")


if __name__ == "__main__":
    main()