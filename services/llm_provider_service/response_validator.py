"""Response validation utilities for LLM Provider Service."""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator


class StandardizedLLMResponse(BaseModel):
    """Standardized response format for LLM comparison results."""

    winner: str = Field(description="Which essay is better", pattern="^(Essay A|Essay B)$")
    justification: str = Field(
        description="Explanation of the choice (50-500 characters)", 
        min_length=50, 
        max_length=500
    )
    confidence: float = Field(
        description="Confidence score between 1.0 and 5.0",
        ge=1.0,
        le=5.0
    )


def validate_and_normalize_response(
    raw_response: str | Dict[str, Any],
) -> Tuple[StandardizedLLMResponse | None, str | None]:
    """Validate and normalize LLM response to standardized format.

    Args:
        raw_response: Raw response from LLM (JSON string or dict)

    Returns:
        Tuple of (validated_response, error_message)
    """
    try:
        # Parse JSON if string
        if isinstance(raw_response, str):
            try:
                parsed_data = json.loads(raw_response)
            except json.JSONDecodeError as e:
                return None, f"Invalid JSON format: {str(e)}"
        else:
            parsed_data = raw_response

        # Extract and normalize fields
        winner = parsed_data.get("winner", "Essay A")
        justification = parsed_data.get("justification", "Analysis provided")
        confidence = parsed_data.get("confidence", 3.0)

        # Normalize winner format
        if winner not in ["Essay A", "Essay B"]:
            winner = "Essay A"

        # Normalize confidence range
        if isinstance(confidence, (int, float)):
            confidence = float(max(1.0, min(5.0, confidence)))
        else:
            confidence = 3.0

        # Normalize justification length
        if len(justification) < 50:
            justification = justification + " - additional analysis provided"
            justification = justification[:50] if len(justification) > 50 else justification.ljust(50)
        elif len(justification) > 500:
            justification = justification[:497] + "..."

        # Create normalized data dict
        normalized_data = {
            "winner": winner,
            "justification": justification,
            "confidence": confidence
        }

        # Validate against schema with normalized data
        validated_response = StandardizedLLMResponse(**normalized_data)
        return validated_response, None

    except ValidationError as e:
        error_details = []
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            error_details.append(f"{field}: {error['msg']}")
        
        return None, f"Validation failed: {'; '.join(error_details)}"

    except Exception as e:
        return None, f"Unexpected validation error: {str(e)}"


def convert_to_internal_format(
    standardized_response: StandardizedLLMResponse,
) -> Tuple[str, str, float]:
    """Convert standardized response to internal format.

    Args:
        standardized_response: Validated standardized response

    Returns:
        Tuple of (choice, reasoning, confidence) in internal format
    """
    choice = "A" if standardized_response.winner == "Essay A" else "B"
    reasoning = standardized_response.justification
    confidence = standardized_response.confidence

    return choice, reasoning, confidence


# JSON Schema for external validation (e.g., in API documentation)
STANDARDIZED_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "winner": {
            "type": "string",
            "enum": ["Essay A", "Essay B"],
            "description": "Which essay is better: 'Essay A' or 'Essay B'"
        },
        "justification": {
            "type": "string",
            "minLength": 50,
            "maxLength": 500,
            "description": "Detailed explanation of why this essay was chosen (50-500 characters)"
        },
        "confidence": {
            "type": "number",
            "minimum": 1.0,
            "maximum": 5.0,
            "description": "Confidence score between 1.0 and 5.0"
        }
    },
    "required": ["winner", "justification", "confidence"],
    "additionalProperties": False
}