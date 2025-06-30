#!/usr/bin/env python3
"""
Script to check the state of a batch in the ELS database.
Usage: python scripts/check_batch_state.py <batch_id>
"""

import asyncio
import os
import sys
from datetime import datetime

import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


async def check_batch_state(batch_id: str):
    """Check the state of essays in a batch."""
    # Get database connection parameters
    db_host = os.getenv("HULEEDU_DB_HOST", "localhost")
    db_port = os.getenv("HULEEDU_DB_PORT", "5433")  # ELS DB port
    db_user = os.getenv("HULEEDU_DB_USER", "huleedu_user")
    db_password = os.getenv("HULEEDU_DB_PASSWORD", "REDACTED_DEFAULT_PASSWORD")
    db_name = "essay_lifecycle"

    # Connect to the database
    conn = await asyncpg.connect(
        host=db_host,
        port=int(db_port),
        user=db_user,
        password=db_password,
        database=db_name,
    )

    try:
        # Check batch tracker
        batch_tracker = await conn.fetchrow(
            "SELECT * FROM batch_essay_trackers WHERE batch_id = $1", batch_id
        )
        
        if batch_tracker:
            print(f"\n=== Batch Tracker for {batch_id} ===")
            print(f"Total slots: {batch_tracker['total_slots']}")
            print(f"Assigned slots: {batch_tracker['assigned_slots']}")
            print(f"Is ready: {batch_tracker['is_ready']}")
            print(f"Created at: {batch_tracker['created_at']}")
            print(f"Updated at: {batch_tracker['updated_at']}")
            if batch_tracker['batch_metadata']:
                print(f"Metadata: {batch_tracker['batch_metadata']}")
        else:
            print(f"\nNo batch tracker found for batch_id: {batch_id}")

        # Check essay states
        essays = await conn.fetch(
            """
            SELECT essay_id, current_status, processing_metadata, 
                   timeline, storage_references, version, created_at, updated_at
            FROM essay_states 
            WHERE batch_id = $1
            ORDER BY essay_id
            """,
            batch_id,
        )

        print(f"\n=== Essay States (Found {len(essays)} essays) ===")
        
        # Count by status
        status_counts = {}
        for essay in essays:
            status = essay['current_status']
            status_counts[status] = status_counts.get(status, 0) + 1
        
        print("\nStatus Summary:")
        for status, count in sorted(status_counts.items()):
            print(f"  {status}: {count}")

        # Show details for each essay
        print("\nDetailed Essay Status:")
        
        # Separate essays by status for analysis
        stuck_essays = [e for e in essays if e['current_status'] == 'spellchecking_in_progress']
        completed_essays = [e for e in essays if e['current_status'] == 'spellchecked_success']
        failed_essays = [e for e in essays if e['current_status'] == 'spellcheck_failed']
        
        if stuck_essays:
            print("\n--- STUCK ESSAYS (spellchecking_in_progress) ---")
            for essay in stuck_essays[:3]:  # Show first 3 stuck essays
                print(f"\nEssay ID: {essay['essay_id']}")
                print(f"  Status: {essay['current_status']}")
                print(f"  Version: {essay['version']}")
                print(f"  Timeline: {essay['timeline']}")
                metadata = essay['processing_metadata']
                print(f"  Current phase: {metadata.get('current_phase', 'NOT SET')}")
                print(f"  Commanded phases: {metadata.get('commanded_phases', 'NOT SET')}")
                print(f"  Dispatch completed: {metadata.get('dispatch_completed', 'NOT SET')}")
                print(f"  Spellcheck phase: {metadata.get('spellcheck_phase', 'NOT SET')}")
        
        if completed_essays:
            print("\n--- COMPLETED ESSAYS (spellchecked_success) ---")
            essay = completed_essays[0]  # Show first completed essay
            print(f"\nEssay ID: {essay['essay_id']}")
            print(f"  Status: {essay['current_status']}")
            print(f"  Version: {essay['version']}")
            print(f"  Timeline: {essay['timeline']}")
            metadata = essay['processing_metadata']
            print(f"  Current phase: {metadata.get('current_phase', 'NOT SET')}")
            print(f"  Commanded phases: {metadata.get('commanded_phases', 'NOT SET')}")
            print(f"  Spellcheck result: {metadata.get('spellcheck_result', 'NOT SET')}")
            print(f"  Phase outcome status: {metadata.get('phase_outcome_status', 'NOT SET')}")

        # Check which essays IDs are stuck
        stuck_essay_ids = [e['essay_id'] for e in stuck_essays]
        if stuck_essay_ids:
            print(f"\n--- CHECKING EVENTS FOR STUCK ESSAYS ---")
            print(f"Stuck essay IDs: {stuck_essay_ids[:5]}...")  # Show first 5
        
        # Check recent processing logs
        logs = await conn.fetch(
            """
            SELECT event_type, previous_status, new_status, 
                   event_metadata, correlation_id, created_at, essay_id
            FROM essay_processing_logs
            WHERE batch_id = $1
            ORDER BY created_at DESC
            LIMIT 50
            """,
            batch_id,
        )

        print(f"\n=== Recent Processing Logs (Last 50) ===")
        
        # Look for events for stuck essays
        stuck_events = []
        for log in logs:
            if log.get('essay_id') in stuck_essay_ids:
                stuck_events.append(log)
        
        if stuck_events:
            print(f"\n--- EVENTS FOR STUCK ESSAYS ---")
            for log in stuck_events[:10]:  # Show first 10
                print(f"\n{log['created_at']}: {log['event_type']} (Essay: {log.get('essay_id', 'N/A')})")
                print(f"  {log['previous_status']} -> {log['new_status']}")
        
        # Show general event summary
        print(f"\n--- EVENT SUMMARY ---")
        event_counts = {}
        for log in logs:
            event_type = log['event_type']
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        for event_type, count in sorted(event_counts.items()):
            print(f"  {event_type}: {count}")

    finally:
        await conn.close()


async def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/check_batch_state.py <batch_id>")
        sys.exit(1)
    
    batch_id = sys.argv[1]
    await check_batch_state(batch_id)


if __name__ == "__main__":
    asyncio.run(main())