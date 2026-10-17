---
name: ghs:archive
description: "Archive the feature groups of completed plans to clean up active project state. Only archives plans with status 'completed'. For incomplete plans, use /ghs:force-archive instead."
---

# Archive Completed Plans

Move completed plans' feature groups from the active `.ghs/features.json` to `.ghs/archived/`, keeping the project state clean for the next plan.

## Prerequisites

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Workflow

### Step 1: List Completed Plans

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --list --project-dir "<PROJECT_DIR>"
```

Show the user which plans are eligible for archiving (status: `completed`).

### Step 2: Preview (optional)

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --dry-run --project-dir "<PROJECT_DIR>"
```

### Step 3: Archive

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --project-dir "<PROJECT_DIR>"
```

This will:
- Create `.ghs/archived/<plan-id>_<name>_<timestamp>/`
- Save the plan's feature data and related sessions to the archive folder
- Remove the archived plan from `.ghs/features.json`
- Reset `.ghs/progress.md` to the default template

No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## What Gets Archived

- Plan feature data → `.ghs/archived/<folder>/features.json`
- Related progress sessions → `.ghs/archived/<folder>/progress.md`
- Plan is removed from `.ghs/features.json`
- `.ghs/progress.md` is reset to the default template

## If No Completed Plans

If there are no completed plans, tell the user. They may need to:
- Mark the plan as completed (all features done)
- Or use `/ghs:force-archive` if they want to archive regardless of status
