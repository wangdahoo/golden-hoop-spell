---
name: ghs:init
description: "Initialize ghs project tracking by creating .ghs/features.json and .ghs/progress.md. Use when setting up a project for ghs for the first time, or when other ghs skills fail because .ghs/ doesn't exist."
---

# Initialize Project Tracking

Set up the project with `.ghs/features.json` and `.ghs/progress.md` so the ghs system can track sprints, features, and progress across sessions. These files live inside `.ghs/` (gitignored) so they stay local.

## Setup

Run the init script from the project directory:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/init_project.py "<PROJECT_NAME>" --description "<DESCRIPTION>" --project-dir "$(pwd)"
```

The script creates the `.ghs/` directory with:
- **.ghs/features.json** — Sprint and feature tracking (from template at `${CLAUDE_PLUGIN_ROOT}/shared/assets/features.json`)
- **.ghs/progress.md** — Session log (from template at `${CLAUDE_PLUGIN_ROOT}/shared/assets/progress.md`)
- Updates **.gitignore** with `.ghs`

## After Initialization

1. Verify files were created:
   ```
   ls .ghs/features.json .ghs/progress.md
   ```

2. Tell the user to run `/ghs:sprint` to plan their first sprint.

## Project Directory Resolution

All ghs commands operate on the current project directory. If the working directory might not be the project root, resolve it first:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

This walks up from the current directory to find where `.ghs/features.json` or `.ghs/progress.md` lives.
