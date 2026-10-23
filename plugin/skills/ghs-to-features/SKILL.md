---
name: ghs:to-features
description: "Turn a plan document or raw requirements into atomic, implementable features in `.ghs/features.json`. Also use to modify existing plans — add features, change priorities, or replan."
disable-model-invocation: true
---

# Feature Planning

Break down requirements into atomic features with acceptance criteria, dependencies, and priorities. Update `features.json` and `progress.md`.

## Prerequisites

The project must be initialized (have `.ghs/features.json` and `.ghs/progress.md`). If not, tell the user to run `/ghs:init` first.

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Planning Process

### Step 1: Archive Completed Plans

Before creating a new plan, check for completed plans to archive.

**1a. List completed plans:**
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --list --project-dir "<PROJECT_DIR>"
```

**1b. If completed plans exist**, offer to archive them before proceeding:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --project-dir "<PROJECT_DIR>"
```
This archives all completed plans at once — the script determines which ones to archive based on their status.

### Step 2: Analyze Requirements

Break requirements into categories:
- **Core Features** — Essential for the plan goal
- **Supporting Features** — Enhance core functionality
- **Technical Enablers** — Infrastructure, refactoring

Context sources:
- User's requirements (from the command arguments or conversation)
- Existing `.ghs/features.json`
- Previous plan learnings from `.ghs/progress.md`
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
  "id": "p{N}-feat-{NNN}",
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

**ID format**: `p{N}-feat-{NNN}` where N is the plan number and NNN is zero-padded sequential (e.g., `p1-feat-001`).
**Plan ID format**: `p{N}` (e.g., `p1`, `p2`).

**Priorities**: `high` = plan blockers/core, `medium` = important but not blocking, `low` = nice to have.
**Complexity**: `small` (<2h), `medium` (2-4h), `large` (4h+ — break it down).

### Step 5: Order by Dependencies

1. Infrastructure first, then features
2. Core before supporting
3. UI after backend support
4. Features with dependencies must wait

### Step 6: Update Files

**Only modify `.ghs/features.json` and `.ghs/progress.md`** — do NOT create extra planning documents.

Update `.ghs/features.json` with the new plan and its features. Set plan status to `in_progress`.

**Validate the structure** by running:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/validate_structure.py --project-dir "<PROJECT_DIR>"
```
If validation fails, report the errors to the user and ask them to fix the issues before proceeding.

Add a planning entry at the **top** of the sessions section in `.ghs/progress.md`:

```markdown
## Feature Planning - YYYY-MM-DD
**Agent**: To-Features Agent
**Plan**: [Plan ID and Name]

### Requirements Received
- [User's requirement summary]

### Features Planned
- Total: N features
- High priority: N
- Medium priority: N
- Low priority: N

### Plan Goal
[Clear goal statement]

### Implementation Order
1. [feature-id] - [title] - [complexity]
2. [feature-id] - [title] - [complexity]

### Notes
[Any context or decisions]
```

### Step 7: Display Summary and Confirm

Show this summary to the user and ask for confirmation before finalizing the plan:

```markdown
## Feature Planning Complete

### Plan: [Name]
**Goal**: [Plan goal]

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

After user confirms, the plan is ready for development. No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## Reference

For detailed schemas, category definitions, and more examples, read `${CLAUDE_PLUGIN_ROOT}/shared/references/features-agent.md` and `${CLAUDE_PLUGIN_ROOT}/shared/references/examples.md`.

## Critical Rules

1. **Never Remove Features** — Only add or change status
2. **Unique IDs** — Each feature must have a unique ID
3. **Respect Tech Stack** — Features must be achievable with the project's tech
4. **Balance Plan** — Mix of complexity levels
5. **Document Decisions** — Explain prioritization rationale

## Closing Steps

Finish every run of this skill with BOTH closing steps. They are mandatory: every ghs skill sets `disable-model-invocation: true` in its frontmatter, so the model never auto-loads the next skill — after this skill finishes, these pointers are the only channel that routes the user to the next stage of the workflow.

### Step 1: Append the progress.md session entry

Add ONE entry at the **top** of the `## Sessions` section in `<PROJECT_DIR>/.ghs/progress.md`, following the field structure of the Session Template built into that file. The Step 6 planning entry records the plan itself; this session entry records the session and its routing outcome — keep both:

```markdown
## Session N - YYYY-MM-DD
**Agent**: To-Features Agent
**Plan**: [Plan ID if applicable]
**Feature**: [Feature ID if applicable]

### Work Completed
- [What was done in this session]

### Tests Performed
- [How the results were verified]

### Issues Encountered
- [Any blockers, bugs, or challenges]

### Decisions Made
- [Architectural or design choices]

### Next Steps
- [Recommended next actions]
```

`N` continues the numbering of existing `## Session N` entries.

### Step 2: Give the user the next-step guidance

End the session by telling the user exactly what to run next. Never invoke the next ghs skill yourself — with model invocation disabled, every ghs skill is triggered only by an explicit user command:

- Next step: `/ghs:code` — start implementing the first pending feature of the new plan
