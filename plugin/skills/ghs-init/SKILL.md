---
name: ghs:init
description: "Initialize ghs project tracking by creating .ghs/features.json and .ghs/progress.md. Use when setting up a project for ghs for the first time, or when other ghs skills fail because .ghs/ doesn't exist."
disable-model-invocation: true
---

# Initialize Project Tracking

Set up the project with `.ghs/features.json` and `.ghs/progress.md` so the ghs system can track plans, features, and progress across sessions. These files live inside `.ghs/` (gitignored) so they stay local.

## Platform Adaptation
- Claude Code hosts: nothing to do — proceed as written below.
- Other hosts (OpenAI Codex CLI, Pi coding agent): if `${CLAUDE_PLUGIN_ROOT}` below is
  not expanded by your harness, derive the plugin root from the directory of the SKILL.md
  you are executing (its grandparent directory), run
  `command python3 <plugin_root>/shared/scripts/host_compat.py`, then read
  `<plugin_root>/shared/references/codex-host.md` when it reports `"host": "codex"` or
  `<plugin_root>/shared/references/pi-host.md` when it reports `"host": "pi"`, and follow
  that file wherever it supersedes a host-specific instruction below (subagent dispatch,
  interactive questions, plugin-root resolution).

## Setup

Run the init script from the project directory:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/init_project.py "<PROJECT_NAME>" --description "<DESCRIPTION>" --project-dir "$(pwd)"
```

The script creates the `.ghs/` directory with:
- **.ghs/features.json** — Plan and feature tracking (from template at `${CLAUDE_PLUGIN_ROOT}/shared/assets/features.json`)
- **.ghs/progress.md** — Session log (from template at `${CLAUDE_PLUGIN_ROOT}/shared/assets/progress.md`)
- Updates **.gitignore** with `.ghs`

## After Initialization

1. Verify files were created:
   ```
   ls .ghs/features.json .ghs/progress.md
   ```

2. Tell the user to run `/ghs:to-features` to plan their first plan.

## Project Directory Resolution

All ghs commands operate on the current project directory. If the working directory might not be the project root, resolve it first:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

This walks up from the current directory to find where `.ghs/features.json` or `.ghs/progress.md` lives.

## Closing Steps

Finish every run of this skill with this closing step. It is mandatory: every ghs skill sets `disable-model-invocation: true` in its frontmatter, so the model never auto-loads the next skill — after this skill finishes, this pointer is the only channel that routes the user to the next stage of the workflow.

### Step 1: Give the user the next-step guidance

End the session by telling the user exactly what to run next. Never invoke the next ghs skill yourself — with model invocation disabled, every ghs skill is triggered only by an explicit user command:

- Next step: `/ghs:to-features` — break the requirement into an atomic, implementable feature plan
- Alternative: `/ghs:plan` — produce a single technical plan through the plan pipeline (its Phase 6 materializes features itself)
