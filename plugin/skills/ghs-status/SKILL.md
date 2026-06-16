---
name: ghs:status
description: "Show current project status: active sprint, feature completion stats, and recent session history."
---

# Project Status

Display the current state of the ghs managed project: active sprint, feature completion, and recent sessions.

## Usage

**Verify python3 works** before any other step:
```bash
python3 --version
```
If this errors with "_lazy_pyenv command not found" (or similar), your shell
has a half-loaded pyenv lazy loader. Workaround: use the full path
`/usr/bin/python3` for all subsequent python invocations in this session.

Resolve the project directory:
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
