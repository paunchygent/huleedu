#!/usr/bin/env python3
"""Debug script to test BatchConfigOverrides instantiation."""

import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.getcwd())

from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides

def test_batch_config_instantiation():
    """Test different ways of creating BatchConfigOverrides."""
    
    print("Testing BatchConfigOverrides instantiation...")
    
    # Test 1: Empty instantiation
    try:
        config1 = BatchConfigOverrides()
        print(f"✓ Empty instantiation successful: {config1}")
    except Exception as e:
        print(f"✗ Empty instantiation failed: {e}")
    
    # Test 2: Single field instantiation 
    try:
        config2 = BatchConfigOverrides(batch_size=100)
        print(f"✓ Single field instantiation successful: {config2}")
    except Exception as e:
        print(f"✗ Single field instantiation failed: {e}")
    
    # Test 3: All fields
    try:
        config3 = BatchConfigOverrides(
            batch_size=75,
            max_concurrent_batches=3,
            partial_completion_threshold=0.8
        )
        print(f"✓ All fields instantiation successful: {config3}")
    except Exception as e:
        print(f"✗ All fields instantiation failed: {e}")

    # Test 4: Invalid values to test validation
    try:
        config4 = BatchConfigOverrides(batch_size=5)  # Should fail validation
        print(f"✗ Invalid batch size validation failed - should have raised error: {config4}")
    except Exception as e:
        print(f"✓ Invalid batch size correctly rejected: {e}")

if __name__ == "__main__":
    test_batch_config_instantiation()