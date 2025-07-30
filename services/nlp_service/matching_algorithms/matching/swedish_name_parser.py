"""Swedish-aware name parsing utilities."""

from __future__ import annotations

import re

from huleedu_service_libs.logging_utils import create_service_logger

from ..models import NameComponents

logger = create_service_logger("nlp_service.matching.swedish_name_parser")


class SwedishNameParser:
    """Parse Swedish names handling special cases and compound names."""

    # Common Swedish name particles
    PARTICLES = {'av', 'af', 'von', 'de', 'van', 'der', 'den', 'la', 'el'}
    
    # Common compound name connectors
    COMPOUND_CONNECTORS = {'-', '–', '—'}  # Different dash types
    
    def parse_name(self, full_name: str) -> NameComponents:
        """Parse a full name into components with Swedish name awareness.
        
        Handles:
        - Simple names: "Johan Andersson"
        - Compound first names: "Anna-Karin Svensson"
        - Middle names: "Erik Johan Andersson" 
        - Particles: "Carl von Linné"
        - Multiple surnames: "Anna Andersson Nilsson"
        """
        # Clean and normalize
        full_name = self._normalize_name(full_name)
        
        if not full_name:
            return NameComponents(
                first_name="",
                last_name="",
                middle_names=[],
                full_name=""
            )
        
        # Split into words, preserving compound names
        words = self._split_preserving_compounds(full_name)
        
        if not words:
            return NameComponents(
                first_name="",
                last_name="",
                middle_names=[],
                full_name=full_name
            )
        
        # Single word - treat as first name
        if len(words) == 1:
            return NameComponents(
                first_name=words[0],
                last_name="",
                middle_names=[],
                full_name=full_name
            )
        
        # Two words - simple first and last
        if len(words) == 2:
            return NameComponents(
                first_name=words[0],
                last_name=words[1],
                middle_names=[],
                full_name=full_name
            )
        
        # Multiple words - need to determine structure
        return self._parse_complex_name(words, full_name)

    def _normalize_name(self, name: str) -> str:
        """Normalize name while preserving Swedish characters."""
        # Remove excessive whitespace
        name = ' '.join(name.split())
        
        # Normalize dashes to standard hyphen
        for dash in self.COMPOUND_CONNECTORS:
            if dash != '-':
                name = name.replace(dash, '-')
        
        return name.strip()

    def _split_preserving_compounds(self, name: str) -> list[str]:
        """Split name into words while preserving compound names."""
        # First, protect compound names by replacing spaces around hyphens
        protected = re.sub(r'\s*-\s*', '-', name)
        
        # Now split on spaces
        words = protected.split()
        
        # Filter out empty strings
        return [w for w in words if w]

    def _parse_complex_name(self, words: list[str], full_name: str) -> NameComponents:
        """Parse names with 3+ words."""
        # Check for particles (von, de, etc.)
        particle_indices = []
        for i, word in enumerate(words):
            if word.lower() in self.PARTICLES:
                particle_indices.append(i)
        
        # Common Swedish pattern: First Middle Last
        # But also: First Last Last (married + maiden name)
        
        # If we have particles, they usually precede surnames
        if particle_indices:
            # Find the earliest particle
            first_particle_idx = min(particle_indices)
            
            # Everything before the particle is given names
            given_names = words[:first_particle_idx]
            # Everything from particle onwards is surname
            surname_parts = words[first_particle_idx:]
            
            if given_names:
                first_name = given_names[0]
                middle_names = given_names[1:] if len(given_names) > 1 else []
                last_name = ' '.join(surname_parts)
            else:
                # Particle at the beginning? Unusual but handle it
                first_name = words[0]
                middle_names = []
                last_name = ' '.join(words[1:])
        else:
            # No particles - use heuristics
            
            # Check if last two words might be compound surname
            # (common in Sweden with married names)
            if len(words) >= 3 and self._looks_like_surname(words[-2]) and self._looks_like_surname(words[-1]):
                # Likely pattern: First [Middle...] Surname1 Surname2
                first_name = words[0]
                last_name = f"{words[-2]} {words[-1]}"
                middle_names = words[1:-2] if len(words) > 3 else []
            else:
                # Standard pattern: First [Middle...] Last
                first_name = words[0]
                last_name = words[-1]
                middle_names = words[1:-1] if len(words) > 2 else []
        
        return NameComponents(
            first_name=first_name,
            last_name=last_name,
            middle_names=middle_names,
            full_name=full_name
        )

    def _looks_like_surname(self, word: str) -> bool:
        """Check if a word looks like a Swedish surname."""
        # Common Swedish surname endings
        surname_endings = ['son', 'sson', 'dotter', 'ström', 'berg', 
                          'qvist', 'kvist', 'lund', 'gren', 'dahl', 'dal']
        
        word_lower = word.lower()
        for ending in surname_endings:
            if word_lower.endswith(ending):
                return True
        
        # Also check if it starts with capital (all surnames do)
        return word and word[0].isupper()

    def get_match_variations(self, name_components: NameComponents) -> list[str]:
        """Get various name combinations for matching.
        
        Returns different combinations that might be used:
        - Full name
        - First + Last
        - First only (if unique enough)
        - Last, First (reversed format)
        """
        variations = [name_components.full_name]
        
        if name_components.first_name and name_components.last_name:
            # Standard format
            variations.append(f"{name_components.first_name} {name_components.last_name}")
            
            # Reversed format
            variations.append(f"{name_components.last_name}, {name_components.first_name}")
            
            # With middle initials if present
            if name_components.middle_names:
                initials = ' '.join(name[0] + '.' for name in name_components.middle_names if name)
                variations.append(f"{name_components.first_name} {initials} {name_components.last_name}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_variations = []
        for v in variations:
            if v.lower() not in seen:
                seen.add(v.lower())
                unique_variations.append(v)
        
        return unique_variations