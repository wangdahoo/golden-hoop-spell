---
name: ghs:code
description: "Implement features from the current sprint plan. Supports single-feature mode (default, one feature per session) and parallel mode (--parallel for independent features). This is the primary development workflow for ghs-managed projects."
argument-hint: "[--parallel] [--max-parallel=N]"
---

# Feature Implementation

Implement features from the current sprint. Two modes: **single feature** (default) and **parallel** (multiple features at once via `--parallel`).

## Prerequisites

**Verify python3 works** before any other step:
```bash
python3 --version
```
If this errors with "_lazy_pyenv command not found" (or similar), your shell
has a half-loaded pyenv lazy loader. Workaround: use the full path
`/usr/bin/python3` for all subsequent python invocations in this session.

The project must have an active sprint with pending features. If not, tell the user to run `/ghs:sprint` first.

## Session Protocol

### Start of Session (always perform in order)

1. **Resolve project directory**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
   ```
   Store the output as `PROJECT_DIR` for all subsequent reads/writes.

2. **Review recent work**:
   ```bash
   git log --oneline -10
   ```
   Read `.ghs/progress.md` to understand previous sessions.

3. **Validate project structure**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"
   ```
   If validation fails, report errors and stop. Fix issues before proceeding.

4. **Review feature status**: Read `.ghs/features.json` to see current sprint, completed/in-progress/pending features, and dependencies.

5. **Verify project state**: Run lint and build commands. If broken, **fix existing issues before starting new work**.

---

## Single Feature Mode (default)

### Step 1: Select Feature

Choose **ONE** feature per session. Prioritize:
1. Features from current in-progress sprint
2. High-priority pending features with completed dependencies
3. Features that build on recent work

**Recovery protocol**: If a feature has status `in_progress` but the working tree is clean (no uncommitted changes related to it), treat it as `pending` and offer to pick it up. This handles cases where a previous session was interrupted after updating status but before completing work.

### Step 2: Understand Feature

- Read acceptance criteria carefully
- Verify dependencies are satisfied
- Identify affected files
- Plan implementation approach

### Step 3: Implement Incrementally

- **Small commits** — frequent, logical commits
- **Test continuously** — verify each change
- **Stay focused** — don't scope-creep
- **Follow conventions** — match existing code style

Commit message format: `<type>(<scope>): <description> (Feature: <feature-id>)` (types: feat, fix, refactor, test, docs, chore, style)

### Step 4: Verify

Check all acceptance criteria:
- Happy path works
- Error scenarios handled
- Edge cases considered
- Lint passes, build succeeds
- No console errors

### Step 5: End of Session

1. **Commit implementation changes first** (before touching any `.ghs/` files):
   ```bash
   git add <list each modified implementation file explicitly>
   git commit -m "feat(<scope>): <description> (Feature: <feature-id>)"
   ```

2. Update the feature status in `.ghs/features.json` (only change `status` field):
   - `completed` — all acceptance criteria met, tests pass
   - `blocked` — cannot proceed, document reason in `blocked_reason`

3. Update `.ghs/progress.md` with session summary at the **top** of the sessions section:

```markdown
## Session N - YYYY-MM-DD
**Agent**: Coding Agent
**Sprint**: [Sprint ID]
**Feature**: [Feature ID and title]

### Implementation
- [What was implemented]
- [Key decisions made]

### Files Changed
- path/to/file.ts - [brief description]

### Tests Performed
- [How the feature was verified]

### Issues Encountered
- [Any blockers or bugs found]

### Acceptance Criteria Status
- [x] Criterion 1
- [x] Criterion 2

### Next Steps
- [Recommended next feature]
```

---

## Parallel Mode (`--parallel`)

When invoked with `--parallel`, implement multiple independent features concurrently using subagents.

### Pre-flight Checks

1. Resolve project directory (same as above)
2. Check for an uncompleted sprint with pending features. If none, exit with: "No uncompleted sprint found. Run `/ghs:sprint` first."
3. Verify clean working tree (`git status`). If uncommitted changes exist, exit with: "Working tree has uncommitted changes. Please commit or stash first."

### Analysis Phase

