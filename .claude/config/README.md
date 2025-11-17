# .claude/config/

Configuration files for Claude Code.

## Files

- **settings.local.json** - Machine-specific Claude Code settings (not committed to git)
  - Hooks configuration
  - Permissions (allow/deny lists for tools)
  - Status line settings

- **cloud-env-instructions.md** - Instructions for running Claude Code in cloud sandbox environments

## Usage

Settings in this directory are automatically loaded by Claude Code. The `settings.local.json` file takes precedence over project-level settings and should contain machine-specific or personal configurations.

For project-wide settings that should be committed, use `.claude/settings.json` in the project root (if needed).
