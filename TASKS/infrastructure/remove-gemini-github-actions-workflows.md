---
id: 'remove-gemini-github-actions-workflows'
title: 'Remove Gemini GitHub Actions workflows'
type: 'task'
status: 'done'
priority: 'medium'
domain: 'infrastructure'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-03'
last_updated: '2026-02-03'
related: []
labels: []
---
# Remove Gemini GitHub Actions workflows

## Objective

Remove all Gemini automation GitHub Actions workflows from this repository to eliminate LLM execution on untrusted public inputs and remove the need for Gemini-related CI secrets/variables.

## Context

This repository is public. The current Gemini workflows process untrusted issue/comment content and require Gemini API credentials, which is an unnecessary security and cost risk for a public repo.

## Plan

- Delete all `.github/workflows/gemini-*.yml` workflows.
- Remove any remaining references to the deleted workflows (if any).
- Validate TASKS structure after updates.

## Success Criteria

- No `gemini-*.yml` workflows remain under `.github/workflows/`.
- No workflows reference `run-gemini-cli` or `@gemini-cli`.

## Implementation Notes

Deleted workflows:

- `.github/workflows/gemini-dispatch.yml`
- `.github/workflows/gemini-review.yml`
- `.github/workflows/gemini-invoke.yml`
- `.github/workflows/gemini-triage.yml`
- `.github/workflows/gemini-scheduled-triage.yml`

## Related

- `.claude/archive/code-reviews/github-actions-gemini-pipelines_2026_02_03.md`