1. **Identify ready features and build batches**: Use `parallel_utils.py` to get ready features and conflict-free batches:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py --project-dir "<PROJECT_DIR>" --max-parallel <N>
   ```
   The script outputs JSON with `ready_features`, `batches`, `skipped`, and any `cycles` detected. Use the `batches` output directly for dispatch.

2. **Detect file conflicts**: Group features by file overlap. Features modifying the same files **cannot** run in parallel. (Handled automatically by `parallel_utils.py`.)

3. **Create batches**: Group non-conflicting ready features into batches. Display the execution plan to the user.

### Dispatch Phase

For each feature, spawn a subagent with this prompt:

```
Implement ONE feature for this project.

## CONTEXT RESET - READ THIS FIRST
This is an isolated task. You MUST:
1. DISREGARD any context from previous conversations or tasks
2. NOT assume any prior knowledge about the project state
3. Read all necessary files fresh to understand current state
4. Start with a clean mental state - this is your ONLY task

## Feature Details
- **ID**: <feature_id>
- **Title**: <title>
- **Description**: <description>
- **Acceptance Criteria**:
  <criteria_list>
- **Technical Notes**: <technical_notes>
- **Files to Modify**: <files_affected>

## Your Task
1. Read .ghs/features.json and .ghs/progress.md to understand project context
2. Implement the feature
3. Test all acceptance criteria
4. Run lint/build to verify no breakage
5. Commit your changes (only implementation files — do NOT modify .ghs/ files): list each modified file explicitly with `git add`, then commit with message: feat(<scope>): <brief description> (Feature: <feature_id>)

## Critical Rules
- Do NOT modify .ghs/features.json or .ghs/progress.md - the orchestrator will update these after your commit
- Focus ONLY on this feature
- Ensure the codebase remains in a working state
- Signal completion by stating "FEATURE COMPLETE: <feature_id>" at the end
- If you cannot complete the feature, state "FEATURE BLOCKED: <feature_id> - <reason>"
```

Spawn as background agents:
```json
{
  "subagent_type": "general-purpose",
  "description": "Implement feature <id>",
  "prompt": "<full prompt from template above>",
  "run_in_background": true
}
```

### Verification Phase

For each background subagent that returns:

1. Capture the raw output (via TaskOutput or equivalent) and save it to disk for post-mortem debugging:
   ```
   <PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N>
   ```
   `attempt<N>` starts at 1 for the first try within a feature; retries increment N.

2. Invoke the parser helper.

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT grep the subagent output yourself — the helper is the single source of truth for completion-signal extraction.**

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_completion_signal.py \
     --feature-id <feature_id> \
     --input-file <PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N> \
     --min-length 50
   ```

