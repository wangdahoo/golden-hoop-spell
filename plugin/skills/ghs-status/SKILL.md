---
name: ghs:status
description: "Show current project status: active plan, feature completion stats, and recent session history."
disable-model-invocation: true
---

# Project Status

Display the current state of the ghs managed project: active plan, feature completion, and recent sessions.

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

## Usage

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

Then run the status script:

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/status.py --project-dir "<PROJECT_DIR>"
```

## What It Shows

- **Project info**: name, description, created date
- **Plan status**: active plan name, status, goal
- **Feature breakdown**: completed / in-progress / pending / blocked counts
- **Current work**: which feature is in-progress
- **Next up**: which pending feature to implement next
- **Recent sessions**: last 3 entries from .ghs/progress.md

## If No Project Found

If `.ghs/features.json` doesn't exist, tell the user to run `/ghs:init` to set up project tracking.

If there are no plans, suggest running `/ghs:to-features` to plan the first plan.

## Closing Steps

Finish every run of this skill with BOTH closing steps. They are mandatory: every ghs skill sets `disable-model-invocation: true` in its frontmatter, so the model never auto-loads the next skill — after this skill finishes, these pointers are the only channel that routes the user to the next stage of the workflow.

### Step 1: Append the progress.md session entry

Add ONE entry at the **top** of the `## Sessions` section in `<PROJECT_DIR>/.ghs/progress.md`, following the field structure of the Session Template built into that file:

```markdown
## Session N - YYYY-MM-DD
**Agent**: Status Agent
**Plan**: [Plan ID if applicable]
**Feature**: [Feature ID if applicable]

### Work Completed
- [What was done in this session]

### Tests Performed
- [How the results were verified]

### Issues Encountered
- [Any blockers, bugs, or challenges]

### Decisions Made
- [Architectural or design choices]

### Next Steps
- [Recommended next actions]
```

`N` continues the numbering of existing `## Session N` entries.

### Step 2: Give the user the next-step guidance

End the session by telling the user exactly what to run next. Never invoke the next ghs skill yourself — with model invocation disabled, every ghs skill is triggered only by an explicit user command:

- If the active plan is completed (all features done): `/ghs:archive` — archive the plan's feature groups to clean up active state
- If features remain: `/ghs:code` — implement the next pending feature
