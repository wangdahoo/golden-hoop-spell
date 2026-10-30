---
name: ghs:force-archive
description: "Force archive ALL plans regardless of status, including incomplete ones. Destructive — always confirms with the user first. For routine archiving of completed plans, use /ghs:archive instead."
disable-model-invocation: true
---

# Force Archive All Plans

Archive **all** plans' feature groups, including those that are in-progress, planning, or on-hold. This is a destructive operation — always confirm with the user first.

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

## Prerequisites

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Workflow

### Step 1: List ALL Plans

Show the user what will be archived:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --list --force --project-dir "<PROJECT_DIR>"
```

### Step 2: Confirm with User

**WARNING**: Display all plans that will be archived and their statuses. Ask the user to explicitly confirm. Example:

```
The following plans will be archived:
  - Plan 1: Authentication (p1) [in_progress] - 3/6 features completed
  - Plan 2: Dashboard (p2) [planning] - 0/4 features completed

This action will move all plan feature data to .ghs/archived/ and reset .ghs/progress.md.
Are you sure you want to proceed?
```

Do NOT proceed without explicit user confirmation.

### Step 3: Archive

After confirmation:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --force --project-dir "<PROJECT_DIR>"
```

This will:
- Archive all plans' feature data to `.ghs/archived/`
- Remove all plans from `.ghs/features.json` (project info is preserved)
- Reset `.ghs/progress.md` to the default template

No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## After Force Archive

The project still has `.ghs/features.json` and `.ghs/progress.md` — just with no active plans. The user can run `/ghs:to-features` to build a new plan from scratch.

Archived data is preserved in `.ghs/archived/` for reference.

## Closing Steps

Finish every run of this skill with BOTH closing steps. They are mandatory: every ghs skill sets `disable-model-invocation: true` in its frontmatter, so the model never auto-loads the next skill — after this skill finishes, these pointers are the only channel that routes the user to the next stage of the workflow.

### Step 1: Append the progress.md session entry

Add ONE entry at the **top** of the `## Sessions` section in `<PROJECT_DIR>/.ghs/progress.md`, following the field structure defined in `${CLAUDE_PLUGIN_ROOT}/shared/references/session-entry-format.md`. Run this step AFTER `archive_plans.py` — the script resets `.ghs/progress.md` to the default template, so the entry must be appended afterwards:

```markdown
## Session N - YYYY-MM-DD
**Agent**: Archive Agent
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

- Done — archiving closes the ghs lifecycle for the archived plans; no next command is required
- To start a new round of work later: `/ghs:to-features` (or `/ghs:plan`) — begin the next plan
