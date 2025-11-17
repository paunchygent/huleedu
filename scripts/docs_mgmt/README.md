# Documentation Management Scripts

## validate_docs_structure.py

Validates documentation structure compliance with `documentation/DOCS_STRUCTURE_SPEC.md`.

### Usage

```bash
# Validate with default root (documentation/)
python scripts/docs_mgmt/validate_docs_structure.py

# Validate with custom root
python scripts/docs_mgmt/validate_docs_structure.py --root /path/to/docs

# Show all validated files
python scripts/docs_mgmt/validate_docs_structure.py --verbose

# Treat warnings as errors
python scripts/docs_mgmt/validate_docs_structure.py --strict
```

### What it validates

1. **Top-level directory taxonomy (§3)**: Only allowed directories exist under `documentation/`
2. **File naming (§4)**: Files use `.md` extension and kebab-case or SCREAMING_SNAKE_CASE
3. **Directory naming (§4)**: Directories use kebab-case or lower_snake_case
4. **No spaces (§4)**: No spaces in any file or directory names
5. **Runbook frontmatter (§5)**: Files in `operations/` have proper frontmatter (warnings)
6. **Decision frontmatter (§6)**: Files in `decisions/` have proper frontmatter and naming (warnings)

### Exit codes

- `0`: Validation passed (warnings ok unless --strict)
- `1`: Validation failed (errors found, or warnings in --strict mode)
- `2`: Usage error (invalid arguments, missing root directory)

### Examples

```bash
# Check for errors only
python scripts/docs_mgmt/validate_docs_structure.py

# Check everything including warnings
python scripts/docs_mgmt/validate_docs_structure.py --verbose

# Enforce warnings as errors in CI
python scripts/docs_mgmt/validate_docs_structure.py --strict
```
