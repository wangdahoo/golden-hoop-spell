# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A skill suite that keeps Claude on a leash — iterative planning, structured sprints, and disciplined code delivery. Skills form a pipeline: `init` sets up tracking, `plan` generates technical designs through iterative review, `sprint` breaks work into features, `code` implements them, and `status`/`archive` track and close out progress.

Plugin runtime content (skills, scripts, references, assets) lives under `./plugin/`; the repository root holds development meta (`docs/`, `ghs-workspace/`, READMEs). The root `CLAUDE.md` is intentionally NOT duplicated into `./plugin/` — per the official Claude Code docs, a plugin-root `CLAUDE.md` is not loaded as project context (plugins contribute context through skills, agents, and hooks).

## Architecture

Each skill is a self-contained directory under `plugin/skills/` with a `SKILL.md` that defines behavior. Skills delegate deterministic operations to Python scripts in `plugin/shared/scripts/` and reference detailed workflows in `plugin/shared/references/`. All tracking state lives in the target project's `.ghs/` directory (gitignored), using `features.json` for sprint/feature tracking and `progress.md` for session logs.

The typical skill workflow: resolve project directory via `resolve_project_dir.py` → read `.ghs/` state → perform task → update `.ghs/` state.

`ghs:plan` uses a three-role architecture: a dispatcher (main conversation) orchestrates a plan designer (Plan subagent) and a plan reviewer (general-purpose subagent) through up to 5 review-revise rounds, communicating via files under `.ghs/plans/`.

## Notes

Historical plan documents under `docs/ghs/plans/` reference the pre-move `skills/` and `shared/` paths (i.e. without the `plugin/` prefix). These are timestamped archives describing past repository states; they are not updated when the layout changes. Refer to the current `## Architecture` section above for the live layout.

## Conventions

- Skill names use `ghs:` prefix; directories use kebab-case (e.g., `ghs-init/`)
- Skills reference shared resources via `${CLAUDE_PLUGIN_ROOT}/shared/`
- Feature IDs follow `s{N}-feat-{NNN}` format
- Commit messages use conventional format: `<type>(<scope>): <description>`
- Each session logs to `.ghs/progress.md` at the top of the sessions section

## Critical Rules

- **Language policy (applies to ALL agents including subagents/parallel agents)**:
  - **Chinese**: All human-readable output — conversation with user, technical documentation (CONTEXT.md, ADRs, READMEs, inline doc comments, PR descriptions), commit messages, git branch names' descriptive parts, TODO/FIXME comments, and task/plan descriptions.
  - **English**: Source code identifiers, log messages, error strings, and LLM-facing prompts/instructions (e.g. skill definitions, agent prompts).
  - **Subagent enforcement**: When spawning any agent (Agent tool, parallel agents, worktree agents), the prompt to the agent MUST include the instruction: "使用中文回复和撰写所有文档/commit message。代码标识符、日志、错误信息用英文。" This ensures delegated work also follows the policy regardless of whether the subagent inherits this file.
- When running eval loops with `/skill-creator`, use the `ghs-workspace` directory as the working directory.
