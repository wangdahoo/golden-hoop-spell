---
name: ghs:init
description: "Initialize agent-harness project tracking files. USE WHEN user wants to set up project tracking, initialize a new project for agent-harness, create features.json and progress.md. Trigger on: 'init project', 'setup tracking', 'new project tracking', 'initialize harness', starting a new managed project. Also use when user mentions wanting to track features, sprints, or multi-session work for the first time."
---

# Initialize Project Tracking

Set up the project with `features.json` and `progress.md` so the agent-harness system can track sprints, features, and progress across sessions.

## Setup

Run the init script from the project directory:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/init_project.py "<PROJECT_NAME>" --description "<DESCRIPTION>" --project-dir "$(pwd)"
```

The script creates:
- **features.json** — Sprint and feature tracking (from template at `${CLAUDE_PLUGIN_ROOT}/shared/assets/features.json`)
- **progress.md** — Session log (from template at `${CLAUDE_PLUGIN_ROOT}/shared/assets/progress.md`)
- Updates **.gitignore** with `.agent-harness`

## After Initialization

1. Verify files were created:
   ```
   ls features.json progress.md
   ```

2. Commit the initialized files:
   ```bash
   git add features.json progress.md .gitignore
   git commit -m "chore: initialize project tracking"
   ```

3. Tell the user to run `/ghs:sprint` to plan their first sprint.

## Project Directory Resolution

All agent-harness commands operate on the current project directory. If the working directory might not be the project root, resolve it first:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

This walks up from the current directory to find where `features.json` or `progress.md` lives.
