#!/usr/bin/env python3
"""
Clear Kafka topics for HuleEdu platform.

This script deletes and recreates Kafka topics to clear all messages.
Useful for test environments when old messages cause idempotency issues.
"""

import subprocess
import sys
import time
from typing import List

# All HuleEdu Kafka topics
HULEEDU_TOPICS = [
    "huleedu.batch.essays.registered.v1",
    "huleedu.file.essay.content.provisioned.v1",
    "huleedu.file.essay.validation.failed.v1",
    "huleedu.els.batch.essays.ready.v1",
    "huleedu.commands.batch.pipeline.v1",
    "huleedu.batch.spellcheck.initiate.command.v1",
    "huleedu.essay.spellcheck.requested.v1",
    "huleedu.essay.spellcheck.completed.v1",
    "huleedu.els.batch.phase.outcome.v1",
    "huleedu.batch.cj_assessment.initiate.command.v1",
    "huleedu.cj_assessment.completed.v1",
    "huleedu.batch.nlp.initiate.command.v1",
    "huleedu.batch.ai_feedback.initiate.command.v1",
    "huleedu.file.batch.file.added.v1",
    "huleedu.file.batch.file.removed.v1",
    "huleedu.class.created.v1",
    "huleedu.class.updated.v1",
    "huleedu.class.deleted.v1",
    "huleedu.class.essay.association.updated.v1",
]


def run_kafka_command(command: List[str]) -> tuple[bool, str]:
    """Run a Kafka command in the Docker container."""
    full_command = ["docker", "exec", "huleedu_kafka"] + command
    try:
        result = subprocess.run(full_command, capture_output=True, text=True, check=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr


def delete_topic(topic: str) -> bool:
    """Delete a single Kafka topic."""
    print(f"Deleting topic: {topic}")
    success, output = run_kafka_command(
        ["kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--delete", "--topic", topic]
    )
    if success:
        print("  ✓ Deleted successfully")
    else:
        print(f"  ✗ Failed to delete: {output}")
    return success


def create_topic(topic: str, partitions: int = 3, replication_factor: int = 1) -> bool:
    """Create a single Kafka topic."""
    print(f"Creating topic: {topic}")
    success, output = run_kafka_command(
        [
            "kafka-topics.sh",
            "--bootstrap-server",
            "localhost:9092",
            "--create",
            "--topic",
            topic,
            "--partitions",
            str(partitions),
            "--replication-factor",
            str(replication_factor),
            "--if-not-exists",
        ]
    )
    if success:
        print("  ✓ Created successfully")
    else:
        print(f"  ✗ Failed to create: {output}")
    return success


def main():
    """Main function to clear and recreate all topics."""
    print("🧹 Clearing Kafka topics for HuleEdu platform")
    print("=" * 60)

    # Check if Kafka is running
    success, output = run_kafka_command(
        ["kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--list"]
    )

    if not success:
        print("❌ Error: Cannot connect to Kafka. Is the container running?")
        sys.exit(1)

    existing_topics = output.strip().split("\n") if output.strip() else []
    print(f"Found {len(existing_topics)} existing topics")

    # Delete existing HuleEdu topics
    print("\n🗑️  Deleting topics...")
    deleted_count = 0
    for topic in HULEEDU_TOPICS:
        if topic in existing_topics:
            if delete_topic(topic):
                deleted_count += 1

    print(f"\nDeleted {deleted_count} topics")

    # Wait a moment for deletions to propagate
    print("\n⏳ Waiting for deletions to propagate...")
    time.sleep(2)

    # Recreate topics
    print("\n🔨 Creating topics...")
    created_count = 0
    for topic in HULEEDU_TOPICS:
        if create_topic(topic):
            created_count += 1

    print(f"\n✅ Created {created_count} topics")
    print("\n🎉 Kafka topics cleared successfully!")

    # Verify final state
    print("\n📋 Final topic list:")
    success, output = run_kafka_command(
        ["kafka-topics.sh", "--bootstrap-server", "localhost:9092", "--list"]
    )
    if success:
        topics = sorted([t for t in output.strip().split("\n") if t.startswith("huleedu.")])
        for topic in topics:
            print(f"  - {topic}")


if __name__ == "__main__":
    main()
