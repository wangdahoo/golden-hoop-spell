---
name: ghs:archive
description: "Archive the feature groups of completed plans to clean up active project state. Only archives plans with status 'completed'. For incomplete plans, use /ghs:force-archive instead."
disable-model-invocation: true
---

# Archive Completed Plans

Move completed plans' feature groups from the active `.ghs/features.json` to `.ghs/archived/`, keeping the project state clean for the next plan.

## Prerequisites

Resolve the project directory:
```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/resolve_project_dir.py
```

## Workflow

### Step 1: List Completed Plans

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --list --project-dir "<PROJECT_DIR>"
```

Show the user which plans are eligible for archiving (status: `completed`).

### Step 2: Preview (optional)

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --dry-run --project-dir "<PROJECT_DIR>"
```

### Step 3: Archive

```bash
command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/archive_plans.py --project-dir "<PROJECT_DIR>"
```

This will:
- Create `.ghs/archived/<plan-id>_<name>_<timestamp>/`
- Save the plan's feature data and related sessions to the archive folder
- Remove the archived plan from `.ghs/features.json`
- Reset `.ghs/progress.md` to the default template

No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## What Gets Archived

- Plan feature data → `.ghs/archived/<folder>/features.json`
- Related progress sessions → `.ghs/archived/<folder>/progress.md`
- Plan is removed from `.ghs/features.json`
- `.ghs/progress.md` is reset to the default template

## If No Completed Plans

If there are no completed plans, tell the user. They may need to:
- Mark the plan as completed (all features done)
- Or use `/ghs:force-archive` if they want to archive regardless of status

## Closing Steps

Finish every run of this skill with BOTH closing steps. They are mandatory: every ghs skill sets `disable-model-invocation: true` in its frontmatter, so the model never auto-loads the next skill — after this skill finishes, these pointers are the only channel that routes the user to the next stage of the workflow.

### Step 1: Append the progress.md session entry

Add ONE entry at the **top** of the `## Sessions` section in `<PROJECT_DIR>/.ghs/progress.md`, following the field structure of the Session Template built into that file. Run this step AFTER `archive_plans.py` — the script resets `.ghs/progress.md` to the default template, so the entry must be appended afterwards:

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
