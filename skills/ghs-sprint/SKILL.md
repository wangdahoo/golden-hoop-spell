---
name: ghs:sprint
description: "Plan a sprint by breaking requirements into atomic, implementable features. USE WHEN user mentions sprint planning, feature breakdown, creating a sprint, planning an iteration, breaking down requirements, or multi-session project planning. Also trigger when user wants to update or modify planned features, add features to an existing sprint, or reorganize sprint priorities."
---

# Sprint Planning

Break down requirements into atomic features with acceptance criteria, dependencies, and priorities. Update `features.json` and `progress.md`.

## Prerequisites

The project must be initialized (have `features.json` and `progress.md`). If not, tell the user to run `/ghs:init` first.

Resolve the project directory:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Planning Process

### Step 1: Archive Completed Sprints

Before creating a new sprint, check for completed sprints to archive:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py --list --project-dir "<PROJECT_DIR>"
```

If there are completed sprints, offer to archive them before proceeding.

### Step 2: Analyze Requirements

Break requirements into categories:
- **Core Features** — Essential for the sprint goal
- **Supporting Features** — Enhance core functionality
- **Technical Enablers** — Infrastructure, refactoring

Context sources:
- User's requirements (from the command arguments or conversation)
- Existing `features.json`
- Previous sprint learnings from `progress.md`
- Current codebase state

### Step 3: Create Atomic Features

Each feature must be:
- **Atomic**: Completable in one session (2-4 hours)
- **Independent**: Minimal dependencies on other features
- **Testable**: Clear acceptance criteria
- **Valuable**: Delivers user value

If a feature would take more than 4 hours, break it down further.

### Step 4: Define Each Feature

```json
{
  "id": "s{N}-feat-{NNN}",
  "category": "core | ui | api | auth | data | infra",
  "priority": "high | medium | low",
  "title": "Short feature title",
  "description": "Detailed description",
  "acceptance_criteria": ["Given [context], when [action], then [outcome]", "..."],
  "technical_notes": "Implementation hints",
  "status": "pending",
  "dependencies": [],
  "estimated_complexity": "small | medium | large",
  "files_affected": ["path/to/file"]
}
```

**ID format**: `s{N}-feat-{NNN}` where N is the sprint number and NNN is zero-padded sequential (e.g., `s1-feat-001`).
**Sprint ID format**: `s{N}` (e.g., `s1`, `s2`).

**Priorities**: `high` = sprint blockers/core, `medium` = important but not blocking, `low` = nice to have.
**Complexity**: `small` (<2h), `medium` (2-4h), `large` (4h+ — break it down).

### Step 5: Order by Dependencies

1. Infrastructure first, then features
2. Core before supporting
3. UI after backend support
4. Features with dependencies must wait

### Step 6: Update Files

**Only modify `features.json` and `progress.md`** — do NOT create extra planning documents.

Update `features.json` with the new sprint and its features. Set sprint status to `in_progress`.

Add a planning entry at the **top** of the sessions section in `progress.md`:

```markdown
## Sprint Planning - YYYY-MM-DD
**Agent**: Sprint Agent
**Sprint**: [Sprint ID and Name]

### Requirements Received
- [User's requirement summary]

### Features Planned
- Total: N features
- High priority: N
- Medium priority: N
- Low priority: N

### Sprint Goal
[Clear goal statement]

### Implementation Order
1. [feature-id] - [title] - [complexity]
2. [feature-id] - [title] - [complexity]

### Notes
[Any context or decisions]
```

### Step 7: Display Summary and Confirm

Show this summary to the user and ask for confirmation before committing:

```markdown
## Sprint Planning Complete

### Sprint: [Name]
**Goal**: [Sprint goal]

### Feature Summary
- Total features: N
- High priority: N
- Low priority: N

### Recommended Implementation Order
1. [id] [title] - [complexity]
2. [id] [title] - [complexity]

### Dependencies
- [id] depends on [id]
- No blockers for: [ids]

### Ready for Development
Run /ghs:code to start implementing the first feature: [first-feature-id]
```

After user confirms:
```bash
git add features.json progress.md
git commit -m "chore: sprint planning - <sprint-name>"
```

## Reference

For detailed schemas, category definitions, and more examples, read `${CLAUDE_PLUGIN_ROOT}/shared/references/sprint-agent.md` and `${CLAUDE_PLUGIN_ROOT}/shared/references/examples.md`.

## Critical Rules

1. **Never Remove Features** — Only add or change status
2. **Unique IDs** — Each feature must have a unique ID
3. **Respect Tech Stack** — Features must be achievable with the project's tech
4. **Balance Sprint** — Mix of complexity levels
5. **Document Decisions** — Explain prioritization rationale
