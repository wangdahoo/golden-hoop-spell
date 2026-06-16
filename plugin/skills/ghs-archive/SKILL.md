---
name: ghs:archive
description: "Archive completed sprints to clean up active project state. Only archives sprints with status 'completed'. For incomplete sprints, use /ghs:force-archive instead."
---

# Archive Completed Sprints

Move completed sprints from the active `.ghs/features.json` to `.ghs/archived/`, keeping the project state clean for the next sprint.

## Prerequisites

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Workflow

### Step 1: List Completed Sprints

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py --list --project-dir "<PROJECT_DIR>"
```

Show the user which sprints are eligible for archiving (status: `completed`).

### Step 2: Preview (optional)

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py --dry-run --project-dir "<PROJECT_DIR>"
```

### Step 3: Archive

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py --project-dir "<PROJECT_DIR>"
```

This will:
- Create `.ghs/archived/<sprint-id>_<name>_<timestamp>/`
- Save sprint data and related sessions to the archive folder
- Remove the archived sprint from `.ghs/features.json`
- Reset `.ghs/progress.md` to the default template

No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## What Gets Archived

- Sprint feature data → `.ghs/archived/<folder>/features.json`
- Related progress sessions → `.ghs/archived/<folder>/progress.md`
- Sprint is removed from `.ghs/features.json`
- `.ghs/progress.md` is reset to the default template

## If No Completed Sprints

If there are no completed sprints, tell the user. They may need to:
- Mark the sprint as completed (all features done)
- Or use `/ghs:force-archive` if they want to archive regardless of status
