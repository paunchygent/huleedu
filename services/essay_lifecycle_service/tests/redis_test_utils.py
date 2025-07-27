"""
Redis test utilities for Essay Lifecycle Service.

Provides mock implementations of Redis components that properly simulate
Redis pipeline behavior for testing.
"""

from __future__ import annotations

from typing import Any


class MockRedisPipeline:
    """Mock Redis pipeline implementation for testing.
    
    This class simulates Redis pipeline behavior with:
    - Synchronous command methods that return self for chaining
    - An async execute() method that returns results
    - Operation tracking for test assertions
    
    All command methods (multi, sadd, hset, etc.) are synchronous and return
    self to allow method chaining, matching the actual Redis pipeline interface.
    Only execute() is async.
    
    Attributes:
        operations: List of tuples tracking (method_name, args, kwargs) for each operation
        results: List of results to return from execute() calls
        result_index: Current index in results list for sequential execute() calls
    """
    
    def __init__(self, results: list[Any] | None = None) -> None:
        """Initialize mock Redis pipeline.
        
        Args:
            results: Optional list of results to return from execute() calls.
                    If not provided, defaults to returning True for each operation.
        """
        self.operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.results = results or []
        self.result_index = 0
        
    def multi(self) -> MockRedisPipeline:
        """Start a transaction block.
        
        Returns:
            Self for method chaining
        """
        self.operations.append(("multi", (), {}))
        return self
        
    def sadd(self, key: str, *values: Any) -> MockRedisPipeline:
        """Add members to a set.
        
        Args:
            key: The set key
            *values: Values to add to the set
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("sadd", (key,) + values, {}))
        return self
        
    def hset(self, key: str, field: str | None = None, value: Any = None, 
             mapping: dict[str, Any] | None = None) -> MockRedisPipeline:
        """Set hash field values.
        
        Args:
            key: The hash key
            field: Optional field name (if setting single field)
            value: Optional field value (if setting single field)
            mapping: Optional dict of field:value pairs to set
            
        Returns:
            Self for method chaining
        """
        args: tuple[str | Any, ...] = (key,)
        kwargs = {}
        if field is not None and value is not None:
            args = args + (field, value)
        if mapping is not None:
            kwargs["mapping"] = mapping
        self.operations.append(("hset", args, kwargs))
        return self
        
    def setex(self, key: str, seconds: int, value: Any) -> MockRedisPipeline:
        """Set key with expiration.
        
        Args:
            key: The key to set
            seconds: TTL in seconds
            value: The value to set
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("setex", (key, seconds, value), {}))
        return self
        
    def rpush(self, key: str, *values: Any) -> MockRedisPipeline:
        """Push values to the end of a list.
        
        Args:
            key: The list key
            *values: Values to push
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("rpush", (key,) + values, {}))
        return self
        
    def spop(self, key: str, count: int | None = None) -> MockRedisPipeline:
        """Remove and return random members from a set.
        
        Args:
            key: The set key
            count: Optional number of members to pop
            
        Returns:
            Self for method chaining
        """
        args: tuple[str | int, ...] = (key,)
        if count is not None:
            args = args + (count,)
        self.operations.append(("spop", args, {}))
        return self
        
    def delete(self, *keys: str) -> MockRedisPipeline:
        """Delete one or more keys.
        
        Args:
            *keys: Keys to delete
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("delete", keys, {}))
        return self
        
    def expire(self, key: str, seconds: int) -> MockRedisPipeline:
        """Set key expiration.
        
        Args:
            key: The key to expire
            seconds: TTL in seconds
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("expire", (key, seconds), {}))
        return self
        
    def set(self, key: str, value: Any) -> MockRedisPipeline:
        """Set a key value.
        
        Args:
            key: The key to set
            value: The value to set
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("set", (key, value), {}))
        return self
        
    def scard(self, key: str) -> MockRedisPipeline:
        """Get the cardinality (number of members) of a set.
        
        Args:
            key: The set key
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("scard", (key,), {}))
        return self
        
    def hget(self, key: str, field: str) -> MockRedisPipeline:
        """Get a hash field value.
        
        Args:
            key: The hash key
            field: The field to get
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("hget", (key, field), {}))
        return self
        
    def exists(self, key: str) -> MockRedisPipeline:
        """Check if a key exists.
        
        Args:
            key: The key to check
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("exists", (key,), {}))
        return self
        
    def llen(self, key: str) -> MockRedisPipeline:
        """Get the length of a list.
        
        Args:
            key: The list key
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("llen", (key,), {}))
        return self
        
    def lrange(self, key: str, start: int, stop: int) -> MockRedisPipeline:
        """Get a range of elements from a list.
        
        Args:
            key: The list key
            start: Start index
            stop: Stop index (-1 for end of list)
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("lrange", (key, start, stop), {}))
        return self
        
    def hlen(self, key: str) -> MockRedisPipeline:
        """Get the number of fields in a hash.
        
        Args:
            key: The hash key
            
        Returns:
            Self for method chaining
        """
        self.operations.append(("hlen", (key,), {}))
        return self
        
    async def execute(self) -> list[Any]:
        """Execute all queued commands in the pipeline.
        
        Returns:
            List of results for each operation. If results were provided
            at initialization, returns those. Otherwise returns True for
            each operation.
            
        Raises:
            IndexError: If more execute() calls are made than results provided
        """
        num_operations = len(self.operations)
        
        if self.results:
            # Use provided results
            if self.result_index >= len(self.results):
                raise IndexError(f"No more results available. Index {self.result_index} >= {len(self.results)}")
            result = self.results[self.result_index]
            self.result_index += 1
            # Ensure we return a list as declared in the return type
            if isinstance(result, list):
                return result
            else:
                # If a single result was provided, wrap it in a list
                return [result]
        else:
            # Default: return True for each operation
            return [True] * num_operations
            
    def reset(self) -> None:
        """Reset the pipeline state.
        
        Clears tracked operations and resets result index.
        """
        self.operations.clear()
        self.result_index = 0