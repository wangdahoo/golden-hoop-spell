---
name: ghs:force-archive
description: "Force archive ALL plans regardless of status, including incomplete ones. Destructive — always confirms with the user first. For routine archiving of completed plans, use /ghs:archive instead."
---

# Force Archive All Plans

Archive **all** plans' feature groups, including those that are in-progress, planning, or on-hold. This is a destructive operation — always confirm with the user first.

## Prerequisites

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Workflow

### Step 1: List ALL Plans

Show the user what will be archived:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --list --force --project-dir "<PROJECT_DIR>"
```

### Step 2: Confirm with User

**WARNING**: Display all plans that will be archived and their statuses. Ask the user to explicitly confirm. Example:

```
The following plans will be archived:
  - Plan 1: Authentication (p1) [in_progress] - 3/6 features completed
  - Plan 2: Dashboard (p2) [planning] - 0/4 features completed

This action will move all plan feature data to .ghs/archived/ and reset .ghs/progress.md.
Are you sure you want to proceed?
```

Do NOT proceed without explicit user confirmation.

### Step 3: Archive

After confirmation:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --force --project-dir "<PROJECT_DIR>"
```

This will:
- Archive all plans' feature data to `.ghs/archived/`
- Remove all plans from `.ghs/features.json` (project info is preserved)
- Reset `.ghs/progress.md` to the default template

No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## After Force Archive

The project still has `.ghs/features.json` and `.ghs/progress.md` — just with no active plans. The user can run `/ghs:to-features` to build a new plan from scratch.

Archived data is preserved in `.ghs/archived/` for reference.
