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
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
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
   Run lint and build commands (see project's AGENTS.md, or CLAUDE.md if AGENTS.md does not exist).

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
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
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

#### Step 1: Identify Ready Features and Build Batches

Use `parallel_utils.py` to identify ready features and build conflict-free parallel batches. This script reads `.ghs/features.json`, detects dependency cycles, identifies features whose dependencies are all completed, and groups them into batches that respect file-level conflicts:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parallel_utils.py \
  --project-dir "<PROJECT_DIR>" \
  --max-parallel 5 \
  --sprint-id "<SPRING_ID>"
```

Output is JSON with the following structure:

```json
{
  "ready_features": [ /* features with all deps completed */ ],
  "batches": [
    [ /* batch 1: features with no file overlap */ ],
    [ /* batch 2: features with no file overlap, but conflict with batch 1 */ ]
  ],
  "skipped": [ /* features not ready (deps unmet, wrong status, or in cycles) */ ],
  "cycles": [ /* detected circular dependency chains */ ],
  "cycle_feature_ids": [ /* feature IDs involved in any cycle */ ]
}
```

Each feature in the output includes: `id`, `title`, `status`, `files_affected`, and `dependencies`.

Key batching rules (enforced by `parallel_utils.py`):
- Only `pending` features with all dependencies `completed` are considered ready
- Features involved in dependency cycles are skipped
- Features with overlapping `files_affected` are never placed in the same batch
- Maximum of 5 features per batch (configurable via `--max-parallel`)

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
This is an isolated task. Disregard prior context, assume nothing, read files fresh, start clean.

## Your Task
1. Open `<PROJECT_DIR>/.ghs/features.json`, find your feature by `id == "<feature_id>"` under `sprints[].features[]`. Read its `description`/`acceptance_criteria`/`technical_notes`/`files_affected` — these are your source of truth, not the title.
2. If the containing sprint has a `plan_ref` field, open that plan file (relative to project root) and read any sections your `technical_notes` references (e.g. "参考 plan §3.3 ..." means read §3.3). If `plan_ref` is missing or the file does not exist, log a one-line warning and proceed with `technical_notes` verbatim.
3. Read `<PROJECT_DIR>/.ghs/progress.md` for recent project context.
4. Implement the feature following the coding-agent.md guidelines; verify all `acceptance_criteria` are met.
5. Run lint/build, then make a **single** commit (stage all modified implementation files with `git add`; do NOT commit `.ghs/*` files) with message: `feat(<scope>): <brief description> (Feature: <feature_id>)`.

## Feature ID
<feature_id>

## Critical Rules
- Do NOT modify `.ghs/` files. You may READ `features.json` but MUST NOT write.
- Focus ONLY on this feature.
- End with EXACTLY ONE signal: `FEATURE COMPLETE: <feature_id>` or `FEATURE BLOCKED: <feature_id> - <reason>`.
```

The orchestrator MUST substitute `<PROJECT_DIR>` (from `resolve_project_dir.py`) and `<feature_id>` (from the batch feature list) into the prompt before spawning. The prompt contains NO inline feature details — the subagent reads them from `.ghs/features.json` per Task step 1. Note: the prompt does NOT contain a `<sprint_id>` placeholder — the subagent locates its feature by `id == "<feature_id>"` across `sprints[].features[]`, so the orchestrator does not need to pass `sprint_id`.

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

For each background subagent that returns:

1. **Capture raw output and save to disk** for post-mortem debugging:
   ```
   <PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N>
   ```
   `attempt<N>` starts at 1 for the first try within a feature; retries increment N.

2. **Invoke the parser helper.**

   > **You MUST copy this command verbatim, only replacing the `<placeholders>`. Do NOT grep the subagent output yourself — the helper is the single source of truth for completion-signal extraction.**

   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/parse_completion_signal.py \
     --feature-id <feature_id> \
     --input-file <PROJECT_DIR>/.ghs/parallel/<sprint_id>/<feature_id>.raw.attempt<N> \
     --min-length 50
   ```

3. **Branch on `status` (read from JSON, do not re-parse the text):**
   - **`completed`**:
     1. **Run the commit/files sanity check** (前置门 — pass 才允许写 features.json):
        - 从 `<PROJECT_DIR>/.ghs/features.json` 读 feature `<feature_id>` 的 `files_affected` 字段，得 `expected_files`（list）。
        - **立即检查 expected_files 是否为空**：若 `expected_files == []`（features.json 中该字段缺失或为空 list），**整个 sanity check 跳过**，视为通过，日志记录 `"sanity check skipped: feature <feature_id> has no files_affected in features.json"`。此跳过分支**必须在读 git log 之前判断**，不得合并到下面的空集检查。
        - 读 subagent 的 commit log（`git log --since=<dispatch_start_iso> --name-only --pretty=format:"%H %s"`，dispatch_start_iso 见下方备注），得 `actual_files`（list，去重）。
        - 计算 `intersection = set(expected_files) ∩ set(actual_files)`。
        - 如果 `intersection` 为空（即所有 commit 加起来一个期望文件都没碰），**不要标记 feature 完成**，触发 Format Recovery retry，appendix 中加一句：`Your commit did not touch any file listed in this feature's files_affected in features.json. Did you read features.json to find your feature's expected files?`。retry 后仍空则走 User Decision Handling。**此分支不写 features.json。**
        - 如果 `intersection` 非空（或 sanity check 走 skip 分支），进入步骤 2。
     2. Update `.ghs/features.json` for `<feature_id>` with `status: "completed"`. Run lint/build to verify code quality. Verify acceptance criteria. Proceed to next feature.

     **备注**：`dispatch_start_iso` 是 orchestrator 在 Dispatch Phase spawn 该 subagent 那一刻记录的 ISO 时间戳（`datetime.now(timezone.utc).isoformat()`），用于时间窗 git log 查询，覆盖 subagent 可能的多 commit。
   - **`blocked`** → Update `.ghs/features.json` with `status: "blocked"` and `blocked_reason: <reason from JSON>`. Record result and proceed.
   - **`unknown`** with `retry_count < MAX_RETRY (=1)` → Increment `retry_count`, re-dispatch the subagent with the original prompt plus the Format Recovery appendix. Save next raw to `<feature_id>.raw.attempt<N+1>`. Return to step 1.
   - **`unknown`** with `retry_count >= MAX_RETRY` → Use AskUserQuestion per the User Decision Handling table. **Never silently hang on an unparseable response.**

4. **Record Result**:
   ```python
   results = {
       "feature_id": {
           "status": "completed" | "blocked" | "unknown",
           "reason": None | "<failure_reason>",
           "strategy": "<exact_signal | case_insensitive | natural_language | none>",
           "raw_file": "<path/to/feature_id>.raw.attempt<N>",
           "files_changed": ["list", "of", "files"]
       }
   }
   ```

#### Format Recovery (retry appendix)

When retrying a subagent whose previous output could not be parsed, append this block verbatim to the original prompt (replace `<feature_id>` with the actual ID):

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

#### User Decision Handling

When retry is exhausted (`retry_count >= MAX_RETRY`) and the parser still cannot determine the outcome, use AskUserQuestion with these four options:

| Option | Dispatcher behavior | File side-effects | When available |
|--------|---------------------|-------------------|----------------|
| **Retry once more** | Increment `retry_count`, re-dispatch with Format Recovery appendix | New `<feature_id>.raw.attempt<N+1>` | Always available |
| **Manually mark as completed** | Update `.ghs/features.json` with `status: "completed"`. Annotate `.ghs/progress.md` noting "manually marked after format deviation retry" | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available — but only choose this after manually verifying (commit log + file diff) |
| **Manually mark as blocked** | Update `.ghs/features.json` with `status: "blocked"` + user-supplied `blocked_reason`. Annotate `.ghs/progress.md` | `.ghs/features.json` written; `.ghs/progress.md` annotated | Always available |
| **Abort this feature, continue with others** | Leave `.ghs/features.json` for this feature at `status: "pending"`. Annotate `.ghs/progress.md`. Continue with other features in the batch | `.ghs/features.json` unchanged for this feature; `.ghs/progress.md` annotated | Always available (parallel mode only) |

The AskUserQuestion prompt must show the parser's `status`, `strategy`, and `warnings` from the most recent attempt, list the four options, and include the path to the most recent `.raw.attempt<N>` file so the user can inspect the raw subagent output before deciding.

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
| `blocked` | Cannot proceed due to blocker (include `blocked_reason`) |

When a feature is marked `blocked`, include a `blocked_reason` field explaining why:

```json
{
  "id": "s1-feat-005",
  "status": "blocked",
  "blocked_reason": "Depends on s1-feat-003 which has lint errors"
}
```

## Testing Requirements

### Pre-Completion Testing

Before marking feature complete:

1. **Functional Testing**
   - Test as a user would interact
   - Verify all acceptance criteria
   - Check happy path and errors

2. **Cross-Platform Testing**
   - Test relevant platforms for the project
   - See project's AGENTS.md (or CLAUDE.md if AGENTS.md does not exist) for requirements

3. **Technical Testing**
   - Lint passes (see AGENTS.md, or CLAUDE.md if AGENTS.md does not exist, for command)
   - Build succeeds (see AGENTS.md, or CLAUDE.md if AGENTS.md does not exist, for command)
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
4. **Follow Project Conventions** - See project's AGENTS.md (or CLAUDE.md if AGENTS.md does not exist) for code style
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
