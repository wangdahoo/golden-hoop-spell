---
name: ghs:force-archive
description: "Force archive ALL sprints regardless of their status, including incomplete ones. USE WHEN user wants to reset the project state, start fresh, force archive everything, or clear all sprint data. This is a destructive operation — always confirm with the user before proceeding. Trigger on: 'force archive', 'reset project', 'archive everything', 'clear all sprints', 'start over'."
---

# Force Archive All Sprints

Archive **all** sprints, including those that are in-progress, planning, or on-hold. This is a destructive operation — always confirm with the user first.

## Prerequisites

Resolve the project directory:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Workflow

### Step 1: List ALL Sprints

Show the user what will be archived:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py --list --force --project-dir "<PROJECT_DIR>"
```

### Step 2: Confirm with User

**WARNING**: Display all sprints that will be archived and their statuses. Ask the user to explicitly confirm. Example:

```
The following sprints will be archived:
  - Sprint 1: Authentication (s1) [in_progress] - 3/6 features completed
  - Sprint 2: Dashboard (s2) [planning] - 0/4 features completed

This action will move all sprint data to .agent-harness/archived/ and reset progress.md.
Are you sure you want to proceed?
```

Do NOT proceed without explicit user confirmation.

### Step 3: Archive

After confirmation:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_sprint.py --force --project-dir "<PROJECT_DIR>"
```

This will:
- Archive all sprints to `.agent-harness/archived/`
- Remove all sprints from `features.json` (project info is preserved)
- Reset `progress.md` to the default template

### Step 4: Commit

```bash
git add -A
git commit -m "chore: force archive all sprints"
```

## After Force Archive

The project still has `features.json` and `progress.md` — just with no active sprints. The user can run `/ghs:sprint` to plan a new sprint from scratch.

Archived data is preserved in `.agent-harness/archived/` for reference.
