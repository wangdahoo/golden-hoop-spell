# Coding Agent Reference

## Table of Contents
1. [Session Protocol](#session-protocol)
2. [Implementation Process](#implementation-process)
3. [Parallel Mode](#parallel-mode)
4. [File Schemas](#file-schemas)
5. [Testing Requirements](#testing-requirements)
6. [Examples](#examples)

## Session Protocol

### Start of Session

**Always perform in order:**

1. **Confirm Location**
   ```bash
   python3 scripts/resolve_project_dir.py
   ```
   Store the output as the absolute project directory. Use it for all reads/writes of `.ghs/features.json` and `.ghs/progress.md`.

2. **Review Recent Work**
   ```bash
   git log --oneline -10
   ```
   Read `.ghs/progress.md` to understand previous sessions. This step is mandatory — it provides the context from prior sessions that enables continuity across context windows.

3. **Review Feature Status**
   Read `.ghs/features.json` to see:
   - Current sprint status
   - Completed features
   - In-progress features
   - Pending features
   - Dependencies

4. **Verify Project State**
   Run lint and build commands (see project's AGENTS.md).

   **⚠️ If broken, fix existing issues before starting new work.**

### End of Session

**Always perform in this order:**

1. Ensure no lint/build errors
2. Commit implementation changes (before touching any `.ghs/` files):
   ```bash
   git add <list each modified implementation file explicitly>
   git commit -m "feat(<scope>): <description>"
   ```
3. Update `.ghs/features.json` if feature complete
4. Update `.ghs/progress.md` with session summary

## Implementation Process

### Step 1: Select Feature

Choose **ONE** feature per session. Prioritize:

1. Features from current in-progress sprint
2. High-priority pending features with completed dependencies
3. Features that build on recent work

### Step 2: Understand Feature

Before coding:

1. Read acceptance criteria carefully
2. Review technical notes
3. Verify dependencies are satisfied
4. Identify affected files
5. Plan implementation approach

### Step 3: Plan Implementation

Write a brief plan covering:
- Which files will be modified
- What patterns to follow
- What tests to write
- Potential challenges

### Step 4: Implement Incrementally

**Key principles:**

1. **Small Commits** - Frequent, logical commits
2. **Test Continuously** - Verify each change
3. **Stay Focused** - Don't scope-creep
4. **Follow Conventions** - Match existing code style

**Commit message format:**
```
<type>(<scope>): <description>

[optional body]

Feature: <feature-id>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`

### Step 5: Verify Implementation

Check all acceptance criteria:
- [ ] Each criterion can be demonstrated
- [ ] Happy path works
- [ ] Error scenarios handled
- [ ] Edge cases considered

## Parallel Mode

When invoked with `--parallel`, the Coding Agent switches to parallel orchestration mode. Instead of implementing one feature at a time, it analyzes the dependency graph and dispatches subagents to implement multiple features concurrently.

### Pre-flight Checks

Perform these checks in order before starting orchestration:

1. **Confirm Location**
   ```bash
   python3 scripts/resolve_project_dir.py
   ```
   Store the output as the absolute project directory.

2. **Check for Uncompleted Sprint**
   Read `.ghs/features.json` and look for a sprint with status `in_progress` or `planning` that has features with status `pending` or `blocked`.

   If no uncompleted sprint exists, exit with:
   ```
   No uncompleted sprint found. Run /ghs:sprint first to plan a sprint.
   ```

3. **Review Recent Context** — Read `.ghs/progress.md` for recent work, blockers, and project state.

4. **Verify Clean Working Tree**
   ```bash
   git status
   ```
   If there are uncommitted changes, exit with:
   ```
   Working tree has uncommitted changes. Please commit or stash before running parallel mode.
   ```

### Analysis Phase

#### Step 1: Build Dependency Graph

For each pending/blocked feature, check if all dependencies are satisfied:

```python
def get_ready_features(features):
    """Get features whose dependencies are all completed."""
    completed_ids = {f["id"] for f in features if f["status"] == "completed"}

    ready = []
    for f in features:
        if f["status"] in ("pending", "blocked"):
            deps = set(f.get("dependencies", []))
            if deps.issubset(completed_ids):
                ready.append(f)

    return ready
```

#### Step 2: Detect File Conflicts

Group features by file overlap. Features modifying the same files cannot run in parallel:

```python
def build_parallel_batches(features, max_parallel=5):
    """
    Group features into batches respecting file conflicts.
    Features in the same batch can run in parallel (no file overlap).
    Batches run sequentially.
    """
    batches = []
    remaining = features.copy()

    while remaining:
        batch = []
        files_in_use = set()

        for f in remaining:
            if len(batch) >= max_parallel:
                break
            f_files = set(f.get("files_affected", []))
            if not f_files & files_in_use:  # No overlap
                batch.append(f)
                files_in_use |= f_files

        if not batch:
            batch = [remaining[0]]
            files_in_use = set(remaining[0].get("files_affected", []))

        batches.append(batch)
        for f in batch:
            remaining.remove(f)

    return batches
```

#### Step 3: Output Execution Plan

Display the execution plan to the user:

```
Parallel Execution Plan
==================
Total ready features: 8
Max parallelism: 5

Batch 1 (parallel):
  - s1-feat-002: Add login page (files: src/auth/login.ts)
  - s1-feat-003: Add signup page (files: src/auth/signup.ts)
  - s1-feat-004: Add API client (files: src/api/client.ts)

Batch 2 (parallel):
  - s1-feat-005: Connect login to API (files: src/auth/login.ts, src/api/client.ts)
  - s1-feat-006: Add dashboard (files: src/pages/dashboard.tsx)
```

### Dispatch Phase

For each feature, spawn a subagent with this prompt structure:

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
2. Implement the feature following the coding-agent.md guidelines
3. Test all acceptance criteria
4. Run lint/build to verify no breakage
5. Commit your changes (only implementation files — do NOT modify .ghs/ files): list each modified file explicitly with `git add`, then commit with message: feat(<scope>): <brief description> (Feature: <feature_id>)

## Critical Rules
- Do NOT modify .ghs/features.json or .ghs/progress.md - the orchestrator will update these after your commit
- Focus ONLY on this feature - do not modify unrelated code
- Ensure the codebase remains in a working state
- Signal completion by stating "FEATURE COMPLETE: <feature_id>" at the end
- If you cannot complete the feature, state "FEATURE BLOCKED: <feature_id> - <reason>"
```

Use the Agent tool to spawn subagents:

```json
{
  "subagent_type": "general-purpose",
  "description": "Implement feature <id>",
  "prompt": "<full prompt from template above>",
  "run_in_background": true
}
```

For each batch:
1. Spawn all subagents in the batch as background tasks
2. Wait for all subagents to complete
3. Collect results (success/failure) for each feature
4. Proceed to verification phase

### Verification Phase

For each completed subagent:

1. **Check Completion Signal** — Look for "FEATURE COMPLETE: <id>" in output. If "FEATURE BLOCKED: <id>" found, mark as blocked.
2. **Verify Code Quality** — Run lint and build commands
3. **Verify Acceptance Criteria** — Review implementation against each criterion
4. **Record Result**:
   ```python
   results = {
       "feature_id": {
           "status": "completed" | "blocked",
           "reason": None | "<failure_reason>",
           "files_changed": ["list", "of", "files"]
       }
   }
   ```

### State Update Phase

Subagents already committed their implementation files individually. No further git commits needed — the orchestrator only updates local tracking files.

1. **Update .ghs/features.json** — Completed features get `status: "completed"`, blocked get `status: "blocked"` with `blocked_reason`

2. **Write .ghs/progress.md entry** — Add parallel orchestration summary at the top of sessions section:

```markdown
## Parallel Orchestration - YYYY-MM-DD
**Agent**: Coding Agent (Parallel Mode)
**Sprint**: [Sprint ID]
**Max Parallelism**: [N]

### Execution Summary
| Feature | Status | Result |
|---------|--------|--------|
| s1-feat-002 | completed | success |
| s1-feat-003 | completed | success |
| s1-feat-004 | blocked | lint errors in src/api/client.ts |

### Statistics
- Total features: 8
- Completed: 6
- Blocked: 2
- Success rate: 75%

### Next Steps
- Review and fix blocked features manually
- Run /ghs:code to address remaining issues
```

### Parallel Mode Error Handling

- **Subagent Failure**: Record failure, continue other subagents, document in .ghs/progress.md
- **Merge Conflicts**: Detect via build/lint failures, isolate conflicting features, revert if needed
- **Catastrophic Failure**: Stop orchestration, run full test suite, rollback if needed, recommend single-feature mode

### Parallel Mode Critical Rules

1. **Continue on Failure** — Blocked features don't stop other features
2. **Respect File Conflicts** — Features modifying same files run sequentially
3. **Max 5 Concurrent Subagents** — Never exceed this limit
4. **Orchestrator Updates State** — Subagents don't modify .ghs/features.json or .ghs/progress.md
5. **Clean State Required** — Only run parallel mode on clean working tree
6. **Context Isolation** — Every subagent MUST receive CONTEXT RESET header

## File Schemas

### progress.md Structure

Add entry at **top** of sessions section:

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
- path/to/another.ts - [brief description]

### Tests Performed
- [How the feature was verified]
- [What scenarios were tested]

### Issues Encountered
- [Any blockers or bugs found]
- [How they were resolved]

### Acceptance Criteria Status
- [x] Criterion 1
- [x] Criterion 2
- [ ] Criterion 3 (if incomplete, explain why)

### Next Steps
- [Recommended next feature or follow-up]
```

### features.json Updates

Only update feature status field:

```json
{
  "id": "s1-feat-001",
  "status": "completed"  // or "in_progress"
}
```

### Feature Status Values

| Status | When to Use |
|--------|-------------|
| `pending` | Not started |
| `in_progress` | Currently being worked on |
| `completed` | Fully implemented and tested |
| `blocked` | Cannot proceed due to blocker |

## Testing Requirements

### Pre-Completion Testing

Before marking feature complete:

1. **Functional Testing**
   - Test as a user would interact
   - Verify all acceptance criteria
   - Check happy path and errors

2. **Cross-Platform Testing**
   - Test relevant platforms for the project
   - See project's AGENTS.md for requirements

3. **Technical Testing**
   - Lint passes (see AGENTS.md for command)
   - Build succeeds (see AGENTS.md for command)
   - Application starts without errors
   - No console errors

### Testing Checklist

```
☐ Happy path works
☐ Error handling works
☐ Responsive on all devices (if applicable)
☐ Theme compatibility (if applicable)
☐ Internationalization (if applicable)
☐ No console errors
☐ No lint errors
☐ Build passes
```

## Examples

See [examples.md](examples.md) for complete examples.

## Quality Checklist

### Before Marking Feature Complete

```
☐ All acceptance criteria met
☐ Lint passes
☐ Build succeeds
☐ Manual testing completed
☐ Code committed with descriptive message
☐ .ghs/progress.md updated
☐ .ghs/features.json status updated
☐ No TODO comments left
☐ No debug code remaining
```

### End of Session Checklist

```
☐ Feature complete (or clearly documented why not)
☐ No lint or build errors
☐ Code committed (before updating .ghs/ files)
☐ .ghs/features.json updated (if feature complete)
☐ .ghs/progress.md updated
☐ Application in working state
```

## Critical Rules

1. **One Feature Per Session** - Don't try to do too much
2. **Always Leave Working Code** - Never leave codebase broken
3. **Follow Acceptance Criteria** - Implement exactly what's specified
4. **Follow Project Conventions** - See project's AGENTS.md for code style
5. **Don't Modify .ghs/features.json Lightly** - Only change feature status
6. **Commit Frequently** - Enable rollback

## Red Flags - Stop and Fix

**Stop immediately if you encounter:**

- Build errors
- Lint errors
- Failing tests
- Application won't start
- Previously working feature broken
- Uncommitted changes from previous session

**Fix these before proceeding with new work.**