3. Read the JSON object printed to stdout. Branch on `status`:

   - **`completed`**: Update `.ghs/features.json` for `<feature_id>` with `status: "completed"`. Run lint/build to verify code quality. Verify acceptance criteria. Proceed to next feature.
   - **`blocked`**: Update `.ghs/features.json` with `status: "blocked"` and `blocked_reason: <reason from JSON>`. Proceed to next feature.
   - **`unknown`** with `retry_count < MAX_RETRY (=1)`: Increment `retry_count`, re-dispatch the subagent with the original prompt plus the [Format Recovery](#format-recovery) appendix for completion signals. Save the next raw response to `<feature_id>.raw.attempt<N+1>` and return to step 2.
   - **`unknown`** with `retry_count >= MAX_RETRY`: Use AskUserQuestion per [## User Decision Handling](#user-decision-handling). **Never silently hang on an unparseable response.**

### State Update Phase

Subagents already committed their implementation files individually. No further git commits needed — the orchestrator only updates local tracking files.

1. Update `.ghs/features.json` — completed features get `status: "completed"`, blocked get `status: "blocked"`
2. Add parallel orchestration summary to top of `.ghs/progress.md` sessions section

### Parallel Error Handling

- **Subagent failure**: Record failure, continue others, document in .ghs/progress.md
- **Merge conflicts**: Detect via build/lint failures, isolate, revert if needed
- **Catastrophic failure**: Stop orchestration, run full tests, rollback if needed, recommend single-feature mode

## Error Handling

- **Subagent failure** (parallel mode): Record failure, continue other subagents, document in `.ghs/progress.md`.
- **Subagent output format deviation**: If the subagent returns successfully but the output cannot be parsed via the completion-signal protocol (detected via `parse_completion_signal.py` returning `status: "unknown"`), retry once with the [Format Recovery](#format-recovery) appendix appended to the prompt. If retry still fails, the raw output is already saved at `<PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N>`; use AskUserQuestion to let the user decide (retry / manually mark completed / manually mark blocked / abort — see [## User Decision Handling](#user-decision-handling)). **Never silently hang on an unparseable response.**
- **Merge conflicts**: Detect via build/lint failures, isolate conflicting features, revert if needed.
- **Catastrophic failure**: Stop orchestration, run full test suite, rollback if needed, recommend single-feature mode.
- **File read/write failure**: Check paths and permissions, notify the user.
- **User not responding**: Wait, do not proceed automatically.

## Format Recovery

When a subagent returns output the parser cannot extract (`status: "unknown"`), the dispatcher retries the subagent once with a stronger format reminder appended to the prompt.

**Constants**:
- `MAX_RETRY = 1` — each subagent call may be re-dispatched at most once. This counter is independent from the sprint-level retry count.

**Raw file naming** (preserves every attempt for post-mortem debugging):
- Parallel mode: `<PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N>` — N starts at 1 for the first try, increments per retry.

**Retry appendix template** (append verbatim to the original subagent prompt; replace `<feature_id>` with the actual ID):

```
## IMPORTANT: Previous Output Format Issue
Your previous response did not contain the required completion signal.
The dispatcher could not determine whether the feature is complete.

This time you MUST end your response with EXACTLY ONE of:
  - "FEATURE COMPLETE: <feature_id>"  (if successful)
  - "FEATURE BLOCKED: <feature_id> - <reason>"  (if blocked)

The signal line must:
1. Be on its own line
2. Use uppercase FEATURE
3. Use the exact feature_id given above
4. For BLOCKED, include a one-line reason after the dash

Do NOT use:
- "Feature Complete" (lowercase)
- "FEATURE COMPLETED" (extra D)
- "The feature is complete" (natural language)
- Chinese variants like "特性完成"
```

## User Decision Handling

When retry is exhausted (`retry_count >= MAX_RETRY`) and the parser still cannot determine the outcome, the dispatcher uses AskUserQuestion to let the user decide. The four options and their semantics:

| Option | Dispatcher behavior | File side-effects | When available |
|--------|---------------------|-------------------|----------------|
| **Retry once more** | Increment `retry_count` (one-shot override past `MAX_RETRY`), re-dispatch the subagent with the [Format Recovery](#format-recovery) appendix | New `<feature_id>.raw.attempt<N+1>` | Always available |
| **Manually mark as completed** | Update `.ghs/features.json` for the feature with `status: "completed"`. Note in `.ghs/progress.md` that the feature was "manually marked after format deviation retry" | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available — but only choose this if you have manually verified the implementation (commit log + file diff) |
| **Manually mark as blocked** | Update `.ghs/features.json` with `status: "blocked"` and a `blocked_reason` you supply. Note in `.ghs/progress.md` | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available |
| **Abort this feature, continue with others** | Leave `.ghs/features.json` for this feature at `status: "pending"`. Note the abort decision in `.ghs/progress.md`. Continue with other features in the batch | `.ghs/features.json` unchanged for this feature; `.ghs/progress.md` annotated | Always available (parallel mode only) |

The AskUserQuestion prompt must:
1. Show the parser's `status`, `strategy`, and `warnings` from the most recent attempt.
2. List the four options above.
3. Include the path to the most recent `.raw.attempt<N>` file so the user can inspect the raw subagent output before deciding.

---

## Reference

For detailed schemas and more examples:
- `${CLAUDE_PLUGIN_ROOT}/shared/references/coding-agent.md` — Full session protocol, parallel mode details, testing requirements
- `${CLAUDE_PLUGIN_ROOT}/shared/references/examples.md` — Realistic examples of features.json, progress.md, and workflows

## Critical Rules

1. **One Feature Per Session** (single mode) — Don't implement multiple
2. **Always Leave Working Code** — Never break the build
3. **Test End-to-End** — Verify as user would experience
4. **Commit Frequently** — Small commits enable rollback
5. **Never Delete Features** — Only change status
6. **Use Progress Log** — Record every session

## Red Flags — Stop and Fix

Stop immediately if you encounter: build errors, lint errors, failing tests, app won't start, previously working feature broken, or uncommitted changes from previous session. Fix these before proceeding.
