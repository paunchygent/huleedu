"""Protocol validation utilities for LLM Provider Service."""

import inspect
from typing import Any, get_type_hints

from services.llm_provider_service.protocols import (
    LLMOrchestratorProtocol,
    LLMProviderProtocol,
    QueueManagerProtocol,
)


def validate_protocol_compliance(implementation: Any, protocol_class: type) -> bool:
    """Validate that an implementation complies with protocol signatures.

    Args:
        implementation: The implementation instance to validate
        protocol_class: The protocol class to validate against

    Returns:
        True if implementation matches protocol signatures

    Raises:
        ValueError: If implementation doesn't match protocol
    """
    protocol_methods = [
        name for name, method in inspect.getmembers(protocol_class, inspect.isfunction)
        if not name.startswith('_')
    ]

    for method_name in protocol_methods:
        if not hasattr(implementation, method_name):
            raise ValueError(f"Implementation missing method: {method_name}")

        impl_method = getattr(implementation, method_name)
        protocol_method = getattr(protocol_class, method_name)

        # Get signature for comparison
        impl_sig = inspect.signature(impl_method)
        protocol_sig = inspect.signature(protocol_method)

        if impl_sig != protocol_sig:
            raise ValueError(
                f"Method signature mismatch for {method_name}:\n"
                f"Protocol: {protocol_sig}\n"
                f"Implementation: {impl_sig}"
            )

    return True


def validate_no_tuple_returns(protocol_class: type) -> bool:
    """Validate that protocol methods don't return tuples.

    Args:
        protocol_class: The protocol class to validate

    Returns:
        True if no tuple returns found

    Raises:
        ValueError: If tuple returns are found
    """
    protocol_methods = [
        name for name, method in inspect.getmembers(protocol_class, inspect.isfunction)
        if not name.startswith('_')
    ]

    for method_name in protocol_methods:
        method = getattr(protocol_class, method_name)
        type_hints = get_type_hints(method)

        if 'return' in type_hints:
            return_type = type_hints['return']
            return_type_str = str(return_type)

            if 'Tuple' in return_type_str or 'tuple' in return_type_str:
                raise ValueError(
                    f"Method {method_name} still has tuple return type: {return_type}"
                )

    return True


def validate_correlation_id_parameters(protocol_class: type) -> bool:
    """Validate that protocol methods include correlation_id parameters where expected.

    Args:
        protocol_class: The protocol class to validate

    Returns:
        True if correlation_id parameters are properly included

    Raises:
        ValueError: If correlation_id is missing from methods that should have it
    """
    # Methods that should have correlation_id parameter
    methods_requiring_correlation_id = {
        'generate_comparison',
        'perform_comparison',
        'test_provider'
    }

    protocol_methods = [
        name for name, method in inspect.getmembers(protocol_class, inspect.isfunction)
        if not name.startswith('_')
    ]

    for method_name in protocol_methods:
        if method_name in methods_requiring_correlation_id:
            method = getattr(protocol_class, method_name)
            sig = inspect.signature(method)

            if 'correlation_id' not in sig.parameters:
                raise ValueError(
                    f"Method {method_name} missing required correlation_id parameter"
                )

    return True


def validate_all_protocols() -> bool:
    """Validate all LLM Provider Service protocols for compliance.

    Returns:
        True if all protocols pass validation

    Raises:
        ValueError: If any protocol validation fails
    """
    protocols_to_validate = [
        LLMProviderProtocol,
        LLMOrchestratorProtocol,
        QueueManagerProtocol,
    ]

    for protocol in protocols_to_validate:
        validate_no_tuple_returns(protocol)
        validate_correlation_id_parameters(protocol)

    return True
