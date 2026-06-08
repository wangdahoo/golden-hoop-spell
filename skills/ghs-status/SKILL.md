---
name: ghs:status
description: "Show current project status: active sprint, feature completion stats, and recent session history."
---

# Project Status

Display the current state of the ghs managed project: active sprint, feature completion, and recent sessions.

## Usage

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

Then run the status script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/status.py --project-dir "<PROJECT_DIR>"
```

## What It Shows

- **Project info**: name, description, created date
- **Sprint status**: active sprint name, status, goal
- **Feature breakdown**: completed / in-progress / pending / blocked counts
- **Current work**: which feature is in-progress
- **Next up**: which pending feature to implement next
- **Recent sessions**: last 3 entries from .ghs/progress.md

## If No Project Found

If `.ghs/features.json` doesn't exist, tell the user to run `/ghs:init` to set up project tracking.

If there are no sprints, suggest running `/ghs:sprint` to plan the first sprint.
