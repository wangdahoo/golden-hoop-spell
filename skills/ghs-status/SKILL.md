---
name: ghs:status
description: "Show current project status including sprint progress, feature completion stats, and recent sessions. USE WHEN user wants to check project status, see what's done, see what's next, review progress, or understand the current state of their agent-harness managed project. Trigger on: 'show status', 'project status', 'what's left', 'how's it going', 'progress', 'what features are done', 'sprint status'."
---

# Project Status

Display the current state of the agent-harness managed project: active sprint, feature completion, and recent sessions.

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
- **Recent sessions**: last 3 entries from progress.md

## If No Project Found

If `features.json` doesn't exist, tell the user to run `/ghs:init` to set up project tracking.

If there are no sprints, suggest running `/ghs:sprint` to plan the first sprint.
