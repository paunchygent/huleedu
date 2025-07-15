#!/usr/bin/env python3
"""Debug script to test mypy behavior with BatchConfigOverrides."""

from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides

def test_instantiation() -> None:
    """Test different ways of creating BatchConfigOverrides."""
    
    # Test 1: Empty instantiation (should work since all fields are optional)
    config1 = BatchConfigOverrides()
    
    # Test 2: Single field instantiation (should work)
    config2 = BatchConfigOverrides(batch_size=100)
    
    # Test 3: All fields (should work)
    config3 = BatchConfigOverrides(
        batch_size=75,
        max_concurrent_batches=3,
        partial_completion_threshold=0.8
    )
    
    print(f"Created configs: {config1}, {config2}, {config3}")

if __name__ == "__main__":
    test_instantiation()