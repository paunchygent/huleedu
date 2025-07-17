from __future__ import annotations

from common_core.metadata_models import ParsedNameMetadata, PersonNameV1

from services.class_management_service.api_models import StudentParsingResult


def parse_student_name(full_name: str) -> StudentParsingResult:
    """
    Parse full name into PersonNameV1-compatible components.
    Handles Swedish/English naming patterns:
    - "Anna Andersson" → first_name="Anna", last_name="Andersson", confidence=0.9
    - "Erik Johan Svensson" → first_name="Erik Johan", last_name="Svensson", confidence=0.8
    - Single names treated as last_name with lower confidence
    """
    parts = full_name.strip().split()
    num_parts = len(parts)

    if num_parts == 0:
        return StudentParsingResult(
            parsed_name=ParsedNameMetadata(
                parsed_name=PersonNameV1(first_name="", last_name="", legal_full_name="")
            ),
            confidence=0.0,
        )
    elif num_parts == 1:
        # Treat single names as last names with lower confidence
        return StudentParsingResult(
            parsed_name=ParsedNameMetadata(
                parsed_name=PersonNameV1(first_name="", last_name=parts[0])
            ),
            confidence=0.5,  # Lower confidence for single name
        )
    else:
        # Assume last part is last name, rest is first name
        first_name = " ".join(parts[:-1])
        last_name = parts[-1]
        return StudentParsingResult(
            parsed_name=ParsedNameMetadata(
                parsed_name=PersonNameV1(first_name=first_name, last_name=last_name)
            ),
            confidence=0.9,  # Higher confidence for multiple parts
        )
