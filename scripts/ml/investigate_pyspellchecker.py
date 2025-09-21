#!/usr/bin/env python3
"""Investigate PySpellChecker's dictionary and configuration."""

import os

from spellchecker import SpellChecker

# Create default spellchecker
spell = SpellChecker()

print("=== PySpellChecker Investigation ===\n")

# Check what language/dictionary is being used
print(f"Distance algorithm: {spell.distance}")
try:
    print(f"Dictionary size: {len(spell.word_frequency.dictionary)} words")
except:
    print(f"Dictionary size: {len(spell)} words")

# Check where the dictionary comes from
print("\n=== Dictionary Source ===")
# PySpellChecker uses word frequency lists
print("PySpellChecker uses word frequency lists from:")
print("- Default: English word frequency from Peter Norvig's work")
print("- Based on: Google Web Trillion Word Corpus")

# Sample what's in the dictionary
print("\n=== Sample Dictionary Contents ===")
try:
    sample_words = list(spell.word_frequency.dictionary.keys())[:20]
    print(f"First 20 words: {sample_words}")
except:
    print("Cannot access dictionary directly")

# Check frequency of some common words
test_words = ["the", "microsoft", "uk", "usa", "cvs", "cv", "covid", "phd", "ai", "email"]
print("\n=== Word Frequencies ===")
for word in test_words:
    if word.lower() in spell:
        print(f"'{word}': KNOWN")
    else:
        print(f"'{word}': NOT IN DICTIONARY")

# Check what happens with unknown words
print("\n=== Unknown Word Handling ===")
unknown = ["UK", "USA", "CVs", "COVID", "AI", "PhD"]
for word in unknown:
    candidates = spell.candidates(word)
    print(f"'{word}' -> candidates: {candidates}")

# Check if we can add words
print("\n=== Can We Add Words? ===")
spell.word_frequency.load_words(["UK", "USA", "COVID", "CVs"])
print("Added: UK, USA, COVID, CVs")
print(f"'UK' now known? {'uk' in spell}")
print(f"'USA' now known? {'usa' in spell}")
print(f"'COVID' now known? {'covid' in spell}")
print(f"'CVs' now known? {'cvs' in spell}")

# Check dictionary file location
print("\n=== Dictionary Files ===")
import inspect

import spellchecker

module_path = os.path.dirname(inspect.getfile(spellchecker))
print(f"Module path: {module_path}")

# List available dictionaries
resources_path = os.path.join(module_path, "resources")
if os.path.exists(resources_path):
    print(f"Available dictionaries in {resources_path}:")
    for file in os.listdir(resources_path):
        if file.endswith(".json.gz"):
            print(f"  - {file}")
