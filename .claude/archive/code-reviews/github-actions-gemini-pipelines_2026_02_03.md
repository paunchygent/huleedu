# GitHub Actions: Google Gemini pipelines (2026-02-03)

## Scope

Assess the Google Gemini automation workflows under `.github/workflows/`:

- `.github/workflows/gemini-dispatch.yml`
- `.github/workflows/gemini-review.yml`
- `.github/workflows/gemini-invoke.yml`
- `.github/workflows/gemini-triage.yml`
- `.github/workflows/gemini-scheduled-triage.yml`

Primary focus: security posture (secrets, permissions, prompt-injection surface), supply-chain pinning, and operational correctness.

---

## What exists (high level)

1. **Dispatch router**
   - `gemini-dispatch.yml` listens to PR/issue/comment events and routes to:
     - PR review (`gemini-review.yml`)
     - Issue triage (`gemini-triage.yml`)
     - Manual “invoke” (`gemini-invoke.yml`)

2. **PR review**
   - `gemini-review.yml` checks out repo and runs `google-github-actions/run-gemini-cli@v0` to post a PR review via GitHub MCP.

3. **Manual invoke (chatops)**
   - `gemini-invoke.yml` runs `run-gemini-cli` on `@gemini-cli …` comments with a broad GitHub MCP tool allowlist.

4. **Issue triage (event driven)**
   - `gemini-triage.yml` runs on `issues.opened/reopened` (via dispatcher), asks Gemini to pick labels, then applies labels with validation.

5. **Issue triage (scheduled)**
   - `gemini-scheduled-triage.yml` runs hourly and attempts to triage a batch of open issues.

---

## Key findings

### 1) Highest-risk surface: untrusted issue content + long-lived API keys

- `gemini-triage.yml` and `gemini-scheduled-triage.yml` run Gemini on **untrusted issue bodies** (anyone who can open issues) while providing **`secrets.GEMINI_API_KEY` and `secrets.GOOGLE_API_KEY`** to a third-party action.
- Both workflows intentionally blank `GITHUB_TOKEN` for the Gemini step (good), but the static API keys are still present as action inputs and may be exposed if:
  - the action is compromised (supply-chain), or
  - the model is allowed to run commands that can surface environment/config (see next finding).

### 2) `printenv` is allowed in the scheduled triage Gemini tool allowlist

- In `.github/workflows/gemini-scheduled-triage.yml`, the Gemini “tools.core” allowlist includes `run_shell_command(printenv)`.
- This materially increases the chance of credential exfiltration (even if GitHub masks raw secret values in logs, secrets can sometimes be transformed/encoded and bypass masking).

### 3) Supply-chain hardening is inconsistent

- `actions/checkout`, `actions/github-script`, and `actions/create-github-app-token` are pinned to SHAs.
- `google-github-actions/run-gemini-cli@v0` is **not** pinned (and is explicitly excluded from “ratchet”), which keeps a moving target in a workflow that consumes secrets.
- `ghcr.io/github/github-mcp-server:v0.18.0` is pinned only by tag, not digest.

### 4) `secrets: inherit` increases blast radius

- `gemini-dispatch.yml` calls the reusable workflows with `secrets: inherit`.
- That means *any* repository secret is available to the called workflow jobs (even if not referenced), which increases impact if an action/tooling path is compromised.

### 5) Scheduled triage issue search query looks logically inconsistent

- `gemini-scheduled-triage.yml` uses:
  - `gh issue list --search 'no:label label:"status/needs-triage"'`
- If GitHub search treats spaces as AND (typical), this query is effectively unsatisfiable (an issue cannot have **no labels** and also have a specific label).
- If this is currently “working” in practice, it’s worth verifying the intended semantics (likely “no label OR has needs-triage label”).

### 6) Capability/permission mismatch: “invoke” includes write-ish tools but workflow permissions are read-only on contents

- `gemini-invoke.yml` includes MCP tools like `create_or_update_file`, `delete_file`, and `push_files`, but the workflow permissions specify `contents: read`.
- Net effect: those capabilities should fail at runtime; if the intent is “Gemini can open PRs / push branches”, permissions need to change; if not, the tool list should be reduced.

---

## Recommendations (prioritized)

1. **Remove `printenv` from Gemini tool allowlists** (especially in scheduled triage).
2. **Eliminate static API keys for untrusted-input workflows**:
   - Prefer Vertex AI auth via GitHub OIDC + WIF + a tightly scoped service account, and remove `GEMINI_API_KEY` / `GOOGLE_API_KEY` from the workflows that ingest untrusted issue content.
3. **Pin `run-gemini-cli` to a commit SHA** (and consider re-enabling ratchet pinning).
4. **Stop using `secrets: inherit`**; explicitly pass only the secrets needed by each reusable workflow.
5. **Fix/verify the scheduled triage issue search query** to match the intended issue set.
6. **Align MCP tool allowlists with intended permissions**:
   - Either remove repo-write tools from `gemini-invoke.yml`, or (if intended) explicitly grant `contents: write` and document guardrails.

---

## Questions to confirm intent

1. Is this repository public, or are issues limited to org members?
2. Do you want Gemini to be able to *write* to the repo (create branches/PRs/commit), or only comment/review?
3. Should issue triage run automatically on `issues.opened`, or only when a collaborator opts in (e.g. `@gemini-cli /triage`)?

## Resolution

2026-02-03: Repository confirmed public; decision taken to remove all Gemini GitHub Actions workflows entirely.
