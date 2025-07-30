"""Pattern-based extractor for common header formats."""

from __future__ import annotations

import re
from typing import Any

from ..models import ExtractedIdentifier, ExtractionResult
from .base_extractor import BaseExtractor


class HeaderExtractor(BaseExtractor):
    """Extract student information from common header patterns.
    
    Looks for patterns like:
    - Name: John Smith
    - Student: Anna-Karin Andersson
    - By: Erik Johansson
    - Namn: Lars Svensson (Swedish)
    """

    def __init__(self, header_patterns: list[str] | None = None):
        """Initialize with configurable header patterns.
        
        Args:
            header_patterns: List of regex patterns. If None, uses defaults.
        """
        super().__init__("header")
        
        # Default patterns if none provided
        if header_patterns is None:
            header_patterns = [
                r"Name:\s*(.+)",
                r"Student:\s*(.+)",
                r"Author:\s*(.+)",
                r"By:\s*(.+)",
                r"Submitted by:\s*(.+)",
                r"Written by:\s*(.+)",
                r"Namn:\s*(.+)",  # Swedish
                r"Elev:\s*(.+)",  # Swedish for "Student"
                r"Författare:\s*(.+)",  # Swedish for "Author"
            ]
        
        # Compile patterns with case-insensitive flag
        self.patterns = [re.compile(pattern, re.IGNORECASE) for pattern in header_patterns]
        
        # Email pattern for additional extraction
        self.email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )

    async def extract(
        self,
        text: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExtractionResult:
        """Extract using header patterns."""
        result = ExtractionResult()
        
        # Split into lines for pattern matching
        lines = text.split('\n')
        
        # Track which patterns we've matched to avoid duplicates
        matched_values = set()
        
        # Search first 20 lines for headers (most headers are at the top)
        search_lines = lines[:20]
        
        for i, line in enumerate(search_lines):
            line = line.strip()
            if not line:
                continue
            
            # Try each pattern
            for pattern in self.patterns:
                match = pattern.match(line)
                if match:
                    extracted_value = match.group(1).strip()
                    
                    # Skip empty or very short extractions
                    if not extracted_value or len(extracted_value) < 3:
                        continue
                    
                    # Check if it's an email
                    if self.email_pattern.match(extracted_value):
                        if extracted_value.lower() not in matched_values:
                            result.possible_emails.append(
                                ExtractedIdentifier(
                                    value=extracted_value.lower(),
                                    source_strategy=self.name,
                                    confidence=0.9,
                                    location_hint=f"line_{i+1}_header"
                                )
                            )
                            matched_values.add(extracted_value.lower())
                            self.logger.debug(f"Extracted email from header: {extracted_value}")
                    else:
                        # It's likely a name
                        if self._looks_like_name(extracted_value) and extracted_value not in matched_values:
                            result.possible_names.append(
                                ExtractedIdentifier(
                                    value=extracted_value,
                                    source_strategy=self.name,
                                    confidence=0.85,  # High confidence for explicit headers
                                    location_hint=f"line_{i+1}_header"
                                )
                            )
                            matched_values.add(extracted_value)
                            self.logger.debug(f"Extracted name from header: {extracted_value}")
                    
                    # Don't break - same line might match multiple patterns
        
        # Also look for emails anywhere in the header area
        header_text = '\n'.join(search_lines)
        all_emails = self.email_pattern.findall(header_text)
        
        for email in all_emails:
            if email.lower() not in matched_values:
                result.possible_emails.append(
                    ExtractedIdentifier(
                        value=email.lower(),
                        source_strategy=self.name,
                        confidence=0.85,
                        location_hint="header_area"
                    )
                )
                matched_values.add(email.lower())
        
        # Set metadata
        result.metadata["patterns_checked"] = len(self.patterns)
        result.metadata["matches_found"] = len(result.possible_names) + len(result.possible_emails)
        
        return result

    def _looks_like_name(self, text: str) -> bool:
        """Check if extracted text looks like a name."""
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        # Skip if too long or too short
        if len(text) < 3 or len(text) > 60:
            return False
        
        # Skip if it contains obvious non-name content
        non_name_indicators = [
            '@', 'http', 'www', '.com', '.se',
            '?', '!', '(', ')', '[', ']',
            '\t', '\r', '\\', '/', '|'
        ]
        
        text_lower = text.lower()
        for indicator in non_name_indicators:
            if indicator in text_lower:
                return False
        
        # Should have at least one space (except for single names)
        # But not be a full sentence
        word_count = len(text.split())
        if word_count > 6:  # Probably not a name if more than 6 words
            return False
        
        # At least one word should start with a capital
        words = text.split()
        has_capital = any(word and word[0].isupper() for word in words 
                         if not word.lower() in ['av', 'von', 'de', 'van', 'der', 'la', 'el'])
        
        return has_capital