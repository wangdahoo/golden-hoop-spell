---
name: ghs:archive
description: "Archive the feature groups of completed plans to clean up active project state. Only archives plans with status 'completed'. For incomplete plans, use /ghs:force-archive instead."
disable-model-invocation: true
---

# Archive Completed Plans

Move completed plans' feature groups from the active `.ghs/features.json` to `.ghs/archived/`, keeping the project state clean for the next plan.

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
- Save the plan's feature data and a full snapshot of the complete Sessions section to the archive folder
- Remove the archived plan from `.ghs/features.json`
- Update `.ghs/progress.md`: reset to the default template when no plans remain; otherwise remove only the archived plan's entries

No git commit needed — `.ghs/` tracking files are local metadata (gitignored by `ghs:init`).

## What Gets Archived

- Plan feature data → `.ghs/archived/<folder>/features.json`
- Full snapshot of the complete Sessions section → `.ghs/archived/<folder>/progress.md`
- Plan is removed from `.ghs/features.json`
- `.ghs/progress.md`: reset to the default template when no plans remain; otherwise only the archived plan's entries are removed

## If No Completed Plans

If there are no completed plans, probe each active plan first — the plan status may simply be stale (all features done, status never flipped):

1. For each plan in `.ghs/features.json`, run:
   ```bash
   command python3 ${CLAUDE_PLUGIN_ROOT}/shared/scripts/update_features.py \
     --file <PROJECT_DIR>/.ghs/features.json --plan-state <plan_id>
   ```
2. If a plan reports `"can_complete": true` but the plan status is not `completed`, use AskUserQuestion:「计划 <plan_id> 全部特性已完成但状态未翻转，是否标记为 completed 并继续归档？」On confirm, run `--set-plan <plan_id> --status completed`, then re-run Step 1 (`archive_plans.py --list`) and continue the normal flow.
3. If every remaining plan still has pending/in_progress/blocked features, tell the user. They may need to:
   - Complete the remaining features first (`/ghs:code`)
   - Or use `/ghs:force-archive` if they want to archive regardless of status

## Closing Steps

Finish every run of this skill with BOTH closing steps. They are mandatory: every ghs skill sets `disable-model-invocation: true` in its frontmatter, so the model never auto-loads the next skill — after this skill finishes, these pointers are the only channel that routes the user to the next stage of the workflow.

### Step 1: Append the progress.md session entry

Add ONE entry at the **top** of the `## Sessions` section in `<PROJECT_DIR>/.ghs/progress.md`, following the field structure defined in `${CLAUDE_PLUGIN_ROOT}/shared/references/session-entry-format.md`. Run this step AFTER `archive_plans.py` — when no plans remain the script resets `.ghs/progress.md` to the default template, so the entry must be appended afterwards; when plans remain the script removes only the archived plan's entries and the entry is inserted at the top as usual:

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
