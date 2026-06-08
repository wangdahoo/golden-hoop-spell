---
name: ghs:code
description: "Start a coding session to implement the next feature. USE WHEN user wants to implement a feature, start coding, work on the next task, or continue development. Supports single-feature mode (default) and parallel mode (--parallel flag). Trigger on: 'implement next feature', 'start coding', 'code session', 'run coding agent', 'implement in parallel'. This is the primary development workflow skill for ghs managed projects."
argument-hint: "[--parallel] [--max-parallel=N]"
---

# Feature Implementation

Implement features from the current sprint. Two modes: **single feature** (default) and **parallel** (multiple features at once via `--parallel`).

## Prerequisites

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

3. **Review feature status**: Read `.ghs/features.json` to see current sprint, completed/in-progress/pending features, and dependencies.

4. **Verify project state**: Run lint and build commands. If broken, **fix existing issues before starting new work**.

---

## Single Feature Mode (default)

### Step 1: Select Feature

Choose **ONE** feature per session. Prioritize:
1. Features from current in-progress sprint
2. High-priority pending features with completed dependencies
3. Features that build on recent work

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

Commit message format: `<type>(<scope>): <description>` (types: feat, fix, refactor, test, docs, chore, style)

### Step 4: Verify

Check all acceptance criteria:
- Happy path works
- Error scenarios handled
- Edge cases considered
- Lint passes, build succeeds
- No console errors

### Step 5: End of Session

1. Update `.ghs/progress.md` with session summary at the **top** of the sessions section:

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

2. Update the feature status in `.ghs/features.json` (only change `status` field):
   - `completed` — all acceptance criteria met, tests pass
   - `blocked` — cannot proceed, document reason in `blocked_reason`

3. Commit implementation changes:
   ```bash
   git add [implementation files]
   git commit -m "feat(<scope>): <description>"
   ```

---

## Parallel Mode (`--parallel`)

When invoked with `--parallel`, implement multiple independent features concurrently using subagents.

### Pre-flight Checks

1. Resolve project directory (same as above)
2. Check for an uncompleted sprint with pending features. If none, exit with: "No uncompleted sprint found. Run `/ghs:sprint` first."
3. Verify clean working tree (`git status`). If uncommitted changes exist, exit with: "Working tree has uncommitted changes. Please commit or stash first."

### Analysis Phase

1. **Build dependency graph**: For each pending/blocked feature, check if all dependencies are completed. Collect all "ready" features.

2. **Detect file conflicts**: Group features by file overlap. Features modifying the same files **cannot** run in parallel.

3. **Create batches**: Group non-conflicting ready features into batches (max 5 concurrent). Display the execution plan to the user.

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
5. Commit your changes with message: feat(<scope>): <brief description> (Feature: <feature_id>)

## Critical Rules
- Do NOT modify .ghs/features.json or .ghs/progress.md - the orchestrator will update these
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

For each completed subagent:
- Check for "FEATURE COMPLETE: \<id\>" or "FEATURE BLOCKED: \<id\>" in output
- Verify code quality (lint/build)
- Verify acceptance criteria

### State Update Phase

1. Update `.ghs/features.json` — completed features get `status: "completed"`, blocked get `status: "blocked"`
2. Add parallel orchestration summary to top of `.ghs/progress.md` sessions section
3. Final commit (implementation files only):
   ```bash
   git add [implementation files]
   git commit -m "chore: parallel orchestration complete - N/M features completed"
   ```

### Parallel Error Handling

- **Subagent failure**: Record failure, continue others, document in .ghs/progress.md
- **Merge conflicts**: Detect via build/lint failures, isolate, revert if needed
- **Catastrophic failure**: Stop orchestration, run full tests, rollback if needed, recommend single-feature mode

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
